"""
Comando para cargar los datos minimos con los que arranca el sistema:
los tres niveles de dificultad, una institucion y una materia de ejemplo,
y un usuario de cada rol para poder probar la plataforma.

Se ejecuta con: python manage.py datos_iniciales
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from apps.catalogo.models import Institucion, Materia, Categoria, Nivel
from apps.evaluaciones.models import Grupo, AsignacionDocente

Persona = get_user_model()

# Contrasena comun para los usuarios de prueba. Cambiala en un entorno real.
CONTRASENA_PRUEBA = 'Edumetrica2026'


class Command(BaseCommand):
    help = 'Carga los datos iniciales del sistema (niveles, materia y usuarios de prueba).'

    def handle(self, *args, **opciones):
        self.crear_niveles()
        self.crear_catalogo_ejemplo()
        self.crear_usuarios_prueba()
        self.crear_grupo_ejemplo()
        self.stdout.write(self.style.SUCCESS('Datos iniciales cargados correctamente.'))

    def crear_niveles(self):
        """Da de alta los tres niveles de dificultad que maneja el sistema."""
        nombres = {
            1: 'Básico',
            2: 'Intermedio',
            3: 'Avanzado',
        }
        for numero, nombre in nombres.items():
            Nivel.objects.get_or_create(
                numero=numero,
                defaults={'nombre': nombre},
            )
        self.stdout.write('Niveles listos.')

    def crear_catalogo_ejemplo(self):
        """Crea una institucion, una materia y una categoria de ejemplo."""
        Institucion.objects.get_or_create(nombre='Preparatoria de ejemplo')

        materia, _ = Materia.objects.get_or_create(nombre='Matemáticas')
        Categoria.objects.get_or_create(materia=materia, nombre='Aritmética')
        self.stdout.write('Catalogo de ejemplo listo.')

    def crear_usuarios_prueba(self):
        """Crea un usuario por cada rol para poder probar el acceso."""
        usuarios = [
            ('admin@edumetrica.mx', 'Administrador', 'General', Persona.Rol.ADMINISTRADOR),
            ('profesor@edumetrica.mx', 'Profesor', 'Demo', Persona.Rol.PROFESOR),
            ('alumno@edumetrica.mx', 'Alumno', 'Demo', Persona.Rol.ALUMNO),
        ]

        for correo, nombre, apellido, rol in usuarios:
            if Persona.objects.filter(correo=correo).exists():
                continue

            if rol == Persona.Rol.ADMINISTRADOR:
                # El administrador necesita acceso al panel de Django.
                Persona.objects.create_superuser(
                    correo=correo,
                    nombre=nombre,
                    apellido=apellido,
                    password=CONTRASENA_PRUEBA,
                )
            else:
                Persona.objects.create_user(
                    correo=correo,
                    nombre=nombre,
                    apellido=apellido,
                    password=CONTRASENA_PRUEBA,
                    rol=rol,
                )

        self.stdout.write('Usuarios de prueba listos (contrasena: ' + CONTRASENA_PRUEBA + ').')

    def crear_grupo_ejemplo(self):
        """Crea un grupo de ejemplo con el profesor y el alumno de prueba."""
        institucion = Institucion.objects.first()
        grupo, _ = Grupo.objects.get_or_create(
            nombre='Primero A',
            defaults={'institucion': institucion},
        )

        profesor = Persona.objects.filter(correo='profesor@edumetrica.mx').first()
        alumno = Persona.objects.filter(correo='alumno@edumetrica.mx').first()
        if profesor:
            # El profesor imparte la asignatura de ejemplo en el grupo.
            categoria = Categoria.objects.filter(nombre='Aritmética').first()
            if categoria:
                AsignacionDocente.objects.get_or_create(
                    grupo=grupo, profesor=profesor, categoria=categoria
                )
        if alumno:
            grupo.alumnos.add(alumno)
        self.stdout.write('Grupo de ejemplo listo.')
