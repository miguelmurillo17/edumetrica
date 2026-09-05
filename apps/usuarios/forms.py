"""Formularios relacionados con el acceso de las personas al sistema."""

from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm


class FormularioInicioSesion(AuthenticationForm):
    """Formulario de acceso que pide el correo en lugar de un usuario."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El campo se sigue llamando username por dentro, pero al usuario
        # le mostramos que debe escribir su correo electronico.
        self.fields['username'].label = 'Correo electrónico'
        self.fields['username'].widget.attrs.update({
            'placeholder': 'correo@ejemplo.com',
            'autofocus': True,
        })
        self.fields['password'].label = 'Contraseña'
        self.fields['password'].widget.attrs.update({
            'placeholder': 'Tu contraseña',
        })


class FormularioCorreoRestablecer(PasswordResetForm):
    """Pide el correo de la persona que olvido su contrasena."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].label = 'Correo electrónico'
        self.fields['email'].widget.attrs.update({
            'placeholder': 'correo@ejemplo.com',
            'autofocus': True,
        })


class FormularioNuevaContrasena(SetPasswordForm):
    """Recibe la contrasena nueva y su confirmacion."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password1'].label = 'Contraseña nueva'
        self.fields['new_password2'].label = 'Confirma la contraseña'
        self.fields['new_password1'].widget.attrs.update({'autofocus': True})
