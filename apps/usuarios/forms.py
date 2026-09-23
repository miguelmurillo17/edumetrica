"""Formularios relacionados con el acceso de las personas al sistema."""

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import (
    AuthenticationForm, PasswordResetForm, SetPasswordForm, UserCreationForm,
)

from .models import Persona


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


class PersonaCreacionForm(UserCreationForm):
    """Alta de una persona desde el panel del administrador.

    Hereda de UserCreationForm para reutilizar password1/password2, la
    validacion con los validadores del proyecto y el set_password en save().
    """

    class Meta:
        model = Persona
        fields = ('correo', 'nombre', 'apellido', 'rol', 'sexo', 'fecha_nacimiento')
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['correo'].label = 'Correo electrónico'


class PersonaEdicionForm(forms.ModelForm):
    """Edicion de una persona ya dada de alta.

    No trae password1/password2 de UserCreationForm porque aqui la
    contrasena es opcional: se deja en blanco para no tocarla, o se llenan
    los dos campos para restablecerla sin pasarle por el flujo de "olvide mi
    contrasena" (util para un alumno sin correo confiable).
    """

    nueva_contrasena1 = forms.CharField(
        label='Nueva contraseña', widget=forms.PasswordInput, required=False,
        help_text='Déjalo en blanco para no cambiar la contraseña actual.',
    )
    nueva_contrasena2 = forms.CharField(
        label='Confirma la nueva contraseña', widget=forms.PasswordInput, required=False,
    )

    class Meta:
        model = Persona
        fields = (
            'correo', 'nombre', 'apellido', 'rol', 'sexo', 'fecha_nacimiento',
            'is_active',
        )
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['correo'].label = 'Correo electrónico'
        self.fields['is_active'].label = 'Activa'

    def clean(self):
        datos = super().clean()
        contrasena1 = datos.get('nueva_contrasena1')
        contrasena2 = datos.get('nueva_contrasena2')

        if contrasena1 or contrasena2:
            if contrasena1 != contrasena2:
                self.add_error('nueva_contrasena2', 'Las contraseñas no coinciden.')
            else:
                try:
                    password_validation.validate_password(contrasena1, self.instance)
                except forms.ValidationError as error:
                    self.add_error('nueva_contrasena1', error)

        return datos

    def save(self, commit=True):
        persona = super().save(commit=False)
        nueva_contrasena = self.cleaned_data.get('nueva_contrasena1')
        if nueva_contrasena:
            persona.set_password(nueva_contrasena)
        if commit:
            persona.save()
        return persona
