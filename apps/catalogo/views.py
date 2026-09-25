"""Vistas para que el profesor administre el catalogo de preguntas."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from apps.usuarios.models import Persona
from apps.usuarios.decoradores import roles_permitidos
from apps.usuarios.listados import resolver_orden

from .models import Categoria, Institucion, Materia, Nivel, Pregunta, SolicitudGeneracion
from .forms import (
    GenerarPreguntaForm, PreguntaForm, OpcionRespuestaFormSet,
    InstitucionForm, MateriaForm, CategoriaForm, DescripcionesNivelForm, NivelForm,
)
from .procedimientos import pasos_a_texto, texto_a_pasos
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


# Columnas por las que se puede ordenar el listado: la clave es la que viaja en
# la URL y el valor es el campo real por el que ordena la base de datos.
ORDEN_PREGUNTAS = {
    'materia': 'materia__nombre',
    'categoria': 'categoria__nombre',
    'nivel': 'nivel__numero',
    'estado': 'estado',
    'origen': 'origen',
}


@login_required
@roles_permitidos(*ROLES_CATALOGO)
def lista_preguntas(request):
    """Muestra el listado de preguntas, con filtros y ordenamiento.

    Se puede acotar por materia, categoria, nivel, estado y origen, y ordenar
    por cualquiera de esas columnas. Todo se resuelve en el servidor -asi
    funciona sin JavaScript y se puede compartir por la URL-; el buscador que
    resalta palabras si vive en el navegador, sobre los renglones ya filtrados.

    El filtro que mas importa es el de borradores: son las preguntas generadas
    que esperan revision, y sin el se pierden entre las demas conforme crece el
    banco.
    """
    preguntas = (
        Pregunta.objects
        .select_related(
            'materia', 'categoria', 'nivel',
            'creada_por', 'modificada_por', 'solicitud',
        )
        .all()
    )

    # Filtros. Cada uno se queda vacio si lo que llega no es valido, para que la
    # pantalla no se rompa con un parametro inventado en la URL.
    estado = request.GET.get('estado', '')
    if estado in Pregunta.Estado.values:
        preguntas = preguntas.filter(estado=estado)
    else:
        estado = ''

    origen = request.GET.get('origen', '')
    if origen in Pregunta.Origen.values:
        preguntas = preguntas.filter(origen=origen)
    else:
        origen = ''

    materia_id = request.GET.get('materia', '')
    if materia_id.isdigit():
        preguntas = preguntas.filter(materia_id=materia_id)
    else:
        materia_id = ''

    categoria_id = request.GET.get('categoria', '')
    if categoria_id.isdigit():
        preguntas = preguntas.filter(categoria_id=categoria_id)
    else:
        categoria_id = ''

    nivel_id = request.GET.get('nivel', '')
    if nivel_id.isdigit():
        preguntas = preguntas.filter(nivel_id=nivel_id)
    else:
        nivel_id = ''

    # Filtros vigentes, para conservarlos al armar los enlaces de ordenamiento.
    filtros_activos = {}
    if estado:
        filtros_activos['estado'] = estado
    if origen:
        filtros_activos['origen'] = origen
    if materia_id:
        filtros_activos['materia'] = materia_id
    if categoria_id:
        filtros_activos['categoria'] = categoria_id
    if nivel_id:
        filtros_activos['nivel'] = nivel_id

    # Ordenamiento. Sin orden explicito se respeta el del modelo (mas reciente
    # primero); el id al final desempata para que la lista no baile entre cargas.
    campo, orden, direccion, columnas_orden = resolver_orden(
        request, ORDEN_PREGUNTAS, filtros_activos
    )
    if campo:
        preguntas = preguntas.order_by(*campo, 'id')

    contexto = {
        'preguntas': preguntas,
        'estado': estado,
        'origen': origen,
        'materia_id': materia_id,
        'categoria_id': categoria_id,
        'nivel_id': nivel_id,
        'estados': Pregunta.Estado.choices,
        'origenes': Pregunta.Origen.choices,
        'materias': Materia.objects.all(),
        'categorias': Categoria.objects.select_related('materia').all(),
        'niveles': Nivel.objects.all(),
        'orden': orden,
        'direccion': direccion,
        'columnas_orden': columnas_orden,
        'hay_filtros': bool(filtros_activos),
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

    pregunta.modificada_por = request.user
    pregunta.save(update_fields=['estado', 'modificada_por', 'fecha_modificacion'])
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
            # El procedimiento se arma con los pasos capturados, numerado.
            pregunta.procedimiento = pasos_a_texto(request.POST.getlist('paso'))
            pregunta.save()

            # Una vez guardada la pregunta se le asocian sus opciones.
            opciones.instance = pregunta
            opciones.save()

            messages.success(request, 'La pregunta se guardo correctamente.')
            return redirect('catalogo:lista_preguntas')
        # Al recargar por un error se conserva lo que ya habia tecleado.
        pasos = request.POST.getlist('paso')
    else:
        formulario = PreguntaForm()
        opciones = OpcionRespuestaFormSet()
        pasos = []

    contexto = {'formulario': formulario, 'opciones': opciones, 'pasos': pasos}
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
            # El procedimiento se rehace con los pasos capturados, numerado.
            pregunta.procedimiento = pasos_a_texto(request.POST.getlist('paso'))
            pregunta.modificada_por = request.user
            pregunta.save()
            opciones.save()

            messages.success(request, 'La pregunta se actualizo correctamente.')
            # Un borrador sigue en revision: se regresa a la pantalla del
            # dictamen para que quien lo corrigio pueda validarlo enseguida.
            if pregunta.estado == Pregunta.Estado.BORRADOR:
                return redirect('catalogo:revisar_pregunta', pregunta_id=pregunta.id)
            return redirect('catalogo:lista_preguntas')
        # Al recargar por un error se conserva lo que ya habia tecleado.
        pasos = request.POST.getlist('paso')
    else:
        formulario = PreguntaForm(instance=pregunta)
        opciones = OpcionRespuestaFormSet(instance=pregunta)
        # Los pasos guardados se vuelven a repartir en un campo por paso.
        pasos = texto_a_pasos(pregunta.procedimiento)

    contexto = {
        'formulario': formulario,
        'opciones': opciones,
        'pregunta': pregunta,
        'pasos': pasos,
    }
    return render(request, 'catalogo/formulario_pregunta.html', contexto)


# El resto de las vistas de este archivo son el CRUD del administrador para
# los catalogos: instituciones, disciplinas, asignaturas y niveles. Ninguna
# borra registros; Materia y Categoria ya tienen su bandera "activa" para
# retirarlas sin perder el historico de preguntas que las usan.

# Columnas ordenables de cada listado del administrador.
ORDEN_INSTITUCIONES = {'nombre': 'nombre'}
ORDEN_MATERIAS = {'nombre': 'nombre', 'estado': 'activa'}
ORDEN_CATEGORIAS = {'materia': 'materia__nombre', 'nombre': 'nombre', 'estado': 'activa'}
ORDEN_NIVELES = {'numero': 'numero', 'nombre': 'nombre'}


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def lista_instituciones(request):
    """Listado de instituciones. El modelo no trae Meta.ordering, asi que se
    ordena por nombre aqui mismo cuando no se pide ningun orden explicito."""
    instituciones = Institucion.objects.all()

    campo, orden, direccion, columnas_orden = resolver_orden(request, ORDEN_INSTITUCIONES)
    instituciones = instituciones.order_by(*(campo or ('nombre',)), 'id')

    contexto = {
        'instituciones': instituciones,
        'orden': orden,
        'direccion': direccion,
        'columnas_orden': columnas_orden,
    }
    return render(request, 'catalogo/lista_instituciones.html', contexto)


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def crear_institucion(request):
    """Da de alta una institucion nueva."""
    if request.method == 'POST':
        formulario = InstitucionForm(request.POST)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, 'La institución se guardó correctamente.')
            return redirect('catalogo:lista_instituciones')
    else:
        formulario = InstitucionForm()

    return render(request, 'catalogo/formulario_institucion.html', {'formulario': formulario})


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def editar_institucion(request, institucion_id):
    """Modifica una institucion que ya existe."""
    institucion = get_object_or_404(Institucion, id=institucion_id)

    if request.method == 'POST':
        formulario = InstitucionForm(request.POST, instance=institucion)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, 'La institución se actualizó correctamente.')
            return redirect('catalogo:lista_instituciones')
    else:
        formulario = InstitucionForm(instance=institucion)

    contexto = {'formulario': formulario, 'institucion': institucion}
    return render(request, 'catalogo/formulario_institucion.html', contexto)


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def lista_materias(request):
    """Listado de disciplinas, con filtros de estado y si es cuantitativa."""
    materias = Materia.objects.all()

    estado = request.GET.get('estado', '')
    if estado == 'activa':
        materias = materias.filter(activa=True)
    elif estado == 'inactiva':
        materias = materias.filter(activa=False)
    else:
        estado = ''

    cuantitativa = request.GET.get('cuantitativa', '')
    if cuantitativa == 'si':
        materias = materias.filter(es_cuantitativa=True)
    elif cuantitativa == 'no':
        materias = materias.filter(es_cuantitativa=False)
    else:
        cuantitativa = ''

    filtros_activos = {}
    if estado:
        filtros_activos['estado'] = estado
    if cuantitativa:
        filtros_activos['cuantitativa'] = cuantitativa

    campo, orden, direccion, columnas_orden = resolver_orden(
        request, ORDEN_MATERIAS, filtros_activos
    )
    if campo:
        materias = materias.order_by(*campo, 'id')

    contexto = {
        'materias': materias,
        'estado': estado,
        'cuantitativa': cuantitativa,
        'orden': orden,
        'direccion': direccion,
        'columnas_orden': columnas_orden,
        'hay_filtros': bool(filtros_activos),
    }
    return render(request, 'catalogo/lista_materias.html', contexto)


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def crear_materia(request):
    """Da de alta una disciplina nueva."""
    if request.method == 'POST':
        formulario = MateriaForm(request.POST)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, 'La disciplina se guardó correctamente.')
            return redirect('catalogo:lista_materias')
    else:
        formulario = MateriaForm()

    return render(request, 'catalogo/formulario_materia.html', {'formulario': formulario})


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def editar_materia(request, materia_id):
    """Modifica una disciplina que ya existe."""
    materia = get_object_or_404(Materia, id=materia_id)

    if request.method == 'POST':
        formulario = MateriaForm(request.POST, instance=materia)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, 'La disciplina se actualizó correctamente.')
            return redirect('catalogo:lista_materias')
    else:
        formulario = MateriaForm(instance=materia)

    contexto = {'formulario': formulario, 'materia': materia}
    return render(request, 'catalogo/formulario_materia.html', contexto)


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def lista_categorias(request):
    """Listado de asignaturas, con filtros de disciplina y estado."""
    categorias = Categoria.objects.select_related('materia').all()

    materia_id = request.GET.get('materia', '')
    if materia_id.isdigit():
        categorias = categorias.filter(materia_id=materia_id)
    else:
        materia_id = ''

    estado = request.GET.get('estado', '')
    if estado == 'activa':
        categorias = categorias.filter(activa=True)
    elif estado == 'inactiva':
        categorias = categorias.filter(activa=False)
    else:
        estado = ''

    filtros_activos = {}
    if materia_id:
        filtros_activos['materia'] = materia_id
    if estado:
        filtros_activos['estado'] = estado

    campo, orden, direccion, columnas_orden = resolver_orden(
        request, ORDEN_CATEGORIAS, filtros_activos
    )
    if campo:
        categorias = categorias.order_by(*campo, 'id')

    contexto = {
        'categorias': categorias,
        'materias': Materia.objects.all(),
        'materia_id': materia_id,
        'estado': estado,
        'orden': orden,
        'direccion': direccion,
        'columnas_orden': columnas_orden,
        'hay_filtros': bool(filtros_activos),
    }
    return render(request, 'catalogo/lista_categorias.html', contexto)


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def crear_categoria(request):
    """Da de alta una asignatura nueva dentro de una disciplina, junto con el
    tipo de preguntas que le corresponde a cada nivel."""
    if request.method == 'POST':
        formulario = CategoriaForm(request.POST)
        formulario_niveles = DescripcionesNivelForm(request.POST)
        if formulario.is_valid() and formulario_niveles.is_valid():
            categoria = formulario.save()
            formulario_niveles.guardar(categoria)
            messages.success(request, 'La asignatura se guardó correctamente.')
            return redirect('catalogo:lista_categorias')
    else:
        formulario = CategoriaForm()
        formulario_niveles = DescripcionesNivelForm()

    contexto = {'formulario': formulario, 'formulario_niveles': formulario_niveles}
    return render(request, 'catalogo/formulario_categoria.html', contexto)


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def editar_categoria(request, categoria_id):
    """Modifica una asignatura que ya existe, junto con el tipo de preguntas
    que le corresponde a cada nivel."""
    categoria = get_object_or_404(Categoria, id=categoria_id)

    if request.method == 'POST':
        formulario = CategoriaForm(request.POST, instance=categoria)
        formulario_niveles = DescripcionesNivelForm(request.POST, categoria=categoria)
        if formulario.is_valid() and formulario_niveles.is_valid():
            formulario.save()
            formulario_niveles.guardar(categoria)
            messages.success(request, 'La asignatura se actualizó correctamente.')
            return redirect('catalogo:lista_categorias')
    else:
        formulario = CategoriaForm(instance=categoria)
        formulario_niveles = DescripcionesNivelForm(categoria=categoria)

    contexto = {
        'formulario': formulario,
        'formulario_niveles': formulario_niveles,
        'categoria': categoria,
    }
    return render(request, 'catalogo/formulario_categoria.html', contexto)


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def lista_niveles(request):
    """Listado de niveles de dificultad."""
    niveles = Nivel.objects.all()

    campo, orden, direccion, columnas_orden = resolver_orden(request, ORDEN_NIVELES)
    if campo:
        niveles = niveles.order_by(*campo, 'id')

    contexto = {
        'niveles': niveles,
        'orden': orden,
        'direccion': direccion,
        'columnas_orden': columnas_orden,
    }
    return render(request, 'catalogo/lista_niveles.html', contexto)


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def crear_nivel(request):
    """Da de alta un nivel nuevo."""
    if request.method == 'POST':
        formulario = NivelForm(request.POST)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, 'El nivel se guardó correctamente.')
            return redirect('catalogo:lista_niveles')
    else:
        formulario = NivelForm()

    return render(request, 'catalogo/formulario_nivel.html', {'formulario': formulario})


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def editar_nivel(request, nivel_id):
    """Modifica un nivel que ya existe."""
    nivel = get_object_or_404(Nivel, id=nivel_id)

    if request.method == 'POST':
        formulario = NivelForm(request.POST, instance=nivel)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, 'El nivel se actualizó correctamente.')
            return redirect('catalogo:lista_niveles')
    else:
        formulario = NivelForm(instance=nivel)

    contexto = {'formulario': formulario, 'nivel': nivel}
    return render(request, 'catalogo/formulario_nivel.html', contexto)
