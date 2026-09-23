"""Rutas de acceso al sistema."""

from django.urls import path, reverse_lazy
from django.contrib.auth import views as vistas_auth

from . import views
from .forms import FormularioInicioSesion, FormularioCorreoRestablecer, FormularioNuevaContrasena

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
    # Restablecimiento de la contrasena en cuatro pasos: se pide el correo,
    # se avisa que ya se mando, se captura la contrasena nueva y se confirma.
    path(
        'restablecer/',
        vistas_auth.PasswordResetView.as_view(
            template_name='usuarios/restablecer_solicitar.html',
            email_template_name='usuarios/correo_restablecer.txt',
            subject_template_name='usuarios/correo_restablecer_asunto.txt',
            form_class=FormularioCorreoRestablecer,
            success_url=reverse_lazy('usuarios:restablecer_enviado'),
        ),
        name='restablecer',
    ),
    path(
        'restablecer/enviado/',
        vistas_auth.PasswordResetDoneView.as_view(
            template_name='usuarios/restablecer_enviado.html',
        ),
        name='restablecer_enviado',
    ),
    path(
        'restablecer/<uidb64>/<token>/',
        vistas_auth.PasswordResetConfirmView.as_view(
            template_name='usuarios/restablecer_nueva.html',
            form_class=FormularioNuevaContrasena,
            success_url=reverse_lazy('usuarios:restablecer_listo'),
        ),
        name='restablecer_confirmar',
    ),
    path(
        'restablecer/listo/',
        vistas_auth.PasswordResetCompleteView.as_view(
            template_name='usuarios/restablecer_listo.html',
        ),
        name='restablecer_listo',
    ),

    # Punto de entrada que reparte a cada quien a su panel.
    path('', views.inicio, name='inicio'),

    # Panel del administrador y alta/edicion de personas.
    path('administracion/', views.panel_administrador, name='panel_administrador'),
    path('personas/', views.lista_personas, name='lista_personas'),
    path('personas/nueva/', views.crear_persona, name='crear_persona'),
    path('personas/<int:persona_id>/editar/', views.editar_persona, name='editar_persona'),
]
