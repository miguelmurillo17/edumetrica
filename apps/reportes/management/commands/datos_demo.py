"""
Comando que genera datos de demostracion para poder ver el tablero con
informacion realista: alumnos con edad y sexo, grupos, preguntas,
evaluaciones finalizadas e intentos con desempeno variado.

Se ejecuta con: python manage.py datos_demo
Pensado tambien como base para el caso de estudio de la tesis.
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.catalogo.models import Materia, Categoria, Nivel, Pregunta, OpcionRespuesta
from apps.evaluaciones.models import (
    Grupo, Evaluacion, CategoriaEvaluacion, IntentoEvaluacion, RespuestaAlumno,
)

Persona = get_user_model()

CONTRASENA = 'Edumetrica2026'

# Estructura de materias y sus categorias para la demostracion.
ESTRUCTURA = {
    'Matematicas': ['Aritmetica', 'Algebra'],
    'Literatura': ['Comprension', 'Gramatica'],
}

NOMBRES = [
    ('Sofia', 'Ramirez'), ('Mateo', 'Torres'), ('Valeria', 'Flores'),
    ('Diego', 'Castro'), ('Camila', 'Reyes'), ('Sebastian', 'Mendoza'),
    ('Renata', 'Vargas'), ('Emiliano', 'Guzman'), ('Regina', 'Ortiz'),
    ('Leonardo', 'Silva'), ('Ximena', 'Rios'), ('Daniel', 'Navarro'),
]


class Command(BaseCommand):
    help = 'Genera datos de demostracion para el tablero y el caso de estudio.'

    def handle(self, *args, **opciones):
        if Persona.objects.filter(correo='alumno1@demo.mx').exists():
            self.stdout.write('Los datos de demostracion ya estaban cargados.')
            return

        # Se usa una semilla fija para que los resultados sean reproducibles.
        random.seed(2026)

        self.crear_niveles()
        categorias = self.crear_materias()
        profesor = self.obtener_profesor()
        grupos = self.crear_grupos_y_alumnos(profesor)
        preguntas_por_materia = self.crear_preguntas(categorias, profesor)
        self.crear_evaluaciones_e_intentos(profesor, grupos, preguntas_por_materia)
        self.crear_evaluacion_disponible(profesor, grupos[0], preguntas_por_materia)

        self.stdout.write(self.style.SUCCESS('Datos de demostracion generados.'))

    def crear_niveles(self):
        for numero in range(1, 7):
            Nivel.objects.get_or_create(numero=numero, defaults={'nombre': f'Nivel {numero}'})

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

    def crear_grupos_y_alumnos(self, profesor):
        """Crea dos grupos con alumnos que tienen edad y sexo variados."""
        grupos = []
        sexos = [Persona.Sexo.MASCULINO, Persona.Sexo.FEMENINO, Persona.Sexo.OTRO]
        contador = 1

        for indice_grupo in range(2):
            grupo, _ = Grupo.objects.get_or_create(nombre=f'Primero {chr(65 + indice_grupo)}')
            grupo.profesores.add(profesor)

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
                    nivel=Nivel.objects.get(numero=random.randint(1, 6)),
                    enunciado=f'{categoria.nombre}: pregunta de ejemplo numero {numero}',
                    creada_por=profesor,
                )
                # La primera opcion siempre es la correcta.
                OpcionRespuesta.objects.create(pregunta=pregunta, texto='Respuesta correcta', es_correcta=True)
                for letra in ['A', 'B', 'C']:
                    OpcionRespuesta.objects.create(pregunta=pregunta, texto=f'Opcion {letra}', es_correcta=False)
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

    def crear_evaluacion_disponible(self, profesor, grupo, preguntas_por_materia):
        """Crea una evaluacion disponible ahora para poder probar el flujo del alumno."""
        materia = Materia.objects.get(nombre='Matematicas')
        seleccion = preguntas_por_materia['Matematicas'][:5]
        ahora = timezone.now()

        evaluacion = Evaluacion.objects.create(
            titulo='Examen de practica (disponible)',
            profesor=profesor, grupo=grupo, materia=materia,
            numero_preguntas=len(seleccion),
            fecha_inicio=ahora - timedelta(hours=1),
            fecha_fin=ahora + timedelta(days=3),
            estado=Evaluacion.Estado.PROGRAMADA,
        )
        self.repartir_categorias(evaluacion, list(materia.categorias.all()), seleccion)
        evaluacion.preguntas.set(seleccion)

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
