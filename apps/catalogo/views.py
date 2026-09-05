"""Vistas para que el profesor administre el catalogo de preguntas."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from apps.usuarios.models import Persona
from apps.usuarios.decoradores import roles_permitidos

from .models import Pregunta
from .forms import PreguntaForm, OpcionRespuestaFormSet

# El profesor y el administrador pueden dar de alta preguntas.
ROLES_CATALOGO = (Persona.Rol.PROFESOR, Persona.Rol.ADMINISTRADOR)


@login_required
@roles_permitidos(*ROLES_CATALOGO)
def lista_preguntas(request):
    """Muestra el listado de preguntas registradas en el sistema."""
    preguntas = (
        Pregunta.objects
        .select_related('materia', 'categoria', 'nivel')
        .all()
    )
    return render(request, 'catalogo/lista_preguntas.html', {'preguntas': preguntas})


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
    return render(request, 'catalogo/crear_pregunta.html', contexto)
