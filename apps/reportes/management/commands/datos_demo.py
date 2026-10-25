"""
Comando que genera datos de demostracion para poder ver el tablero con
informacion realista: alumnos con edad y sexo, grupos, preguntas,
evaluaciones finalizadas e intentos con desempeno variado.

Se ejecuta con: python manage.py datos_demo
Pensado tambien como base para el caso de estudio de la tesis.

Dos banderas lo hacen repetible:
  --reiniciar      borra lo que sembro antes y lo vuelve a generar.
  --minutos N      acorta la ventana de la evaluacion disponible, para poder
                   ver la cuenta regresiva y la entrega automatica sin esperar
                   los tres dias que dura por omision.
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.utils import timezone

from apps.catalogo.models import (
    Institucion, Materia, Categoria, Nivel, Pregunta, OpcionRespuesta,
)
from apps.evaluaciones.models import (
    Grupo, AsignacionDocente, Evaluacion, CategoriaEvaluacion,
    IntentoEvaluacion, RespuestaAlumno,
)
from apps.usuarios.models import Notificacion

Persona = get_user_model()

CONTRASENA = 'Edumetrica2026'

# Estructura de materias y sus categorias para la demostracion.
ESTRUCTURA = {
    'Matemáticas': ['Aritmética', 'Álgebra'],
    'Literatura': ['Comprensión', 'Gramática'],
}

# Los tres niveles que maneja el sistema, con los mismos nombres que les pone
# datos_iniciales. Una version anterior de este comando creaba seis, y los tres
# sobrantes salian en los filtros y en la grafica de aciertos por nivel.
NIVELES = {
    1: 'Básico',
    2: 'Intermedio',
    3: 'Avanzado',
}

# Por donde reconocemos lo que sembro este comando, para poder borrarlo sin
# tocar el banco capturado a mano ni los usuarios de datos_iniciales.
GRUPOS_DEMO = ['Primero A', 'Primero B']
MARCA_PREGUNTA = 'pregunta de ejemplo'
CORREO_DEMO = '@demo.mx'

# Cuantas preguntas lleva el examen de practica con que se prueba el flujo
# del alumno.
NUMERO_DE_PRACTICA = 5

NOMBRES = [
    ('Sofía', 'Ramírez'), ('Mateo', 'Torres'), ('Valeria', 'Flores'),
    ('Diego', 'Castro'), ('Camila', 'Reyes'), ('Sebastián', 'Mendoza'),
    ('Renata', 'Vargas'), ('Emiliano', 'Guzmán'), ('Regina', 'Ortiz'),
    ('Leonardo', 'Silva'), ('Ximena', 'Rios'), ('Daniel', 'Navarro'),
]


class Command(BaseCommand):
    help = 'Genera datos de demostracion para el tablero y el caso de estudio.'

    def add_arguments(self, analizador):
        analizador.add_argument(
            '--reiniciar', action='store_true',
            help='Borra los datos de demostracion y los vuelve a generar.',
        )
        analizador.add_argument(
            '--minutos', type=int, default=None,
            help=(
                'Duracion en minutos de la evaluacion disponible. Sin esto la '
                'ventana dura tres dias; con un valor corto (6, por ejemplo) '
                'se alcanza a ver la cuenta regresiva y la entrega automatica.'
            ),
        )

    def handle(self, *args, **opciones):
        if opciones['reiniciar']:
            self.limpiar_datos_demo()

        if Persona.objects.filter(correo='alumno1@demo.mx').exists():
            self.stdout.write(
                'Los datos de demostracion ya estaban cargados. '
                'Usa --reiniciar para volver a generarlos.'
            )
            return

        # Se usa una semilla fija para que los resultados sean reproducibles.
        random.seed(2026)

        self.crear_niveles()
        categorias = self.crear_materias()
        profesor = self.obtener_profesor()
        grupos = self.crear_grupos_y_alumnos(profesor, categorias)
        preguntas_por_materia = self.crear_preguntas(categorias, profesor)
        self.crear_evaluaciones_e_intentos(profesor, grupos, preguntas_por_materia)
        self.crear_evaluacion_disponible(
            profesor, grupos[0], preguntas_por_materia, opciones['minutos']
        )

        self.stdout.write(self.style.SUCCESS('Datos de demostracion generados.'))

    def crear_niveles(self):
        """Da de alta los tres niveles de dificultad que maneja el sistema."""
        for numero, nombre in NIVELES.items():
            Nivel.objects.get_or_create(numero=numero, defaults={'nombre': nombre})

    def crear_materias(self):
        """Crea las materias con sus categorias y regresa la lista de categorias."""
        categorias = []
        for nombre_materia, nombres_categorias in ESTRUCTURA.items():
            materia, _ = Materia.objects.get_or_create(nombre=nombre_materia)
            for nombre_categoria in nombres_categorias:
                categoria, _ = Categoria.objects.get_or_create(
                    materia=materia, nombre=nombre_categoria
                )
                categorias.append(categoria)
        return categorias

    def obtener_profesor(self):
        profesor = Persona.objects.filter(correo='profesor@edumetrica.mx').first()
        if profesor is None:
            profesor = Persona.objects.create_user(
                correo='profesor@edumetrica.mx', nombre='Profesor', apellido='Demo',
                password=CONTRASENA, rol=Persona.Rol.PROFESOR,
            )
        return profesor

    def crear_grupos_y_alumnos(self, profesor, categorias):
        """Crea dos grupos con alumnos que tienen edad y sexo variados."""
        grupos = []
        sexos = [Persona.Sexo.MASCULINO, Persona.Sexo.FEMENINO, Persona.Sexo.OTRO]
        contador = 1
        # Primero A es tambien el grupo de datos_iniciales, que es el que le
        # pone institucion. Se la ponemos aqui tambien para que el grupo no
        # quede huerfano cuando se resiembra con --reiniciar.
        institucion = Institucion.objects.first()

        for indice_grupo in range(2):
            grupo, _ = Grupo.objects.get_or_create(
                nombre=f'Primero {chr(65 + indice_grupo)}',
                defaults={'institucion': institucion},
            )
            if grupo.institucion is None and institucion is not None:
                grupo.institucion = institucion
                grupo.save()
            # El profesor imparte todas las asignaturas del catalogo demo en el
            # grupo, para poder programar evaluaciones de ambas disciplinas.
            for categoria in categorias:
                AsignacionDocente.objects.get_or_create(
                    grupo=grupo, profesor=profesor, categoria=categoria
                )

            for _ in range(6):
                nombre, apellido = NOMBRES[contador - 1]
                edad = random.randint(15, 18)
                nacimiento = date(date.today().year - edad, random.randint(1, 12), random.randint(1, 28))
                alumno = Persona.objects.create_user(
                    correo=f'alumno{contador}@demo.mx',
                    nombre=nombre, apellido=apellido, password=CONTRASENA,
                    rol=Persona.Rol.ALUMNO,
                    sexo=random.choice(sexos),
                    fecha_nacimiento=nacimiento,
                )
                grupo.alumnos.add(alumno)
                contador += 1

            # El alumno de datos_iniciales entra al primer grupo. Es con el que
            # inicia sesion el script de capturas de la tesis, y sin grupo no
            # le aparecia ninguna evaluacion que presentar.
            if indice_grupo == 0:
                alumno_inicial = Persona.objects.filter(
                    correo='alumno@edumetrica.mx'
                ).first()
                if alumno_inicial is not None:
                    grupo.alumnos.add(alumno_inicial)

            grupos.append(grupo)
        return grupos

    def crear_preguntas(self, categorias, profesor):
        """Crea cinco preguntas con cuatro opciones por cada categoria.

        Regresa las preguntas agrupadas por materia para usarlas despues.
        """
        preguntas_por_materia = {}
        for categoria in categorias:
            for numero in range(1, 6):
                pregunta = Pregunta.objects.create(
                    materia=categoria.materia, categoria=categoria,
                    nivel=Nivel.objects.get(numero=random.randint(1, len(NIVELES))),
                    enunciado=f'{categoria.nombre}: pregunta de ejemplo número {numero}',
                    # El procedimiento es lo que el alumno lee al final en las
                    # preguntas que fallo. Sin el, la pantalla de resultado de
                    # la demostracion se veria sin la mitad que ensena.
                    procedimiento=(
                        'Se identifica lo que pide el enunciado.\n'
                        'Se plantea la operación y se resuelve paso a paso.\n'
                        'El resultado obtenido corresponde a la opción correcta.'
                    ),
                    creada_por=profesor,
                    # Las de demostracion nacen validadas para que se puedan
                    # usar en las evaluaciones de ejemplo.
                    origen=Pregunta.Origen.MANUAL,
                    estado=Pregunta.Estado.VALIDADA,
                )
                # La primera opcion siempre es la correcta.
                OpcionRespuesta.objects.create(pregunta=pregunta, texto='Respuesta correcta', es_correcta=True)
                for letra in ['A', 'B', 'C']:
                    OpcionRespuesta.objects.create(pregunta=pregunta, texto=f'Opción {letra}', es_correcta=False)
                preguntas_por_materia.setdefault(categoria.materia.nombre, []).append(pregunta)
        return preguntas_por_materia

    def crear_evaluaciones_e_intentos(self, profesor, grupos, preguntas_por_materia):
        """Programa evaluaciones finalizadas y genera los intentos de los alumnos."""
        ahora = timezone.now()

        for grupo in grupos:
            for nombre_materia in ESTRUCTURA:
                materia = Materia.objects.get(nombre=nombre_materia)
                categorias = list(materia.categorias.all())
                preguntas = preguntas_por_materia[nombre_materia]
                seleccion = random.sample(preguntas, min(8, len(preguntas)))

                evaluacion = Evaluacion.objects.create(
                    titulo=f'{nombre_materia} - {grupo.nombre}',
                    profesor=profesor, grupo=grupo, materia=materia,
                    numero_preguntas=len(seleccion),
                    fecha_inicio=ahora - timedelta(days=7),
                    fecha_fin=ahora - timedelta(days=7, hours=-2),
                    estado=Evaluacion.Estado.FINALIZADA,
                )
                # Las preguntas elegidas se reparten entre las categorias.
                self.repartir_categorias(evaluacion, categorias, seleccion)
                evaluacion.preguntas.set(seleccion)

                self.generar_intentos(evaluacion, grupo, seleccion, ahora)

    def crear_evaluacion_disponible(self, profesor, grupo, preguntas_por_materia,
                                    minutos=None):
        """Crea una evaluacion disponible ahora para poder probar el flujo del alumno.

        Con minutos se acorta la ventana. Es lo que permite ver la cuenta
        regresiva, que asoma en los ultimos tres minutos, y la entrega
        automatica al llegar a cero: con la ventana de tres dias habria que
        esperar tres dias para que aparecieran.
        """
        materia = Materia.objects.get(nombre='Matemáticas')
        seleccion = self.preguntas_para_practicar(materia, preguntas_por_materia)
        ahora = timezone.now()
        if minutos:
            fecha_fin = ahora + timedelta(minutes=minutos)
        else:
            fecha_fin = ahora + timedelta(days=3)

        evaluacion = Evaluacion.objects.create(
            titulo='Examen de practica (disponible)',
            profesor=profesor, grupo=grupo, materia=materia,
            numero_preguntas=len(seleccion),
            fecha_inicio=ahora - timedelta(hours=1),
            fecha_fin=fecha_fin,
            estado=Evaluacion.Estado.PROGRAMADA,
        )
        self.repartir_categorias(evaluacion, list(materia.categorias.all()), seleccion)
        evaluacion.preguntas.set(seleccion)

    def preguntas_para_practicar(self, materia, preguntas_por_materia):
        """Elige con que preguntas se arma el examen de practica.

        Se prefieren las del banco capturado a mano: tienen enunciado y
        procedimiento de verdad. Las de ejemplo que siembra este comando dicen
        "pregunta de ejemplo numero N" y su opcion correcta se llama
        "Respuesta correcta", que es justo lo que saldria en las capturas de
        pantalla de la tesis. Si el banco no esta cargado se usan las de
        ejemplo, para que el comando siga sirviendo en una base recien creada.
        """
        del_banco = list(
            Pregunta.objects.utilizables()
            .filter(materia=materia)
            .exclude(enunciado__contains=MARCA_PREGUNTA)[:NUMERO_DE_PRACTICA]
        )
        if len(del_banco) == NUMERO_DE_PRACTICA:
            return del_banco
        return preguntas_por_materia[materia.nombre][:NUMERO_DE_PRACTICA]

    def repartir_categorias(self, evaluacion, categorias, seleccion):
        """Crea los renglones de categorias contando las preguntas de cada una."""
        conteo = {}
        for pregunta in seleccion:
            conteo[pregunta.categoria_id] = conteo.get(pregunta.categoria_id, 0) + 1

        for categoria in categorias:
            numero = conteo.get(categoria.id, 0)
            if numero:
                CategoriaEvaluacion.objects.create(
                    evaluacion=evaluacion,
                    categoria=categoria,
                    numero_preguntas=numero,
                )

    def generar_intentos(self, evaluacion, grupo, preguntas, ahora):
        """Crea un intento finalizado por alumno con respuestas segun su habilidad."""
        for alumno in grupo.alumnos.all():
            # Cada alumno tiene una habilidad distinta para dar variedad.
            habilidad = random.uniform(0.4, 0.95)
            intento = IntentoEvaluacion.objects.create(
                evaluacion=evaluacion, alumno=alumno,
                estado=IntentoEvaluacion.Estado.FINALIZADO,
                fecha_fin=ahora - timedelta(days=7, hours=-1),
            )
            for pregunta in preguntas:
                opciones = list(pregunta.opciones.all())
                correcta = next(opcion for opcion in opciones if opcion.es_correcta)
                if random.random() < habilidad:
                    elegida = correcta
                else:
                    elegida = random.choice([opcion for opcion in opciones if not opcion.es_correcta])
                RespuestaAlumno.objects.create(
                    intento=intento, pregunta=pregunta,
                    opcion_seleccionada=elegida, es_correcta=elegida.es_correcta,
                )
            intento.calificacion = intento.calcular_calificacion()
            intento.save()

    def limpiar_datos_demo(self):
        """Borra lo que sembro este comando para poder volver a sembrarlo.

        El orden importa, porque varias llaves foraneas son PROTECT: los
        intentos arrastran las respuestas, que son las que protegen a las
        preguntas, y las evaluaciones protegen a los grupos. Solo se va lo que
        nacio de aqui: el banco de preguntas capturado a mano y los usuarios de
        datos_iniciales se quedan donde estan.
        """
        grupos = Grupo.objects.filter(nombre__in=GRUPOS_DEMO)
        evaluaciones = Evaluacion.objects.filter(grupo__in=grupos)
        alumnos = Persona.objects.filter(correo__endswith=CORREO_DEMO)

        # Los avisos de los alumnos demo se van con ellos.
        Notificacion.objects.filter(persona__in=alumnos).delete()

        IntentoEvaluacion.objects.filter(evaluacion__in=evaluaciones).delete()
        evaluaciones.delete()
        Pregunta.objects.filter(enunciado__contains=MARCA_PREGUNTA).delete()
        AsignacionDocente.objects.filter(grupo__in=grupos).delete()
        grupos.delete()
        alumnos.delete()

        self.borrar_avisos_sin_destino()

        # Los niveles 4 a 6 los dejaba una version anterior de este comando.
        # Solo se van si ya nadie los usa; si alguna pregunta del banco quedo
        # colgada de ellos, se avisa en vez de tumbar el comando.
        for nivel in Nivel.objects.filter(numero__gt=len(NIVELES)):
            try:
                nivel.delete()
            except ProtectedError:
                self.stdout.write(
                    f'El nivel {nivel.numero} sigue en uso y se quedo.'
                )

        self.stdout.write('Datos de demostracion borrados.')

    def borrar_avisos_sin_destino(self):
        """Quita los avisos que apuntan a una evaluacion que ya no existe.

        Se corre despues de borrar las evaluaciones, no antes: los que quedaron
        de pruebas anteriores llevan en la campanita a una pagina que no carga,
        y por el destinatario no se distinguen de los buenos.
        """
        vivas = set(Evaluacion.objects.values_list('id', flat=True))
        muertos = []
        for aviso in Notificacion.objects.filter(url__contains='/evaluaciones/'):
            partes = aviso.url.strip('/').split('/')
            if len(partes) < 2 or not partes[1].isdigit():
                continue
            if int(partes[1]) not in vivas:
                muertos.append(aviso.id)

        if muertos:
            Notificacion.objects.filter(id__in=muertos).delete()
            if len(muertos) == 1:
                self.stdout.write('Se quito 1 aviso que ya no tenia destino.')
            else:
                self.stdout.write(
                    f'Se quitaron {len(muertos)} avisos que ya no tenian destino.'
                )
