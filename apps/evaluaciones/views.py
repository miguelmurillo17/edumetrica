"""Vistas de los paneles de profesor y alumno, y de las evaluaciones."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from apps.usuarios.models import Persona
from apps.usuarios.decoradores import roles_permitidos
from apps.catalogo.models import Pregunta

from .models import Grupo, Evaluacion, IntentoEvaluacion
from .forms import (
    EvaluacionForm, CategoriaEvaluacionFormSet, GrupoForm, AsignacionDocenteFormSet,
)


@login_required
def panel_profesor(request):
    """Pantalla principal del profesor con sus evaluaciones y accesos."""
    return render(request, 'evaluaciones/panel_profesor.html')


@login_required
def panel_alumno(request):
    """Muestra al alumno sus evaluaciones y la situacion de cada una."""
    alumno = request.user
    evaluaciones = (
        Evaluacion.objects
        .filter(grupo__alumnos=alumno)
        .select_related('grupo', 'materia')
        .order_by('-fecha_inicio')
    )

    # Intentos del alumno indexados por evaluacion para saber cuales ya presento.
    intentos = {
        intento.evaluacion_id: intento
        for intento in IntentoEvaluacion.objects.filter(alumno=alumno)
    }

    ahora = timezone.now()
    lista = []
    for evaluacion in evaluaciones:
        intento = intentos.get(evaluacion.id)
        if intento and intento.estado == IntentoEvaluacion.Estado.FINALIZADO:
            situacion = 'finalizada'
        elif evaluacion.esta_disponible():
            situacion = 'disponible'
        elif evaluacion.fecha_inicio > ahora:
            situacion = 'proxima'
        else:
            situacion = 'cerrada'
        lista.append({'evaluacion': evaluacion, 'situacion': situacion, 'intento': intento})

    return render(request, 'evaluaciones/panel_alumno.html', {'evaluaciones': lista})


@login_required
def presentar_evaluacion(request, evaluacion_id):
    """Monta la aplicacion de Vue para que el alumno presente la evaluacion."""
    evaluacion = get_object_or_404(Evaluacion, id=evaluacion_id)
    return render(request, 'evaluaciones/presentar_evaluacion.html', {'evaluacion': evaluacion})


@login_required
@roles_permitidos(Persona.Rol.PROFESOR, Persona.Rol.ADMINISTRADOR)
def lista_grupos(request):
    """Muestra los grupos con sus alumnos y que asignatura imparte cada profesor."""
    grupos = (
        Grupo.objects
        .prefetch_related('alumnos', 'asignaciones__profesor', 'asignaciones__categoria')
        .select_related('institucion')
    )

    # El profesor solo ve los grupos que le asignaron; el administrador todos.
    # distinct() porque el through repite el grupo por cada asignatura.
    if request.user.es_profesor:
        grupos = grupos.filter(profesores=request.user).distinct()

    # Filtro por estado; un valor inventado en la URL se ignora.
    estado = request.GET.get('estado', '')
    if estado == 'activo':
        grupos = grupos.filter(activo=True)
    elif estado == 'inactivo':
        grupos = grupos.filter(activo=False)
    else:
        estado = ''

    # Se agrupan las asignaciones por profesor para mostrar "Fulano - Asig1, Asig2".
    grupos = list(grupos)
    for grupo in grupos:
        docentes = {}
        for asignacion in grupo.asignaciones.all():
            ficha = docentes.setdefault(
                asignacion.profesor_id,
                {'profesor': asignacion.profesor, 'asignaturas': []},
            )
            ficha['asignaturas'].append(asignacion.categoria.nombre)
        grupo.docentes = list(docentes.values())

    contexto = {
        'grupos': grupos,
        'estado': estado,
        'hay_filtros': bool(estado),
    }
    return render(request, 'evaluaciones/lista_grupos.html', contexto)


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def crear_grupo(request):
    """Da de alta un grupo con sus alumnos y su plantilla docente."""
    if request.method == 'POST':
        formulario = GrupoForm(request.POST)
        asignaciones = AsignacionDocenteFormSet(request.POST)

        if formulario.is_valid() and asignaciones.is_valid():
            grupo = formulario.save()
            asignaciones.instance = grupo
            asignaciones.save()

            messages.success(request, 'El grupo se guardó correctamente.')
            return redirect('evaluaciones:lista_grupos')
    else:
        formulario = GrupoForm()
        asignaciones = AsignacionDocenteFormSet()

    contexto = {'formulario': formulario, 'asignaciones': asignaciones}
    return render(request, 'evaluaciones/formulario_grupo.html', contexto)


@login_required
@roles_permitidos(Persona.Rol.ADMINISTRADOR)
def editar_grupo(request, grupo_id):
    """Modifica un grupo que ya existe."""
    grupo = get_object_or_404(Grupo, id=grupo_id)

    if request.method == 'POST':
        formulario = GrupoForm(request.POST, instance=grupo)
        asignaciones = AsignacionDocenteFormSet(request.POST, instance=grupo)

        if formulario.is_valid() and asignaciones.is_valid():
            formulario.save()
            asignaciones.save()

            messages.success(request, 'El grupo se actualizó correctamente.')
            return redirect('evaluaciones:lista_grupos')
    else:
        formulario = GrupoForm(instance=grupo)
        asignaciones = AsignacionDocenteFormSet(instance=grupo)

    contexto = {'formulario': formulario, 'asignaciones': asignaciones, 'grupo': grupo}
    return render(request, 'evaluaciones/formulario_grupo.html', contexto)


@login_required
@roles_permitidos(Persona.Rol.PROFESOR)
def lista_evaluaciones(request):
    """Muestra las evaluaciones que ha programado el profesor."""
    evaluaciones = (
        Evaluacion.objects
        .filter(profesor=request.user)
        .select_related('grupo', 'materia')
    )
    return render(request, 'evaluaciones/lista_evaluaciones.html', {'evaluaciones': evaluaciones})


@login_required
@roles_permitidos(Persona.Rol.PROFESOR)
def detalle_evaluacion(request, evaluacion_id):
    """Muestra al profesor el avance de cada alumno en una evaluacion."""
    evaluacion = get_object_or_404(Evaluacion, id=evaluacion_id, profesor=request.user)

    # Intentos indexados por alumno para cruzarlos con la lista del grupo.
    intentos = {
        intento.alumno_id: intento
        for intento in evaluacion.intentos.select_related('alumno')
    }

    filas = []
    for alumno in evaluacion.grupo.alumnos.all():
        intento = intentos.get(alumno.id)
        if intento is None:
            situacion = 'no_iniciado'
        elif intento.estado == IntentoEvaluacion.Estado.EN_CURSO:
            situacion = 'en_curso'
        else:
            situacion = 'finalizado'
        filas.append({'alumno': alumno, 'intento': intento, 'situacion': situacion})

    return render(request, 'evaluaciones/detalle_evaluacion.html', {
        'evaluacion': evaluacion,
        'filas': filas,
    })


@login_required
@roles_permitidos(Persona.Rol.PROFESOR)
def finalizar_evaluacion(request, evaluacion_id):
    """Finaliza la evaluacion y cierra los intentos que sigan en curso."""
    evaluacion = get_object_or_404(Evaluacion, id=evaluacion_id, profesor=request.user)

    if request.method == 'POST' and evaluacion.estado != Evaluacion.Estado.FINALIZADA:
        ahora = timezone.now()
        # Si todavia no llegaba la hora de fin, fue una finalizacion anticipada.
        evaluacion.estado = Evaluacion.Estado.FINALIZADA
        evaluacion.finalizada_anticipadamente = ahora < evaluacion.fecha_fin
        evaluacion.save()

        # Cada alumno que seguia presentando se cierra con lo que llevaba.
        for intento in evaluacion.intentos.filter(estado=IntentoEvaluacion.Estado.EN_CURSO):
            intento.estado = IntentoEvaluacion.Estado.FINALIZADO
            intento.fecha_fin = ahora
            intento.calificacion = intento.calcular_calificacion()
            intento.save()

        messages.success(
            request,
            'La evaluación se finalizó. Los alumnos en curso verán su resultado.',
        )

    return redirect('evaluaciones:detalle_evaluacion', evaluacion_id=evaluacion.id)


@login_required
@roles_permitidos(Persona.Rol.PROFESOR)
def crear_evaluacion(request):
    """Programa una evaluacion y arma el conjunto de preguntas al azar."""
    if request.method == 'POST':
        formulario = EvaluacionForm(request.POST, usuario=request.user)
        filas = CategoriaEvaluacionFormSet(request.POST)
        # Se fija antes de validar/renderizar: limita el desplegable de
        # asignaturas a las que imparte el profesor (ver add_fields del formset).
        filas.usuario = request.user

        # La materia y el grupo viven en el otro formulario, pero la tabla los
        # necesita para revisar que las asignaturas capturadas le correspondan
        # al profesor en ese grupo.
        formulario_valido = formulario.is_valid()
        filas.materia = formulario.cleaned_data.get('materia') if formulario_valido else None
        filas.grupo = formulario.cleaned_data.get('grupo') if formulario_valido else None

        if formulario_valido and filas.is_valid():
            evaluacion = formulario.save(commit=False)
            evaluacion.profesor = request.user
            evaluacion.save()

            # Guarda los renglones de categorias con su numero de preguntas.
            filas.instance = evaluacion
            filas.save()

            # Por cada categoria se toman al azar las preguntas que pidio.
            preguntas = []
            for fila in evaluacion.categorias_elegidas.all():
                preguntas += list(
                    Pregunta.objects
                    .utilizables()
                    .filter(categoria=fila.categoria)
                    .order_by('?')[:fila.numero_preguntas]
                )
            evaluacion.preguntas.set(preguntas)

            # El total de la evaluacion es la suma de todos los renglones.
            evaluacion.numero_preguntas = len(preguntas)
            evaluacion.save(update_fields=['numero_preguntas'])

            messages.success(request, 'La evaluación se programó correctamente.')
            return redirect('evaluaciones:lista_evaluaciones')
    else:
        formulario = EvaluacionForm(usuario=request.user)
        filas = CategoriaEvaluacionFormSet()
        filas.usuario = request.user

    contexto = {'formulario': formulario, 'filas': filas}
    return render(request, 'evaluaciones/crear_evaluacion.html', contexto)
