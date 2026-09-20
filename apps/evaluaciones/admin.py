"""Configuracion del panel de administracion para las evaluaciones."""

from django.contrib import admin

from .models import (
    Grupo,
    AsignacionDocente,
    Evaluacion,
    CategoriaEvaluacion,
    IntentoEvaluacion,
    RespuestaAlumno,
)


class AsignacionDocenteInline(admin.TabularInline):
    """Que asignatura imparte cada profesor en el grupo."""
    model = AsignacionDocente
    extra = 1


@admin.register(Grupo)
class GrupoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'institucion', 'activo')
    list_filter = ('activo', 'institucion')
    search_fields = ('nombre',)
    # Facilita asignar muchos alumnos al grupo; los profesores y su asignatura
    # se capturan en la tabla de asignaciones de abajo.
    filter_horizontal = ('alumnos',)
    inlines = [AsignacionDocenteInline]


class CategoriaEvaluacionInline(admin.TabularInline):
    """Tabla de categorias con su numero de preguntas dentro de la evaluacion."""
    model = CategoriaEvaluacion
    extra = 1


@admin.register(Evaluacion)
class EvaluacionAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'grupo', 'materia', 'estado', 'fecha_inicio', 'fecha_fin')
    list_filter = ('estado', 'materia', 'grupo')
    search_fields = ('titulo',)
    filter_horizontal = ('preguntas',)
    inlines = [CategoriaEvaluacionInline]


@admin.register(IntentoEvaluacion)
class IntentoEvaluacionAdmin(admin.ModelAdmin):
    list_display = ('alumno', 'evaluacion', 'estado', 'calificacion')
    list_filter = ('estado', 'evaluacion')
    search_fields = ('alumno__nombre', 'alumno__apellido')


@admin.register(RespuestaAlumno)
class RespuestaAlumnoAdmin(admin.ModelAdmin):
    list_display = ('intento', 'pregunta', 'es_correcta')
    list_filter = ('es_correcta',)
