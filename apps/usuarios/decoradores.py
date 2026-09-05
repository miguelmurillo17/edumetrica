"""Decoradores para restringir el acceso a las vistas segun el rol."""

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def roles_permitidos(*roles):
    """Deja pasar solo a las personas cuyo rol este en la lista indicada."""

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('usuarios:inicio_sesion')
            if request.user.is_superuser:
                # El superusuario entra a cualquier vista sin importar su rol.
                # Es coherente con el panel de Django, donde de todos modos
                # tiene control total del sistema.
                return vista(request, *args, **kwargs)
            if request.user.rol not in roles:
                # Si el rol no esta permitido se niega el acceso.
                raise PermissionDenied
            return vista(request, *args, **kwargs)
        return envoltura

    return decorador
