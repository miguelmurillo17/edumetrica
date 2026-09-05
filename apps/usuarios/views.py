"""Vistas de acceso y de reparto segun el rol de la persona."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required
def inicio(request):
    """Manda a cada persona a su panel segun el rol que tenga."""
    persona = request.user

    if persona.es_administrador:
        # El administrador trabaja desde el panel propio de Django.
        return redirect('/admin/')
    if persona.es_profesor:
        return redirect('evaluaciones:panel_profesor')
    # Por defecto se asume que es alumno.
    return redirect('evaluaciones:panel_alumno')
