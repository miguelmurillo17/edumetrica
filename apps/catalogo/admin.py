"""Configuracion del panel de administracion para los catalogos."""

from django.contrib import admin

from .models import (
    Institucion, Materia, Categoria, CategoriaNivel, Nivel, Pregunta,
    OpcionRespuesta, SolicitudGeneracion,
)
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


class CategoriaNivelInline(admin.TabularInline):
    """El tipo de preguntas que corresponde a cada nivel de esta asignatura."""
    model = CategoriaNivel
    extra = 0
    can_delete = False


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'materia', 'activa')
    list_filter = ('materia', 'activa')
    search_fields = ('nombre',)
    inlines = [CategoriaNivelInline]


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
    list_display = ('enunciado', 'materia', 'categoria', 'nivel', 'estado', 'origen', 'activa')
    list_filter = ('estado', 'origen', 'materia', 'categoria', 'nivel', 'activa')
    search_fields = ('enunciado',)
    inlines = [OpcionRespuestaInline]


@admin.register(SolicitudGeneracion)
class SolicitudGeneracionAdmin(admin.ModelAdmin):
    """Consulta de los lotes pedidos a la inteligencia artificial."""
    list_display = (
        'fecha', 'profesor', 'categoria', 'nivel', 'cantidad_pedida',
        'cantidad_recibida', 'cantidad_aprobada', 'cantidad_validada', 'estado',
    )
    list_filter = ('estado', 'materia', 'categoria', 'nivel')
    date_hierarchy = 'fecha'
    # El lote es un registro de lo que paso; no se edita a mano.
    readonly_fields = [campo.name for campo in SolicitudGeneracion._meta.fields]

    def has_add_permission(self, request):
        return False
