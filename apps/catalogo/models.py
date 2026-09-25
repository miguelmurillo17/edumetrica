"""
Catalogos del sistema: la institucion, las materias, las categorias,
los niveles de dificultad y las preguntas con sus opciones de respuesta.
"""

from django.db import models
from django.conf import settings

from config.orden_alfabetico import alfabetico


class Institucion(models.Model):
    """Datos de la escuela donde se usa el sistema."""

    nombre = models.CharField(max_length=200)
    direccion = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = 'institución'
        verbose_name_plural = 'instituciones'
        ordering = alfabetico('nombre')

    def __str__(self):
        return self.nombre


class Materia(models.Model):
    """Una materia que se evalua, por ejemplo Matematicas o Literatura."""

    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)
    # Si la materia es cuantitativa, sus preguntas generadas deben traer la
    # expresion que el verificador simbolico revisa. Sin esta bandera, una
    # pregunta de matematicas sin expresion pasaria como "no aplica" y se
    # saltaria la comprobacion. El valor por omision es falso porque la mayoria
    # de las materias no lo son; el administrador la marca al darlas de alta.
    es_cuantitativa = models.BooleanField(default=False)

    class Meta:
        # En la interfaz una materia se llama "disciplina" (el codigo sigue
        # diciendo materia). Ver la regla de acentos e identificadores.
        verbose_name = 'disciplina'
        verbose_name_plural = 'disciplinas'
        ordering = alfabetico('nombre')

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    """Tema dentro de una materia, por ejemplo Aritmetica dentro de Matematicas."""

    materia = models.ForeignKey(
        Materia,
        on_delete=models.CASCADE,
        related_name='categorias',
        verbose_name='disciplina',
    )
    nombre = models.CharField(max_length=100)
    activa = models.BooleanField(default=True)

    class Meta:
        # En la interfaz una categoria se llama "asignatura" (el codigo sigue
        # diciendo categoria).
        verbose_name = 'asignatura'
        verbose_name_plural = 'asignaturas'
        # Ordena por el nombre de la materia, no por su id, para que coincida
        # con el orden alfabetico del texto que se ve en el select
        # ("Materia - Categoria").
        ordering = alfabetico('materia__nombre', 'nombre')
        # No se puede repetir el mismo nombre de categoria dentro de una materia.
        unique_together = ['materia', 'nombre']

    def __str__(self):
        return f'{self.materia.nombre} - {self.nombre}'


class Nivel(models.Model):
    """Nivel de dificultad de las preguntas. El sistema maneja tres niveles."""

    numero = models.PositiveSmallIntegerField(unique=True)
    nombre = models.CharField(max_length=50)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = 'nivel'
        verbose_name_plural = 'niveles'
        ordering = ['numero']

    def __str__(self):
        return f'Nivel {self.numero} - {self.nombre}'


class CategoriaNivel(models.Model):
    """Que tipo de preguntas corresponde a un nivel dentro de una asignatura.

    Una misma dificultad significa cosas distintas segun la asignatura (un
    nivel 2 de aritmetica no es lo mismo que un nivel 2 de trigonometria), asi
    que la descripcion vive por pareja categoria-nivel y no en el nivel solo.
    Se le manda a la inteligencia artificial junto con el numero de nivel al
    generar una pregunta nueva.
    """

    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.CASCADE,
        related_name='descripciones_nivel',
        verbose_name='asignatura',
    )
    nivel = models.ForeignKey(
        Nivel,
        on_delete=models.CASCADE,
        related_name='descripciones_categoria',
    )
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = 'tipo de preguntas por nivel'
        verbose_name_plural = 'tipos de preguntas por nivel'
        unique_together = ['categoria', 'nivel']
        ordering = ['categoria', 'nivel__numero']

    def __str__(self):
        return f'{self.categoria} - {self.nivel}'


