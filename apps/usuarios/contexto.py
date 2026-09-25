"""
Datos que necesita la barra superior en todas las pantallas.

Se registra como procesador de contexto en config/settings.py para no tener
que pasar la campanita desde cada una de las vistas del sistema.
"""

from .models import Notificacion


def notificaciones(request):
    """Las notificaciones recientes y cuantas quedan sin leer."""
    if not request.user.is_authenticated:
        return {}

    avisos = request.user.notificaciones.all()
    return {
        # Las que caben en el desplegable de la campanita; el resto se ven en
        # la pantalla de notificaciones.
        'notificaciones_recientes': avisos[:5],
        'notificaciones_sin_leer': avisos.filter(
            estado=Notificacion.Estado.ENVIADA
        ).count(),
    }
