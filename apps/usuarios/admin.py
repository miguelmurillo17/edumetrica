"""Configuracion del panel de administracion para las personas."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Persona


@admin.register(Persona)
class PersonaAdmin(UserAdmin):
    """Adapta el admin de usuarios de Django a los campos de Persona."""

    # Columnas que se muestran en la lista de personas.
    list_display = ('correo', 'nombre', 'apellido', 'rol', 'is_active')
    list_filter = ('rol', 'is_active', 'sexo')
    search_fields = ('correo', 'nombre', 'apellido')
    ordering = ('apellido', 'nombre')

    # Como se agrupan los campos al editar una persona.
    fieldsets = (
        (None, {'fields': ('correo', 'password')}),
        ('Datos personales', {
            'fields': ('nombre', 'apellido', 'fecha_nacimiento', 'sexo')
        }),
        ('Rol y permisos', {
            'fields': ('rol', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
    )

    # Campos que aparecen al crear una persona nueva desde el admin.
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('correo', 'nombre', 'apellido', 'rol', 'password1', 'password2'),
        }),
    )
