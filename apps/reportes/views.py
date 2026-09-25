"""
Tablero del profesor: resume el desempeno de los alumnos con filtros,
graficas y exportacion a CSV. El administrador tambien puede consultarlo.
"""

import csv
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.usuarios.models import Persona
from apps.usuarios.decoradores import roles_permitidos
from apps.usuarios.listados import resolver_orden
from apps.catalogo.models import Materia
from apps.evaluaciones.models import (
    Evaluacion, Grupo, IntentoEvaluacion, RespuestaAlumno,
)
from apps.evaluaciones.servicios import actualizar_estados, construir_resultado

# El tablero lo pueden ver el profesor y el administrador.
ROLES_TABLERO = (Persona.Rol.PROFESOR, Persona.Rol.ADMINISTRADOR)

# Cuantas preguntas entran en el ranking de mas falladas del tablero.
TOPE_PREGUNTAS_DIFICILES = 10

# Columnas ordenables del listado de intentos.
ORDEN_INTENTOS = {
    'alumno': ('alumno__apellido', 'alumno__nombre'),
    'grupo': 'evaluacion__grupo__nombre',
    'evaluacion': 'evaluacion__titulo',
    'calificacion': 'calificacion',
    'fecha': 'fecha_fin',
}

# Columnas ordenables del detalle de un intento. A diferencia de ORDEN_INTENTOS
# el detalle no es un queryset sino una lista de diccionarios que arma
# construir_resultado, asi que aqui el valor es la llave del diccionario por
# la que se ordena en Python, no una ruta de ORM.
ORDEN_DETALLE_INTENTO = {
    'asignatura': 'categoria',
    'nivel': 'nivel_numero',
    'resultado': 'acerto',
}


def _restar_anios(fecha, anios):
    """Resta anios a una fecha cuidando el caso del 29 de febrero."""
    try:
        return fecha.replace(year=fecha.year - anios)
    except ValueError:
        return fecha.replace(year=fecha.year - anios, day=28)


def _poner_al_dia(request):
    """Cierra las evaluaciones vencidas antes de ponerse a contar.

    El tablero solo mira los intentos finalizados, asi que el alumno que cerro
    el navegador y dejo su intento abierto no aparece en ningun promedio hasta
    que alguien lo cierra. Se hace aqui, al entrar, para que los numeros del
    tablero no dependan de quien paso antes por el panel del alumno.
    """
    evaluaciones = Evaluacion.objects.all()
    if request.user.es_profesor:
        evaluaciones = evaluaciones.filter(profesor=request.user)
    actualizar_estados(evaluaciones)


def _intentos_visibles(request):
    """Intentos finalizados que el usuario puede consultar segun su rol.

    Es la base tanto del tablero (que ademas le encima los filtros del
    formulario) como del detalle de un intento (que solo necesita saber si
    ese usuario puede verlo, sin los filtros de la barra lateral).
    """
    intentos = (
        IntentoEvaluacion.objects
        .filter(estado=IntentoEvaluacion.Estado.FINALIZADO)
        .select_related('alumno', 'evaluacion__grupo', 'evaluacion__materia')
    )

    # El profesor solo ve sus evaluaciones; el administrador las ve todas.
    if request.user.es_profesor:
        intentos = intentos.filter(evaluacion__profesor=request.user)

    return intentos


def _a_calificacion(texto):
    """Convierte un texto a la calificacion que representa (0 a 100).

    Regresa None si no es un numero valido o si cae fuera de esa escala; el
    filtro simplemente lo ignora, igual que hace edad_min/edad_max con un
    texto que no es un numero. Se usa float y no isdigit() porque una
    calificacion puede traer decimales (70.5).
    """
    try:
        calificacion = float(texto)
    except (TypeError, ValueError):
        return None
    if calificacion < 0 or calificacion > 100:
        return None
    return calificacion


