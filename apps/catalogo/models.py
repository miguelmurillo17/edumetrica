"""
Catalogos del sistema: la institucion, las materias, las categorias,
los niveles de dificultad y las preguntas con sus opciones de respuesta.
"""

from django.db import models
from django.conf import settings


class Institucion(models.Model):
    """Datos de la escuela donde se usa el sistema."""

    nombre = models.CharField(max_length=200)
    direccion = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = 'institucion'
        verbose_name_plural = 'instituciones'

    def __str__(self):
        return self.nombre


class Materia(models.Model):
    """Una materia que se evalua, por ejemplo Matematicas o Literatura."""

    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'materia'
        verbose_name_plural = 'materias'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    """Tema dentro de una materia, por ejemplo Aritmetica dentro de Matematicas."""

    materia = models.ForeignKey(
        Materia,
        on_delete=models.CASCADE,
        related_name='categorias',
    )
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'categoria'
        verbose_name_plural = 'categorias'
        ordering = ['materia', 'nombre']
        # No se puede repetir el mismo nombre de categoria dentro de una materia.
        unique_together = ['materia', 'nombre']

    def __str__(self):
        return f'{self.materia.nombre} - {self.nombre}'


class Nivel(models.Model):
    """Nivel de dificultad de las preguntas. El sistema maneja seis niveles."""

    numero = models.PositiveSmallIntegerField(unique=True)
    nombre = models.CharField(max_length=50)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = 'nivel'
        verbose_name_plural = 'niveles'
        ordering = ['numero']

    def __str__(self):
        return f'Nivel {self.numero} - {self.nombre}'


class Pregunta(models.Model):
    """Pregunta de opcion multiple que forma parte de las evaluaciones."""

    materia = models.ForeignKey(
        Materia,
        on_delete=models.PROTECT,
        related_name='preguntas',
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name='preguntas',
    )
    nivel = models.ForeignKey(
        Nivel,
        on_delete=models.PROTECT,
        related_name='preguntas',
    )
    enunciado = models.TextField()
    # Imagen opcional que acompana al enunciado de la pregunta.
    imagen = models.ImageField(upload_to='preguntas/', null=True, blank=True)
    # Profesor o administrador que dio de alta la pregunta.
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='preguntas_creadas',
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'pregunta'
        verbose_name_plural = 'preguntas'
        ordering = ['-fecha_creacion']

    def __str__(self):
        # Se muestra solo el inicio del enunciado para que sea legible en listas.
        return self.enunciado[:60]


class OpcionRespuesta(models.Model):
    """Cada una de las cuatro opciones de respuesta de una pregunta."""

    pregunta = models.ForeignKey(
        Pregunta,
        on_delete=models.CASCADE,
        related_name='opciones',
    )
    # Una opcion puede ser texto, imagen o ambos.
    texto = models.CharField(max_length=255, blank=True)
    imagen = models.ImageField(upload_to='opciones/', null=True, blank=True)
    es_correcta = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'opcion de respuesta'
        verbose_name_plural = 'opciones de respuesta'

    def __str__(self):
        return self.texto if self.texto else f'Opcion con imagen ({self.id})'
