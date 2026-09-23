"""
Modelo de usuario del sistema. Toda persona que entra a Edumetrica
(administrador, profesor o alumno) se guarda en la tabla Persona.
"""

from datetime import date
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.core.exceptions import ValidationError

from config.orden_alfabetico import alfabetico


class AdministradorPersonas(BaseUserManager):
    """Encargado de crear las personas y los superusuarios del sistema."""

    def create_user(self, correo, nombre, apellido, password=None, **otros_campos):
        # El correo es obligatorio porque es el dato con el que se inicia sesion.
        if not correo:
            raise ValueError('La persona debe tener un correo electronico.')

        correo = self.normalize_email(correo)
        persona = self.model(
            correo=correo,
            nombre=nombre,
            apellido=apellido,
            **otros_campos,
        )
        # set_password guarda la contrasena cifrada, nunca en texto plano.
        persona.set_password(password)
        persona.save(using=self._db)
        return persona

    def create_superuser(self, correo, nombre, apellido, password=None, **otros_campos):
        # Un superusuario siempre tiene rol de administrador y acceso al panel.
        otros_campos.setdefault('rol', Persona.Rol.ADMINISTRADOR)
        otros_campos.setdefault('is_staff', True)
        otros_campos.setdefault('is_superuser', True)

        if otros_campos.get('is_staff') is not True:
            raise ValueError('El superusuario debe tener is_staff en verdadero.')
        if otros_campos.get('is_superuser') is not True:
            raise ValueError('El superusuario debe tener is_superuser en verdadero.')

        return self.create_user(correo, nombre, apellido, password, **otros_campos)


class Persona(AbstractBaseUser, PermissionsMixin):
    """Representa a cualquier usuario del sistema sin importar su rol."""

    class Rol(models.TextChoices):
        ADMINISTRADOR = 'administrador', 'Administrador'
        ALUMNO = 'alumno', 'Alumno'
        PROFESOR = 'profesor', 'Profesor'

    class Sexo(models.TextChoices):
        FEMENINO = 'femenino', 'Femenino'
        MASCULINO = 'masculino', 'Masculino'
        OTRO = 'otro', 'Otro'

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    sexo = models.CharField(
        max_length=10,
        choices=Sexo.choices,
        blank=True,
    )
    correo = models.EmailField(unique=True, verbose_name='correo electrónico')
    rol = models.CharField(
        max_length=15,
        choices=Rol.choices,
        default=Rol.ALUMNO,
    )

    # Campos de control que necesita Django para el manejo de sesiones.
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    objects = AdministradorPersonas()

    # El correo reemplaza al nombre de usuario para iniciar sesion.
    USERNAME_FIELD = 'correo'
    # Django manda aqui el mensaje para restablecer la contrasena. Sin esto
    # buscaria un campo llamado "email", que este modelo no tiene.
    EMAIL_FIELD = 'correo'
    REQUIRED_FIELDS = ['nombre', 'apellido']

    class Meta:
        verbose_name = 'persona'
        verbose_name_plural = 'personas'
        ordering = alfabetico('apellido', 'nombre')

    def __str__(self):
        return f'{self.apellido} {self.nombre} ({self.get_rol_display()})'

    @property
    def nombre_completo(self):
        return f'{self.apellido} {self.nombre}'

    def clean(self):
        super().clean()
        if self.fecha_nacimiento:
            edad = (date.today() - self.fecha_nacimiento).days / 365.25
            if edad > 80:
                raise ValidationError(
                    {'fecha_nacimiento': 'La fecha de nacimiento no puede ser más de 80 años atrás.'}
                )

    # Atajos para preguntar el rol de una persona de forma legible.
    @property
    def es_administrador(self):
        return self.rol == self.Rol.ADMINISTRADOR

    @property
    def es_profesor(self):
        return self.rol == self.Rol.PROFESOR

    @property
    def es_alumno(self):
        return self.rol == self.Rol.ALUMNO