class SolicitudGeneracion(models.Model):
    """Registro de cada lote de preguntas que se le pidio a la inteligencia
    artificial.

    De aqui salen los numeros del capitulo de resultados: cuantas preguntas se
    pidieron, cuantas llegaron, cuantas paso el verificador simbolico y cuantas
    termino validando el profesor.
    """

    profesor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='solicitudes_generacion',
    )
    materia = models.ForeignKey(
        Materia,
        on_delete=models.PROTECT,
        related_name='solicitudes',
        verbose_name='disciplina',
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name='solicitudes',
        verbose_name='asignatura',
    )
    nivel = models.ForeignKey(
        Nivel,
        on_delete=models.PROTECT,
        related_name='solicitudes',
    )
    class Estado(models.TextChoices):
        EN_PROCESO = 'en_proceso', 'En proceso'
        EXITOSA = 'exitosa', 'Exitosa'
        FALLIDA = 'fallida', 'Fallida'

    cantidad_pedida = models.PositiveSmallIntegerField()
    # Cuantas preguntas devolvio el modelo.
    cantidad_recibida = models.PositiveSmallIntegerField(default=0)
    # Cuantas de esas paso el verificador simbolico.
    cantidad_aprobada = models.PositiveSmallIntegerField(default=0)
    # Modelo y consumo, para poder reportar el costo del experimento.
    modelo = models.CharField(max_length=60, blank=True)
    tokens_entrada = models.PositiveIntegerField(default=0)
    tokens_salida = models.PositiveIntegerField(default=0)
    fecha = models.DateTimeField(auto_now_add=True)
    # La solicitud nace en proceso porque la llamada al proveedor corre en un
    # hilo aparte, y la pantalla del profesor sondea este campo para saber si
    # ya termino. Un solo campo dice las tres cosas; con un booleano "exitosa"
    # no se podria distinguir "fallo" de "todavia no acaba".
    estado = models.CharField(
        max_length=12,
        choices=Estado.choices,
        default=Estado.EN_PROCESO,
    )
    # Cuando falla se guardan por separado el tipo de falla y el mensaje ya
    # redactado que si puede leer el profesor.
    tipo_error = models.CharField(max_length=20, blank=True)
    mensaje_error = models.TextField(blank=True)
    # El texto crudo del proveedor. Es para la bitacora: nunca se muestra en
    # pantalla, porque un volcado de JSON hace pensar que el sistema se rompio.
    detalle_error = models.TextField(blank=True)

    class Meta:
        verbose_name = 'solicitud de generación'
        verbose_name_plural = 'solicitudes de generación'
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.categoria.nombre} x{self.cantidad_pedida} ({self.fecha:%d/%m/%Y})'

    @property
    def cantidad_validada(self):
        """Cuantas preguntas del lote termino validando el profesor.

        Se cuenta al vuelo en lugar de guardarla, porque cambia cada vez que
        el profesor revisa una pregunta y un contador guardado se desfasaria.
        """
        return self.preguntas.filter(estado=Pregunta.Estado.VALIDADA).count()


class PreguntaQuerySet(models.QuerySet):
    """Consultas propias de las preguntas."""

    def utilizables(self):
        """Las que pueden entrar a una evaluacion: activas y ya validadas.

        Se concentra aqui para que el filtro sea uno solo. Antes vivia repetido
        en el formulario y en la vista que arma la evaluacion, y era facil
        cambiar uno y olvidar el otro.
        """
        return self.filter(activa=True, estado=Pregunta.Estado.VALIDADA)


class Pregunta(models.Model):
    """Pregunta de opcion multiple que forma parte de las evaluaciones."""

    class Origen(models.TextChoices):
        MANUAL = 'manual', 'Capturada por el profesor'
        IA = 'ia', 'Generada con inteligencia artificial'

    class Estado(models.TextChoices):
        BORRADOR = 'borrador', 'Borrador'
        VALIDADA = 'validada', 'Validada'
        DESCARTADA = 'descartada', 'Descartada'

    materia = models.ForeignKey(
        Materia,
        on_delete=models.PROTECT,
        related_name='preguntas',
        verbose_name='disciplina',
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name='preguntas',
        verbose_name='asignatura',
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
    # Ultima persona que la edito, valido o descarto. Nulo si nadie la ha tocado
    # desde que se dio de alta.
    modificada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='preguntas_modificadas',
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    # Se actualiza sola en cada guardado, junto con modificada_por.
    fecha_modificacion = models.DateTimeField(auto_now=True)
    activa = models.BooleanField(default=True)

    # De donde salio la pregunta. Sirve para separar las metricas de la tesis.
    origen = models.CharField(
        max_length=10,
        choices=Origen.choices,
        default=Origen.MANUAL,
    )
    # Una pregunta nace en borrador a proposito: si alguna ruta nueva olvida
    # marcarla, se queda fuera de las evaluaciones en lugar de colarse sin
    # que nadie la haya revisado.
    estado = models.CharField(
        max_length=12,
        choices=Estado.choices,
        default=Estado.BORRADOR,
    )
    # Explicacion paso a paso que se le muestra al alumno al terminar.
    procedimiento = models.TextField(blank=True)
    # Operacion de la que sale la respuesta correcta, la que el verificador
    # simbolico comprobo. Vacia en las preguntas capturadas a mano.
    expresion = models.CharField('expresión', max_length=300, blank=True)
    # Dictamen del verificador simbolico. Queda en nulo cuando la pregunta no
    # es de matematicas y por lo tanto no habia nada que comprobar.
    verificada_simbolicamente = models.BooleanField(null=True, blank=True)
    # Regla que fallo, cuando el verificador o el profesor la descartaron.
    motivo_rechazo = models.TextField(blank=True)
    # Lote del que salio, si se genero con inteligencia artificial.
    solicitud = models.ForeignKey(
        'SolicitudGeneracion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='preguntas',
    )

    objects = PreguntaQuerySet.as_manager()

    class Meta:
        verbose_name = 'pregunta'
        verbose_name_plural = 'preguntas'
        ordering = ['-fecha_creacion']

    def __str__(self):
        # Se muestra solo el inicio del enunciado para que sea legible en listas.
        return self.enunciado[:60]

    @property
    def es_utilizable(self):
        """Indica si la pregunta puede formar parte de una evaluacion."""
        return self.activa and self.estado == self.Estado.VALIDADA


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
        verbose_name = 'opción de respuesta'
        verbose_name_plural = 'opciones de respuesta'

    def __str__(self):
        return self.texto if self.texto else f'Opcion con imagen ({self.id})'