def _filtrar_intentos(request):
    """Arma el conjunto de intentos finalizados segun los filtros recibidos."""
    intentos = _intentos_visibles(request)

    grupo = request.GET.get('grupo')
    profesor = request.GET.get('profesor')
    materia = request.GET.get('materia')
    alumno = request.GET.get('alumno', '').strip()
    sexo = request.GET.get('sexo')
    edad_min = request.GET.get('edad_min')
    edad_max = request.GET.get('edad_max')
    calificacion_min = _a_calificacion(request.GET.get('calificacion_min'))
    calificacion_max = _a_calificacion(request.GET.get('calificacion_max'))

    if grupo:
        intentos = intentos.filter(evaluacion__grupo_id=grupo)
    if profesor:
        intentos = intentos.filter(evaluacion__profesor_id=profesor)
    if materia:
        intentos = intentos.filter(evaluacion__materia_id=materia)
    if alumno:
        intentos = intentos.filter(
            Q(alumno__nombre__icontains=alumno) | Q(alumno__apellido__icontains=alumno)
        )
    if sexo:
        intentos = intentos.filter(alumno__sexo=sexo)

    hoy = date.today()
    if edad_min and edad_min.isdigit():
        # Nacidos hace al menos esa cantidad de anios.
        intentos = intentos.filter(alumno__fecha_nacimiento__lte=_restar_anios(hoy, int(edad_min)))
    if edad_max and edad_max.isdigit():
        # Nacidos hace a lo mucho esa cantidad de anios.
        intentos = intentos.filter(alumno__fecha_nacimiento__gt=_restar_anios(hoy, int(edad_max) + 1))

    if calificacion_min is not None:
        intentos = intentos.filter(calificacion__gte=calificacion_min)
    if calificacion_max is not None:
        intentos = intentos.filter(calificacion__lte=calificacion_max)

    return intentos


def _grupos_visibles(usuario):
    """Grupos que puede filtrar el usuario segun su rol."""
    if usuario.es_profesor:
        # Un profesor puede impartir varias asignaturas en el mismo grupo, y
        # cada una es un renglon de AsignacionDocente: sin distinct() el
        # grupo saldria repetido una vez por asignatura.
        return usuario.grupos_asignados.distinct()
    return Grupo.objects.all()


def _profesores_visibles(usuario):
    """Profesores por los que se puede filtrar, igual que _grupos_visibles:
    el profesor solo se ve a si mismo (ya esta limitado a sus evaluaciones),
    el administrador o el superusuario ven a todos. Se pregunta al reves de
    "es_administrador" porque el superusuario entra por roles_permitidos sin
    que su rol sea administrador.
    """
    if usuario.es_profesor:
        return Persona.objects.filter(id=usuario.id)
    return Persona.objects.filter(rol=Persona.Rol.PROFESOR).order_by('apellido', 'nombre')


def _resumen_filtros(request, intentos):
    """Arma la lista de filtros activos y, si el de alumno esta en uso, con
    quienes coincidio; para el dialogo "Ver filtros aplicados".

    Se resuelve aqui y no en el template porque un id de grupo o de profesor
    no dice nada por si solo (hay que ir a buscar su nombre), y los alumnos
    que coinciden salen de cruzar el texto escrito con quienes de verdad
    quedaron en el conjunto ya filtrado por todos los criterios juntos, no
    solo por el texto.
    """
    filtros = request.GET
    resumen = []

    grupo_id = filtros.get('grupo')
    if grupo_id:
        grupo = Grupo.objects.filter(id=grupo_id).first()
        if grupo:
            resumen.append(('Grupo', grupo.nombre))

    profesor_id = filtros.get('profesor')
    if profesor_id:
        profesor = Persona.objects.filter(id=profesor_id).first()
        if profesor:
            resumen.append(('Profesor', profesor.nombre_completo))

    materia_id = filtros.get('materia')
    if materia_id:
        materia = Materia.objects.filter(id=materia_id).first()
        if materia:
            resumen.append(('Disciplina', materia.nombre))

    alumno_texto = filtros.get('alumno', '').strip()
    if alumno_texto:
        resumen.append(('Alumno', alumno_texto))

    sexo = filtros.get('sexo')
    if sexo:
        resumen.append(('Sexo', dict(Persona.Sexo.choices).get(sexo, sexo)))

    edad_min = filtros.get('edad_min')
    if edad_min and edad_min.isdigit():
        resumen.append(('Edad mínima', edad_min))

    edad_max = filtros.get('edad_max')
    if edad_max and edad_max.isdigit():
        resumen.append(('Edad máxima', edad_max))

    calificacion_min = _a_calificacion(filtros.get('calificacion_min'))
    if calificacion_min is not None:
        resumen.append(('Calificación mínima', calificacion_min))

    calificacion_max = _a_calificacion(filtros.get('calificacion_max'))
    if calificacion_max is not None:
        resumen.append(('Calificación máxima', calificacion_max))

    alumnos_coincidentes = []
    if alumno_texto:
        alumnos_coincidentes = list(
            Persona.objects
            .filter(id__in=intentos.values_list('alumno_id', flat=True))
            .order_by('apellido', 'nombre')
        )

    return resumen, alumnos_coincidentes


