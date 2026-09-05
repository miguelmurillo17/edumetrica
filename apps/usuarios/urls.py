"""Rutas de acceso al sistema."""

from django.urls import path
from django.contrib.auth import views as vistas_auth

from . import views
from .forms import FormularioInicioSesion

app_name = 'usuarios'

urlpatterns = [
    # Pantalla de inicio de sesion con nuestro formulario de correo.
    path(
        'entrar/',
        vistas_auth.LoginView.as_view(
            template_name='usuarios/inicio_sesion.html',
            authentication_form=FormularioInicioSesion,
            redirect_authenticated_user=True,
        ),
        name='inicio_sesion',
    ),
    # Cierre de sesion.
    path(
        'salir/',
        vistas_auth.LogoutView.as_view(),
        name='cerrar_sesion',
    ),
    # Punto de entrada que reparte a cada quien a su panel.
    path('', views.inicio, name='inicio'),
]
