"""
Logica central del sistema: los grupos de alumnos, las evaluaciones que
programa el profesor, los intentos de cada alumno y sus respuestas.
"""

from django.db import models
from django.conf import settings
from django.utils import timezone

from apps.catalogo.models import Institucion, Materia, Categoria, Pregunta, OpcionRespuesta


class Grupo(models.Model):
    """Conjunto de alumnos al que el profesor le programa evaluaciones."""

    nombre = models.CharField(max_length=100)
    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.CASCADE,
        related_name='grupos',
        null=True,
        blank=True,
    )
    # Alumnos que pertenecen al grupo. El administrador hace esta asignacion.
    alumnos = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='grupos',
        blank=True,
    )
    # Profesores que imparten en el grupo. Un grupo puede tener varios.
    profesores = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='grupos_asignados',
        blank=True,
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'grupo'
        verbose_name_plural = 'grupos'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Evaluacion(models.Model):
    """Examen que el profesor programa a un grupo en una fecha determinada."""

    class Estado(models.TextChoices):
        PROGRAMADA = 'programada', 'Programada'
        EN_CURSO = 'en_curso', 'En curso'
        FINALIZADA = 'finalizada', 'Finalizada'

    titulo = models.CharField(max_length=200)
    profesor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='evaluaciones_creadas',
    )
    grupo = models.ForeignKey(
        Grupo,
        on_delete=models.PROTECT,
        related_name='evaluaciones',
    )
    materia = models.ForeignKey(
        Materia,
        on_delete=models.PROTECT,
        related_name='evaluaciones',
    )
    # Preguntas concretas que se arman al momento de programar la evaluacion.
    preguntas = models.ManyToManyField(
        Pregunta,
        related_name='evaluaciones',
        blank=True,
    )
    # Total de preguntas de la evaluacion. Se calcula sumando las de cada
    # categoria elegida, se guarda para no recalcularlo en cada consulta.
    numero_preguntas = models.PositiveSmallIntegerField(default=0)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    estado = models.CharField(
        max_length=12,
        choices=Estado.choices,
        default=Estado.PROGRAMADA,
    )
    # Se marca cuando el profesor decide terminar antes del tiempo programado.
    finalizada_anticipadamente = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'evaluacion'
        verbose_name_plural = 'evaluaciones'
        ordering = ['-fecha_inicio']

    def __str__(self):
        return f'{self.titulo} ({self.grupo.nombre})'

    def esta_disponible(self):
        """Indica si la evaluacion se puede presentar en este momento."""
        ahora = timezone.now()
        if self.estado == self.Estado.FINALIZADA:
            return False
        return self.fecha_inicio <= ahora <= self.fecha_fin


class CategoriaEvaluacion(models.Model):
    """Cuantas preguntas se toman de una categoria dentro de una evaluacion."""

    evaluacion = models.ForeignKey(
        Evaluacion,
        on_delete=models.CASCADE,
        related_name='categorias_elegidas',
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name='evaluaciones',
    )
    numero_preguntas = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name = 'categoria de la evaluacion'
        verbose_name_plural = 'categorias de la evaluacion'
        # Una categoria no se puede repetir dentro de la misma evaluacion.
        constraints = [
            models.UniqueConstraint(
                fields=['evaluacion', 'categoria'],
                name='categoria_unica_por_evaluacion',
            ),
        ]
        ordering = ['id']

    def __str__(self):
        return f'{self.categoria.nombre}: {self.numero_preguntas} preguntas'


class IntentoEvaluacion(models.Model):
    """Registro de cada alumno que presenta una evaluacion."""

    class Estado(models.TextChoices):
        EN_CURSO = 'en_curso', 'En curso'
        FINALIZADO = 'finalizado', 'Finalizado'

    evaluacion = models.ForeignKey(
        Evaluacion,
        on_delete=models.CASCADE,
        related_name='intentos',
    )
    alumno = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='intentos',
    )
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(
        max_length=12,
        choices=Estado.choices,
        default=Estado.EN_CURSO,
    )
    # Calificacion final del alumno en una escala de cero a cien.
    calificacion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'intento de evaluacion'
        verbose_name_plural = 'intentos de evaluacion'
        # Cada alumno presenta una evaluacion una sola vez.
        unique_together = ['evaluacion', 'alumno']

    def __str__(self):
        return f'{self.alumno.nombre_completo} - {self.evaluacion.titulo}'

    def calcular_calificacion(self):
        """Calcula la calificacion segun las respuestas correctas del alumno."""
        total = self.evaluacion.numero_preguntas
        if total == 0:
            return 0

        aciertos = self.respuestas.filter(es_correcta=True).count()
        return round((aciertos / total) * 100, 2)


class RespuestaAlumno(models.Model):
    """Respuesta que da un alumno a una pregunta dentro de un intento."""

    intento = models.ForeignKey(
        IntentoEvaluacion,
        on_delete=models.CASCADE,
        related_name='respuestas',
    )
    pregunta = models.ForeignKey(
        Pregunta,
        on_delete=models.PROTECT,
        related_name='respuestas',
    )
    # Opcion que eligio el alumno. Queda vacia si no alcanzo a contestar.
    opcion_seleccionada = models.ForeignKey(
        OpcionRespuesta,
        on_delete=models.PROTECT,
        related_name='respuestas',
        null=True,
        blank=True,
    )
    # Se guarda si la respuesta fue correcta para no recalcular despues.
    es_correcta = models.BooleanField(default=False)
    fecha_respuesta = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'respuesta de alumno'
        verbose_name_plural = 'respuestas de alumno'
        # Una sola respuesta por pregunta dentro de cada intento.
        unique_together = ['intento', 'pregunta']

    def __str__(self):
        return f'{self.intento.alumno.nombre_completo} - {self.pregunta}'