@login_required
@roles_permitidos(*ROLES_TABLERO)
def dashboard(request):
    """Muestra el resumen, las graficas y los filtros del tablero."""
    _poner_al_dia(request)

    intentos = _filtrar_intentos(request)
    resumen_filtros, alumnos_coincidentes = _resumen_filtros(request, intentos)

    resumen = intentos.aggregate(promedio=Avg('calificacion'), total=Count('id'))

    # Promedio de calificacion por grupo.
    por_grupo = (
        intentos.values('evaluacion__grupo__nombre')
        .annotate(promedio=Avg('calificacion'))
        .order_by('evaluacion__grupo__nombre')
    )
    datos_grupos = {
        'etiquetas': [fila['evaluacion__grupo__nombre'] for fila in por_grupo],
        'valores': [round(float(fila['promedio'] or 0), 2) for fila in por_grupo],
    }

    # Promedio de calificacion por materia.
    por_materia = (
        intentos.values('evaluacion__materia__nombre')
        .annotate(promedio=Avg('calificacion'))
        .order_by('evaluacion__materia__nombre')
    )
    datos_materias = {
        'etiquetas': [fila['evaluacion__materia__nombre'] for fila in por_materia],
        'valores': [round(float(fila['promedio'] or 0), 2) for fila in por_materia],
    }

    # Porcentaje de aciertos por categoria, mirando cada respuesta.
    respuestas = RespuestaAlumno.objects.filter(intento__in=intentos)
    por_categoria = (
        respuestas.values('pregunta__categoria__nombre')
        .annotate(total=Count('id'), aciertos=Count('id', filter=Q(es_correcta=True)))
        .order_by('pregunta__categoria__nombre')
    )
    datos_categorias = {
        'etiquetas': [fila['pregunta__categoria__nombre'] for fila in por_categoria],
        'valores': [
            round(fila['aciertos'] / fila['total'] * 100, 2) if fila['total'] else 0
            for fila in por_categoria
        ],
    }

    # Porcentaje de aciertos por nivel de dificultad. Muestra si el grupo
    # domina lo basico pero se cae en lo avanzado, o al reves.
    por_nivel = (
        respuestas.values('pregunta__nivel__numero', 'pregunta__nivel__nombre')
        .annotate(total=Count('id'), aciertos=Count('id', filter=Q(es_correcta=True)))
        .order_by('pregunta__nivel__numero')
    )
    datos_niveles = {
        'etiquetas': [fila['pregunta__nivel__nombre'] for fila in por_nivel],
        'valores': [
            round(fila['aciertos'] / fila['total'] * 100, 2) if fila['total'] else 0
            for fila in por_nivel
        ],
    }

    # Promedio por evaluacion en orden cronologico, para ver si el grupo
    # mejora evaluacion tras evaluacion y no solo su foto actual.
    por_evaluacion = (
        intentos.values('evaluacion_id', 'evaluacion__fecha_inicio')
        .annotate(promedio=Avg('calificacion'))
        .order_by('evaluacion__fecha_inicio')
    )
    datos_tendencia = {
        'etiquetas': [
            timezone.localtime(fila['evaluacion__fecha_inicio']).strftime('%d/%m/%Y')
            for fila in por_evaluacion
        ],
        'valores': [round(float(fila['promedio'] or 0), 2) for fila in por_evaluacion],
    }

    # Ranking de las preguntas con mas error: es el dato que de verdad le dice
    # al profesor que repasar, mas alla del promedio general del grupo.
    por_pregunta = (
        respuestas.values(
            'pregunta_id',
            'pregunta__enunciado',
            'pregunta__categoria__nombre',
            'pregunta__nivel__nombre',
        )
        .annotate(total=Count('id'), aciertos=Count('id', filter=Q(es_correcta=True)))
    )
    preguntas_dificiles = sorted(
        (
            {
                'enunciado': fila['pregunta__enunciado'],
                'categoria': fila['pregunta__categoria__nombre'],
                'nivel': fila['pregunta__nivel__nombre'],
                'total': fila['total'],
                'porcentaje_error': round(
                    (fila['total'] - fila['aciertos']) / fila['total'] * 100, 2
                ) if fila['total'] else 0,
            }
            for fila in por_pregunta
        ),
        key=lambda fila: fila['porcentaje_error'],
        reverse=True,
    )[:TOPE_PREGUNTAS_DIFICILES]

    # Participacion: cuantos alumnos distintos ya presentaron contra cuantos
    # hay en los grupos que el filtro deja ver. "Evaluaciones presentadas"
    # cuenta intentos, no dice nada de que tan completa fue la participacion.
    grupos_visibles = _grupos_visibles(request.user)
    grupo_filtro = request.GET.get('grupo')
    grupos_en_alcance = (
        grupos_visibles.filter(id=grupo_filtro) if grupo_filtro else grupos_visibles
    )
    total_alumnos = Persona.objects.filter(grupos__in=grupos_en_alcance).distinct().count()
    alumnos_evaluados = intentos.values('alumno_id').distinct().count()

    contexto = {
        'resumen': resumen,
        'alumnos_evaluados': alumnos_evaluados,
        'total_alumnos': total_alumnos,
        'datos_grupos': datos_grupos,
        'datos_materias': datos_materias,
        'datos_categorias': datos_categorias,
        'datos_niveles': datos_niveles,
        'datos_tendencia': datos_tendencia,
        'preguntas_dificiles': preguntas_dificiles,
        # Opciones y valores actuales de los filtros.
        'grupos': grupos_visibles,
        'profesores': _profesores_visibles(request.user),
        'materias': Materia.objects.all(),
        'sexos': Persona.Sexo.choices,
        'filtros': request.GET,
        'resumen_filtros': resumen_filtros,
        'alumnos_coincidentes': alumnos_coincidentes,
    }
    return render(request, 'reportes/dashboard.html', contexto)


