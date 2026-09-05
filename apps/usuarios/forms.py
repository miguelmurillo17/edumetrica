"""Formularios relacionados con el acceso de las personas al sistema."""

from django.contrib.auth.forms import AuthenticationForm


class FormularioInicioSesion(AuthenticationForm):
    """Formulario de acceso que pide el correo en lugar de un usuario."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El campo se sigue llamando username por dentro, pero al usuario
        # le mostramos que debe escribir su correo electronico.
        self.fields['username'].label = 'Correo electronico'
        self.fields['username'].widget.attrs.update({
            'placeholder': 'correo@ejemplo.com',
            'autofocus': True,
        })
        self.fields['password'].label = 'Contrasena'
        self.fields['password'].widget.attrs.update({
            'placeholder': 'Tu contrasena',
        })
