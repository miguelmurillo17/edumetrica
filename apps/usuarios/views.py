"""Vistas de acceso y de reparto segun el rol de la persona."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone

from .decoradores import roles_permitidos
from .forms import PersonaCreacionForm, PersonaEdicionForm
from .listados import resolver_orden
from .models import Notificacion, Persona

# Columnas por las que se puede ordenar el listado de personas.
ORDEN_PERSONAS = {
    'nombre': ('apellido', 'nombre'),
    'correo': 'correo',
    'rol': 'rol',
    'estado': 'is_active',
}


@login_required
def inicio(request):
    """Manda a cada persona a su panel segun el rol que tenga."""
    persona = request.user

    if persona.is_superuser:
        # El superusuario puede trabajar desde cualquiera de los tres paneles,
        # asi que en lugar de mandarlo a uno se le muestran los accesos para
        # que elija. Los demas si van directo al que les toca.
        return render(request, 'usuarios/paneles.html')

    if persona.es_administrador:
        return redirect('usuarios:panel_administrador')
    if persona.es_profesor:
        return redirect('evaluaciones:panel_profesor')
    # Por defecto se asume que es alumno.
    return redirect('evaluaciones:panel_alumno')


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def panel_administrador(request):
    """Pantalla principal del administrador con los accesos a cada catalogo."""
    return render(request, 'usuarios/panel_administrador.html')


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def lista_personas(request):
    """Listado de personas, con filtros de rol y estado, y orden por columna."""
    personas = Persona.objects.all()

    rol = request.GET.get('rol', '')
    if rol in Persona.Rol.values:
        personas = personas.filter(rol=rol)
    else:
        rol = ''

    estado = request.GET.get('estado', '')
    if estado == 'activa':
        personas = personas.filter(is_active=True)
    elif estado == 'inactiva':
        personas = personas.filter(is_active=False)
    else:
        estado = ''

    filtros_activos = {}
    if rol:
        filtros_activos['rol'] = rol
    if estado:
        filtros_activos['estado'] = estado

    campo, orden, direccion, columnas_orden = resolver_orden(
        request, ORDEN_PERSONAS, filtros_activos
    )
    if campo:
        personas = personas.order_by(*campo, 'id')

    contexto = {
        'personas': personas,
        'roles': Persona.Rol.choices,
        'rol': rol,
        'estado': estado,
        'orden': orden,
        'direccion': direccion,
        'columnas_orden': columnas_orden,
        'hay_filtros': bool(filtros_activos),
    }
    return render(request, 'usuarios/lista_personas.html', contexto)


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def crear_persona(request):
    """Da de alta una persona nueva (administrador, profesor o alumno)."""
    if request.method == 'POST':
        formulario = PersonaCreacionForm(request.POST)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, 'La persona se dio de alta correctamente.')
            return redirect('usuarios:lista_personas')
    else:
        formulario = PersonaCreacionForm()

    return render(request, 'usuarios/formulario_persona.html', {'formulario': formulario})


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def editar_persona(request, persona_id):
    """Modifica los datos de una persona que ya existe."""
    persona = get_object_or_404(Persona, id=persona_id)

    if request.method == 'POST':
        formulario = PersonaEdicionForm(request.POST, instance=persona)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, 'La persona se actualizo correctamente.')
            return redirect('usuarios:lista_personas')
    else:
        formulario = PersonaEdicionForm(instance=persona)

    contexto = {'formulario': formulario, 'persona': persona}
    return render(request, 'usuarios/formulario_persona.html', contexto)


@login_required
def lista_notificaciones(request):
    """Todas las notificaciones de la persona, la mas reciente primero."""
    return render(request, 'usuarios/lista_notificaciones.html', {
        'notificaciones': request.user.notificaciones.all(),
    })


@login_required
def abrir_notificacion(request, notificacion_id):
    """Da la notificacion por leida y lleva a donde apunta."""
    aviso = get_object_or_404(
        Notificacion, id=notificacion_id, persona=request.user
    )
    aviso.marcar_leida()

    # La direccion la escribe el sistema, pero se revisa de todos modos: una
    # ruta propia empieza con una sola diagonal, y asi la campanita no puede
    # acabar mandando a un sitio de fuera si alguien edita el aviso a mano.
    propia = aviso.url.startswith('/') and not aviso.url.startswith('//')
    return redirect(aviso.url if propia else 'usuarios:notificaciones')


@login_required
def marcar_notificaciones_leidas(request):
    """Da por leidas de una vez todas las que quedaban pendientes."""
    if request.method == 'POST':
        request.user.notificaciones.filter(
            estado=Notificacion.Estado.ENVIADA
        ).update(
            estado=Notificacion.Estado.LEIDA, fecha_lectura=timezone.now()
        )

    return redirect('usuarios:notificaciones')
