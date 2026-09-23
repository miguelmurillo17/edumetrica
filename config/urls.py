"""
Rutas principales del proyecto Edumetrica.

Aqui se incluyen el panel de administracion, las rutas de acceso al sistema
y los paneles de profesor y alumno de cada aplicacion.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# El admin de Django trae su propio nombre por omision; se cambia aqui para
# que diga el nombre del sistema en vez de "Administracion de Django".
admin.site.site_header = 'Administración Edumétrica'
admin.site.site_title = 'Administración Edumétrica'
admin.site.index_title = 'Administración Edumétrica'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.usuarios.urls')),
    path('', include('apps.catalogo.urls')),
    path('', include('apps.evaluaciones.urls')),
    path('', include('apps.reportes.urls')),
]

# Durante el desarrollo Django sirve las imagenes que suben los usuarios.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
