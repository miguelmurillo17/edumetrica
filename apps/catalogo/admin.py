"""Configuracion del panel de administracion para los catalogos."""

from django.contrib import admin

from .models import Institucion, Materia, Categoria, Nivel, Pregunta, OpcionRespuesta
from .forms import OpcionRespuestaForm, BaseOpcionesFormSet, NUMERO_OPCIONES


@admin.register(Institucion)
class InstitucionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono')
    search_fields = ('nombre',)


@admin.register(Materia)
class MateriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre',)


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'materia', 'activa')
    list_filter = ('materia', 'activa')
    search_fields = ('nombre',)


@admin.register(Nivel)
class NivelAdmin(admin.ModelAdmin):
    list_display = ('numero', 'nombre')
    ordering = ('numero',)


class OpcionRespuestaInline(admin.TabularInline):
    """Permite editar las opciones de respuesta dentro de la misma pregunta."""
    model = OpcionRespuesta
    form = OpcionRespuestaForm
    # Se usa el mismo formset que el formulario del profesor para que la regla
    # de las cuatro opciones con una sola correcta valga tambien aqui.
    formset = BaseOpcionesFormSet
    extra = NUMERO_OPCIONES
    max_num = NUMERO_OPCIONES


@admin.register(Pregunta)
class PreguntaAdmin(admin.ModelAdmin):
    list_display = ('enunciado', 'materia', 'categoria', 'nivel', 'activa')
    list_filter = ('materia', 'categoria', 'nivel', 'activa')
    search_fields = ('enunciado',)
    inlines = [OpcionRespuestaInline]
