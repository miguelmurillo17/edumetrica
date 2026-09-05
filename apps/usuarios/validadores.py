"""
Reglas que debe cumplir una contrasena.

Django ya trae estas validaciones y sus mensajes en espanol, pero hablando
de usted. Aqui solo se reemplaza el texto para que tutee, como el resto del
sistema; la revision de fondo sigue siendo la de Django.
"""

from django.core.exceptions import ValidationError
from django.contrib.auth import password_validation as reglas


class SimilitudConDatosPersonales(reglas.UserAttributeSimilarityValidator):
    """Evita contrasenas parecidas al nombre o al correo de la persona."""

    # Django compara contra username, first_name, last_name y email, campos
    # que nuestro modelo Persona no tiene, asi que hay que nombrarle los
    # nuestros o la revision no compararia nada.
    CAMPOS_DE_LA_PERSONA = ('correo', 'nombre', 'apellido')

    def __init__(self, user_attributes=CAMPOS_DE_LA_PERSONA, max_similarity=0.7):
        super().__init__(user_attributes, max_similarity)

    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError:
            raise ValidationError(
                'Tu contraseña se parece demasiado a tus datos personales.',
                code='password_too_similar',
            )

    def get_help_text(self):
        return 'No uses tu nombre ni tu correo dentro de la contraseña.'


class LargoMinimo(reglas.MinimumLengthValidator):
    """Pide una cantidad minima de caracteres."""

    def validate(self, password, user=None):
        if len(password) < self.min_length:
            raise ValidationError(
                f'Tu contraseña es muy corta. Debe tener al menos '
                f'{self.min_length} caracteres.',
                code='password_too_short',
            )

    def get_help_text(self):
        return f'Debe tener al menos {self.min_length} caracteres.'


class ContrasenaComun(reglas.CommonPasswordValidator):
    """Rechaza las contrasenas que todo el mundo usa."""

    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError:
            raise ValidationError(
                'Tu contraseña es demasiado común. Elige una menos predecible.',
                code='password_too_common',
            )

    def get_help_text(self):
        return 'No uses contraseñas comunes como "12345678" o "password".'


class SoloNumeros(reglas.NumericPasswordValidator):
    """Obliga a que la contrasena no sea puros digitos."""

    def validate(self, password, user=None):
        if password.isdigit():
            raise ValidationError(
                'Tu contraseña no puede ser solo números.',
                code='password_entirely_numeric',
            )

    def get_help_text(self):
        return 'No puede ser solo números.'
