"""Vistas para que el profesor administre el catalogo de preguntas."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from apps.usuarios.models import Persona
from apps.usuarios.decoradores import roles_permitidos

from .models import Pregunta, SolicitudGeneracion
from .forms import GenerarPreguntaForm, PreguntaForm, OpcionRespuestaFormSet
from .servicios import (
    alcanzo_el_tope,
    hay_llave_configurada,
    lanzar_generacion,
    mensaje_de_espera,
    solicitudes_de_la_ultima_hora,
)

# El profesor y el administrador pueden dar de alta preguntas.
ROLES_CATALOGO = (Persona.Rol.PROFESOR, Persona.Rol.ADMINISTRADOR)

# Se te acabo el cupo de la hora. El texto es el mismo en la pantalla de
# generacion y en la de espera, asi que vive en un solo lugar.
AVISO_TOPE = (
    'Alcanzaste el límite de {limite} generaciones por hora. La cuota del '
    'proveedor la comparte toda la institución, así que el límite existe para '
    'que no se agote para los demás. Puedes seguir capturando preguntas a '
    'mano mientras tanto.'
)


@login_required
@roles_permitidos(*ROLES_CATALOGO)
def lista_preguntas(request):
    """Muestra el listado de preguntas, con filtro por estado.

    El filtro que importa es el de borradores: son las preguntas generadas que
    estan esperando a que alguien las revise, y sin el se pierden entre las
    demas conforme crece el banco.
    """
    preguntas = (
        Pregunta.objects
        .select_related('materia', 'categoria', 'nivel')
        .all()
    )

    estado = request.GET.get('estado', '')
    if estado in Pregunta.Estado.values:
        preguntas = preguntas.filter(estado=estado)
    else:
        estado = ''

    contexto = {
        'preguntas': preguntas,
        'estado': estado,
        'estados': Pregunta.Estado.choices,
        'borradores': Pregunta.objects.filter(
            estado=Pregunta.Estado.BORRADOR
        ).count(),
        'hay_ia': hay_llave_configurada(),
    }
    return render(request, 'catalogo/lista_preguntas.html', contexto)


@login_required
@roles_permitidos(*ROLES_CATALOGO)
def generar_pregunta(request):
    """Pide una pregunta al proveedor y manda a la pantalla de espera.

    La llamada no se hace aqui: se lanza en segundo plano y esta vista
    responde de inmediato con una redireccion. Sostener la peticion los veinte
    o sesenta segundos que tarda no funcionaria, porque un servidor de
    produccion suele cortar a los treinta.
    """
    if not hay_llave_configurada():
        # Sin llave no tiene caso ofrecer el formulario: cada intento fallaria
        # igual y el profesor no puede hacer nada al respecto.
        messages.error(
            request,
            'La generación con inteligencia artificial no está configurada en '
            'este servidor. Avisa al administrador; mientras tanto puedes '
            'capturar preguntas a mano.',
        )
        return redirect('catalogo:lista_preguntas')

    restantes = settings.AI_LIMITE_POR_HORA - solicitudes_de_la_ultima_hora(request.user)

    if request.method == 'POST':
        formulario = GenerarPreguntaForm(request.POST)
        if alcanzo_el_tope(request.user):
            # Se vuelve a revisar aqui y no solo al pintar el formulario,
            # porque entre una cosa y la otra pudo pedir varias en otra pestaña.
            messages.error(
                request, AVISO_TOPE.format(limite=settings.AI_LIMITE_POR_HORA)
            )
            return redirect('catalogo:lista_preguntas')
        if formulario.is_valid():
            solicitud = lanzar_generacion(
                profesor=request.user,
                categoria=formulario.cleaned_data['categoria'],
                nivel=formulario.cleaned_data['nivel'],
            )
            return redirect('catalogo:esperar_generacion', solicitud_id=solicitud.id)
    else:
        formulario = GenerarPreguntaForm()

    contexto = {
        'formulario': formulario,
        'restantes': max(restantes, 0),
        'limite': settings.AI_LIMITE_POR_HORA,
    }
    return render(request, 'catalogo/generar_pregunta.html', contexto)


@login_required
@roles_permitidos(*ROLES_CATALOGO)
def esperar_generacion(request, solicitud_id):
    """Pantalla de espera mientras el hilo habla con el proveedor."""
    solicitud = get_object_or_404(
        SolicitudGeneracion.objects.select_related('categoria__materia', 'nivel'),
        id=solicitud_id,
    )
    situacion = mensaje_de_espera(solicitud)

    # Cuando ya hay pregunta se va directo a revisarla. Asi el sondeo solo
    # tiene que recargar esta pagina, y quien decide a donde ir es la vista y
    # no el JavaScript.
    if situacion['estado'] == 'lista':
        return redirect(
            'catalogo:revisar_pregunta', pregunta_id=situacion['pregunta_id']
        )

    contexto = {'solicitud': solicitud, 'situacion': situacion}
    return render(request, 'catalogo/esperar_generacion.html', contexto)


@login_required
@roles_permitidos(*ROLES_CATALOGO)
def estado_generacion(request, solicitud_id):
    """Sondeo de la pantalla de espera. No hay WebSockets en el proyecto.

    Nunca devuelve el campo detalle del error: ese texto es del proveedor, va
    a la bitacora, y si se pintara en pantalla pareceria que el sistema se
    rompio cuando en realidad el problema es de quien atiende la peticion.
    """
    solicitud = get_object_or_404(SolicitudGeneracion, id=solicitud_id)
    return JsonResponse(mensaje_de_espera(solicitud))


@login_required
@roles_permitidos(*ROLES_CATALOGO)
def revisar_pregunta(request, pregunta_id):
    """Muestra la pregunta generada con el dictamen del verificador.

    Las rechazadas se muestran igual que las aprobadas, con el motivo a la
    vista: es lo que le da al profesor la confianza de que el sistema si
    revisa lo que el modelo propone.
    """
    pregunta = get_object_or_404(
        Pregunta.objects.select_related(
            'materia', 'categoria', 'nivel', 'creada_por', 'solicitud'
        ),
        id=pregunta_id,
    )
    contexto = {
        'pregunta': pregunta,
        'opciones': pregunta.opciones.all(),
        # Quien la genero es el responsable de revisarla, pero cualquiera con
        # acceso al catalogo puede echarle una mano.
        'es_mia': pregunta.creada_por_id == request.user.id,
    }
    return render(request, 'catalogo/revisar_pregunta.html', contexto)


@login_required
@roles_permitidos(*ROLES_CATALOGO)
@require_POST
def resolver_pregunta(request, pregunta_id):
    """Valida o descarta una pregunta desde la pantalla de revision.

    Una pregunta que el verificador rechazo si se puede validar despues de
    corregirla: buena parte de sus rechazos son de formato -unidades, coma
    decimal- y no errores de matematicas. Lo que no se toca es
    verificada_simbolicamente ni el motivo, para que en el capitulo de
    resultados siga distinguiendose lo que rechazo la maquina de lo que
    rescato una persona.
    """
    pregunta = get_object_or_404(Pregunta, id=pregunta_id)
    accion = request.POST.get('accion')

    if accion == 'validar':
        pregunta.estado = Pregunta.Estado.VALIDADA
        aviso = 'La pregunta quedó validada y ya puede entrar a una evaluación.'
    elif accion == 'descartar':
        pregunta.estado = Pregunta.Estado.DESCARTADA
        aviso = 'La pregunta quedó descartada y no entrará a ninguna evaluación.'
    else:
        messages.error(request, 'No se reconoció la acción solicitada.')
        return redirect('catalogo:revisar_pregunta', pregunta_id=pregunta.id)

    pregunta.save(update_fields=['estado'])
    messages.success(request, aviso)
    return redirect('catalogo:lista_preguntas')


@login_required
@roles_permitidos(*ROLES_CATALOGO)
def crear_pregunta(request):
    """Da de alta una pregunta nueva junto con sus cuatro opciones."""
    if request.method == 'POST':
        formulario = PreguntaForm(request.POST, request.FILES)
        opciones = OpcionRespuestaFormSet(request.POST, request.FILES)

        if formulario.is_valid() and opciones.is_valid():
            pregunta = formulario.save(commit=False)
            # La materia se deduce de la categoria elegida.
            pregunta.materia = pregunta.categoria.materia
            pregunta.creada_por = request.user
            # La escribio una persona, asi que no necesita pasar por revision.
            pregunta.origen = Pregunta.Origen.MANUAL
            pregunta.estado = Pregunta.Estado.VALIDADA
            pregunta.save()

            # Una vez guardada la pregunta se le asocian sus opciones.
            opciones.instance = pregunta
            opciones.save()

            messages.success(request, 'La pregunta se guardo correctamente.')
            return redirect('catalogo:lista_preguntas')
    else:
        formulario = PreguntaForm()
        opciones = OpcionRespuestaFormSet()

    contexto = {'formulario': formulario, 'opciones': opciones}
    return render(request, 'catalogo/formulario_pregunta.html', contexto)


@login_required
@roles_permitidos(*ROLES_CATALOGO)
def editar_pregunta(request, pregunta_id):
    """Modifica una pregunta que ya existe junto con sus cuatro opciones."""
    pregunta = get_object_or_404(Pregunta, id=pregunta_id)

    if request.method == 'POST':
        formulario = PreguntaForm(request.POST, request.FILES, instance=pregunta)
        opciones = OpcionRespuestaFormSet(request.POST, request.FILES, instance=pregunta)

        if formulario.is_valid() and opciones.is_valid():
            pregunta = formulario.save(commit=False)
            # La materia se vuelve a deducir por si le cambiaron la categoria.
            pregunta.materia = pregunta.categoria.materia
            pregunta.save()
            opciones.save()

            messages.success(request, 'La pregunta se actualizo correctamente.')
            # Un borrador sigue en revision: se regresa a la pantalla del
            # dictamen para que quien lo corrigio pueda validarlo enseguida.
            if pregunta.estado == Pregunta.Estado.BORRADOR:
                return redirect('catalogo:revisar_pregunta', pregunta_id=pregunta.id)
            return redirect('catalogo:lista_preguntas')
    else:
        formulario = PreguntaForm(instance=pregunta)
        opciones = OpcionRespuestaFormSet(instance=pregunta)

    contexto = {'formulario': formulario, 'opciones': opciones, 'pregunta': pregunta}
    return render(request, 'catalogo/formulario_pregunta.html', contexto)