@login_required
@roles_permitidos(*ROLES_TABLERO)
def exportar_csv(request):
    """Exporta los resultados filtrados en un archivo CSV."""
    _poner_al_dia(request)

    intentos = _filtrar_intentos(request).order_by(
        'evaluacion__grupo__nombre', 'alumno__apellido'
    )

    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = 'attachment; filename="resultados.csv"'
    # El BOM ayuda a que Excel muestre bien los acentos.
    respuesta.write('﻿')

    escritor = csv.writer(respuesta)
    escritor.writerow(['Alumno', 'Grupo', 'Disciplina', 'Evaluación', 'Calificación', 'Fecha'])
    for intento in intentos:
        escritor.writerow([
            intento.alumno.nombre_completo,
            intento.evaluacion.grupo.nombre,
            intento.evaluacion.materia.nombre,
            intento.evaluacion.titulo,
            intento.calificacion,
            intento.fecha_fin.strftime('%d/%m/%Y %H:%M') if intento.fecha_fin else '',
        ])

    return respuesta


@login_required
@roles_permitidos(*ROLES_TABLERO)
def lista_intentos(request):
    """Listado de intentos finalizados, con los mismos filtros del tablero.

    Es la puerta de entrada para explorar el detalle de un alumno en
    particular: el tablero se queda en promedios y graficas, aqui se ve
    renglon por renglon.
    """
    _poner_al_dia(request)

    intentos = _filtrar_intentos(request).select_related(
        'alumno', 'evaluacion__grupo', 'evaluacion__materia'
    )
    resumen_filtros, alumnos_coincidentes = _resumen_filtros(request, intentos)

    campo, orden, direccion, columnas_orden = resolver_orden(
        request, ORDEN_INTENTOS, request.GET
    )
    intentos = intentos.order_by(*(campo or ('-fecha_fin',)), 'id')

    contexto = {
        'intentos': intentos,
        'orden': orden,
        'direccion': direccion,
        'columnas_orden': columnas_orden,
        'grupos': _grupos_visibles(request.user),
        'profesores': _profesores_visibles(request.user),
        'materias': Materia.objects.all(),
        'sexos': Persona.Sexo.choices,
        'filtros': request.GET,
        'resumen_filtros': resumen_filtros,
        'alumnos_coincidentes': alumnos_coincidentes,
    }
    return render(request, 'reportes/lista_intentos.html', contexto)


@login_required
@roles_permitidos(*ROLES_TABLERO)
def detalle_intento(request, intento_id):
    """Detalle pregunta por pregunta de un intento ya finalizado.

    Reusa construir_resultado, la misma funcion que arma el resultado que ve
    el alumno, para no mantener dos formas distintas de decidir que conto
    como acierto. El detalle es una lista de diccionarios, no un queryset, asi
    que el orden se aplica a mano en Python en vez de con order_by.
    """
    intento = get_object_or_404(_intentos_visibles(request), id=intento_id)
    resultado = construir_resultado(intento)

    campo, orden, direccion, columnas_orden = resolver_orden(
        request, ORDEN_DETALLE_INTENTO
    )
    if campo:
        clave = ORDEN_DETALLE_INTENTO[orden]
        resultado['detalle'] = sorted(
            resultado['detalle'],
            key=lambda fila: fila[clave],
            reverse=(direccion == 'desc'),
        )

    contexto = {
        'intento': intento,
        'resultado': resultado,
        'orden': orden,
        'direccion': direccion,
        'columnas_orden': columnas_orden,
    }
    return render(request, 'reportes/detalle_intento.html', contexto)
