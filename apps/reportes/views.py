"""
Tablero del profesor: resume el desempeno de los alumnos con filtros,
graficas y exportacion a CSV. El administrador tambien puede consultarlo.
"""

import csv
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import render

from apps.usuarios.models import Persona
from apps.usuarios.decoradores import roles_permitidos
from apps.catalogo.models import Materia
from apps.evaluaciones.models import IntentoEvaluacion, RespuestaAlumno

# El tablero lo pueden ver el profesor y el administrador.
ROLES_TABLERO = (Persona.Rol.PROFESOR, Persona.Rol.ADMINISTRADOR)


def _restar_anios(fecha, anios):
    """Resta anios a una fecha cuidando el caso del 29 de febrero."""
    try:
        return fecha.replace(year=fecha.year - anios)
    except ValueError:
        return fecha.replace(year=fecha.year - anios, day=28)


def _filtrar_intentos(request):
    """Arma el conjunto de intentos finalizados segun los filtros recibidos."""
    intentos = (
        IntentoEvaluacion.objects
        .filter(estado=IntentoEvaluacion.Estado.FINALIZADO)
        .select_related('alumno', 'evaluacion__grupo', 'evaluacion__materia')
    )

    # El profesor solo ve sus evaluaciones; el administrador las ve todas.
    if request.user.es_profesor:
        intentos = intentos.filter(evaluacion__profesor=request.user)

    grupo = request.GET.get('grupo')
    materia = request.GET.get('materia')
    sexo = request.GET.get('sexo')
    edad_min = request.GET.get('edad_min')
    edad_max = request.GET.get('edad_max')

    if grupo:
        intentos = intentos.filter(evaluacion__grupo_id=grupo)
    if materia:
        intentos = intentos.filter(evaluacion__materia_id=materia)
    if sexo:
        intentos = intentos.filter(alumno__sexo=sexo)

    hoy = date.today()
    if edad_min and edad_min.isdigit():
        # Nacidos hace al menos esa cantidad de anios.
        intentos = intentos.filter(alumno__fecha_nacimiento__lte=_restar_anios(hoy, int(edad_min)))
    if edad_max and edad_max.isdigit():
        # Nacidos hace a lo mucho esa cantidad de anios.
        intentos = intentos.filter(alumno__fecha_nacimiento__gt=_restar_anios(hoy, int(edad_max) + 1))

    return intentos


def _grupos_visibles(usuario):
    """Grupos que puede filtrar el usuario segun su rol."""
    from apps.evaluaciones.models import Grupo
    if usuario.es_profesor:
        return usuario.grupos_asignados.all()
    return Grupo.objects.all()


@login_required
@roles_permitidos(*ROLES_TABLERO)
def dashboard(request):
    """Muestra el resumen, las graficas y los filtros del tablero."""
    intentos = _filtrar_intentos(request)

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

    contexto = {
        'resumen': resumen,
        'datos_grupos': datos_grupos,
        'datos_materias': datos_materias,
        'datos_categorias': datos_categorias,
        # Opciones y valores actuales de los filtros.
        'grupos': _grupos_visibles(request.user),
        'materias': Materia.objects.all(),
        'sexos': Persona.Sexo.choices,
        'filtros': request.GET,
    }
    return render(request, 'reportes/dashboard.html', contexto)


@login_required
@roles_permitidos(*ROLES_TABLERO)
def exportar_csv(request):
    """Exporta los resultados filtrados en un archivo CSV."""
    intentos = _filtrar_intentos(request).order_by(
        'evaluacion__grupo__nombre', 'alumno__apellido'
    )

    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = 'attachment; filename="resultados.csv"'
    # El BOM ayuda a que Excel muestre bien los acentos.
    respuesta.write('﻿')

    escritor = csv.writer(respuesta)
    escritor.writerow(['Alumno', 'Grupo', 'Materia', 'Evaluacion', 'Calificacion', 'Fecha'])
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
