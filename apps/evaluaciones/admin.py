"""Configuracion del panel de administracion para las evaluaciones."""

from django.contrib import admin

from .models import Grupo, Evaluacion, IntentoEvaluacion, RespuestaAlumno


@admin.register(Grupo)
class GrupoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'institucion', 'activo')
    list_filter = ('activo', 'institucion')
    search_fields = ('nombre',)
    # Facilita asignar muchos alumnos y profesores al grupo.
    filter_horizontal = ('alumnos', 'profesores')


@admin.register(Evaluacion)
class EvaluacionAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'grupo', 'materia', 'estado', 'fecha_inicio', 'fecha_fin')
    list_filter = ('estado', 'materia', 'grupo')
    search_fields = ('titulo',)
    filter_horizontal = ('categorias', 'preguntas')


@admin.register(IntentoEvaluacion)
class IntentoEvaluacionAdmin(admin.ModelAdmin):
    list_display = ('alumno', 'evaluacion', 'estado', 'calificacion')
    list_filter = ('estado', 'evaluacion')
    search_fields = ('alumno__nombre', 'alumno__apellido')


@admin.register(RespuestaAlumno)
class RespuestaAlumnoAdmin(admin.ModelAdmin):
    list_display = ('intento', 'pregunta', 'es_correcta')
    list_filter = ('es_correcta',)
