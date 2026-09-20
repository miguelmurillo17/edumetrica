"""
Pruebas del flujo central del sistema: programar una evaluacion, presentarla
y cerrarla.

Es la parte de la que depende la hipotesis de la tesis, asi que lo que se
comprueba aqui no es que las pantallas respondan sino que los numeros salgan
bien: que la calificacion cuente sobre el total de la evaluacion y no sobre lo
que el alumno alcanzo a contestar, que al armar el examen solo entren preguntas
validadas, y que finalizar antes de tiempo cierre a cada alumno con lo que
llevaba.
"""

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalogo.models import (
    Categoria, Institucion, Materia, Nivel, OpcionRespuesta, Pregunta,
)
from apps.usuarios.models import Persona

from .models import (
    AsignacionDocente, CategoriaEvaluacion, Evaluacion, Grupo,
    IntentoEvaluacion, RespuestaAlumno,
)


class BaseEvaluacionesTest(TestCase):
    """Un grupo con su profesor, su alumno y un banco de preguntas."""

    def setUp(self):
        self.institucion = Institucion.objects.create(nombre='Preparatoria 1')
        self.materia = Materia.objects.create(
            nombre='Matemáticas', es_cuantitativa=True
        )
        self.categoria = Categoria.objects.create(
            materia=self.materia, nombre='Aritmética'
        )
        self.nivel = Nivel.objects.create(numero=2, nombre='Elemental')

        self.profesor = Persona.objects.create_user(
            correo='profesor@prueba.mx', nombre='Ana', apellido='Ruiz',
            password='Edumetrica2026', rol=Persona.Rol.PROFESOR,
        )
        self.alumno = Persona.objects.create_user(
            correo='alumno@prueba.mx', nombre='Beto', apellido='Lara',
            password='Edumetrica2026', rol=Persona.Rol.ALUMNO,
        )

        self.grupo = Grupo.objects.create(
            nombre='Primero A', institucion=self.institucion
        )
        self.grupo.alumnos.add(self.alumno)
        # El profesor imparte la asignatura en el grupo.
        AsignacionDocente.objects.create(
            grupo=self.grupo, profesor=self.profesor, categoria=self.categoria
        )

    def crear_pregunta(self, **extras):
        datos = {
            'materia': self.materia,
            'categoria': self.categoria,
            'nivel': self.nivel,
            'enunciado': '¿Cuánto es 2 + 3 por 4?',
            'creada_por': self.profesor,
            'estado': Pregunta.Estado.VALIDADA,
        }
        datos.update(extras)
        pregunta = Pregunta.objects.create(**datos)
        for posicion, texto in enumerate(['14', '20', '9', '24']):
            OpcionRespuesta.objects.create(
                pregunta=pregunta, texto=texto, es_correcta=(posicion == 0)
            )
        return pregunta

    def crear_evaluacion(self, *, preguntas=(), inicio=None, fin=None, **extras):
        ahora = timezone.now()
        datos = {
            'titulo': 'Diagnóstico',
            'profesor': self.profesor,
            'grupo': self.grupo,
            'materia': self.materia,
            'fecha_inicio': inicio or ahora - timedelta(hours=1),
            'fecha_fin': fin or ahora + timedelta(hours=1),
            'numero_preguntas': len(preguntas),
        }
        datos.update(extras)
        evaluacion = Evaluacion.objects.create(**datos)
        evaluacion.preguntas.set(preguntas)
        return evaluacion

    def responder(self, intento, pregunta, acerto):
        opcion = pregunta.opciones.filter(es_correcta=acerto).first()
        return RespuestaAlumno.objects.create(
            intento=intento, pregunta=pregunta,
            opcion_seleccionada=opcion, es_correcta=acerto,
        )


class CalificacionTest(BaseEvaluacionesTest):
    """El calculo de la calificacion, que es el numero del que todo depende."""

    def setUp(self):
        super().setUp()
        self.preguntas = [self.crear_pregunta() for _ in range(4)]
        self.evaluacion = self.crear_evaluacion(preguntas=self.preguntas)
        self.intento = IntentoEvaluacion.objects.create(
            evaluacion=self.evaluacion, alumno=self.alumno
        )

    def test_todas_correctas_son_cien(self):
        for pregunta in self.preguntas:
            self.responder(self.intento, pregunta, True)
        self.assertEqual(self.intento.calcular_calificacion(), 100)

    def test_la_mitad_son_cincuenta(self):
        for pregunta in self.preguntas[:2]:
            self.responder(self.intento, pregunta, True)
        for pregunta in self.preguntas[2:]:
            self.responder(self.intento, pregunta, False)
        self.assertEqual(self.intento.calcular_calificacion(), 50)

    def test_sin_responder_nada_es_cero(self):
        self.assertEqual(self.intento.calcular_calificacion(), 0)

    def test_las_no_contestadas_cuentan_como_falladas(self):
        # Es la regla que mas facil se rompe: si el divisor fueran las
        # respuestas guardadas en lugar del total de la evaluacion, un alumno
        # que contesta una sola pregunta y acierta sacaria cien.
        self.responder(self.intento, self.preguntas[0], True)
        self.assertEqual(self.intento.calcular_calificacion(), 25)

    def test_redondea_a_dos_decimales(self):
        # Un tercio de tres aciertos sobre siete preguntas no da un numero
        # redondo, y la calificacion se guarda con dos decimales.
        evaluacion = self.crear_evaluacion(
            preguntas=[self.crear_pregunta() for _ in range(7)]
        )
        intento = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.alumno
        )
        for pregunta in list(evaluacion.preguntas.all())[:3]:
            self.responder(intento, pregunta, True)

        self.assertEqual(intento.calcular_calificacion(), 42.86)

    def test_una_evaluacion_sin_preguntas_no_revienta(self):
        # Dividir entre cero tumbaria la pantalla del alumno al finalizar.
        evaluacion = self.crear_evaluacion(preguntas=[])
        intento = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.alumno
        )
        self.assertEqual(intento.calcular_calificacion(), 0)


class DisponibilidadTest(BaseEvaluacionesTest):
    """Cuando se puede presentar una evaluacion y cuando no."""

    def test_dentro_del_horario_esta_disponible(self):
        self.assertTrue(self.crear_evaluacion().esta_disponible())

    def test_antes_de_la_hora_de_inicio_no(self):
        ahora = timezone.now()
        evaluacion = self.crear_evaluacion(
            inicio=ahora + timedelta(hours=1), fin=ahora + timedelta(hours=2)
        )
        self.assertFalse(evaluacion.esta_disponible())

    def test_despues_de_la_hora_de_fin_tampoco(self):
        ahora = timezone.now()
        evaluacion = self.crear_evaluacion(
            inicio=ahora - timedelta(hours=2), fin=ahora - timedelta(hours=1)
        )
        self.assertFalse(evaluacion.esta_disponible())

    def test_finalizada_no_esta_disponible_aunque_falte_tiempo(self):
        # El profesor la cerro antes: el horario ya no manda.
        evaluacion = self.crear_evaluacion(
            estado=Evaluacion.Estado.FINALIZADA
        )
        self.assertFalse(evaluacion.esta_disponible())


class ProgramarEvaluacionTest(BaseEvaluacionesTest):
    """La pantalla con la que el profesor arma el examen."""

    def setUp(self):
        super().setUp()
        self.otra_categoria = Categoria.objects.create(
            materia=self.materia, nombre='Álgebra'
        )
        # El profesor tambien imparte la segunda asignatura en el grupo.
        AsignacionDocente.objects.create(
            grupo=self.grupo, profesor=self.profesor, categoria=self.otra_categoria
        )
        # Banco suficiente para pedir hasta cinco de cada categoria.
        for _ in range(5):
            self.crear_pregunta()
            self.crear_pregunta(categoria=self.otra_categoria)
        self.client.force_login(self.profesor)

    def datos(self, renglones, **extras):
        """Arma el envio del formulario con su tabla de categorias."""
        ahora = timezone.now()
        envio = {
            'titulo': 'Diagnóstico',
            'grupo': self.grupo.id,
            'materia': self.materia.id,
            'fecha_inicio': (ahora - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
            'fecha_fin': (ahora + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
            'categorias_elegidas-TOTAL_FORMS': str(len(renglones)),
            'categorias_elegidas-INITIAL_FORMS': '0',
            'categorias_elegidas-MIN_NUM_FORMS': '0',
            'categorias_elegidas-MAX_NUM_FORMS': '1000',
        }
        for posicion, (categoria, numero) in enumerate(renglones):
            envio[f'categorias_elegidas-{posicion}-categoria'] = categoria.id
            envio[f'categorias_elegidas-{posicion}-numero_preguntas'] = numero
        envio.update(extras)
        return envio

    def programar(self, renglones, **extras):
        return self.client.post(
            reverse('evaluaciones:crear_evaluacion'),
            self.datos(renglones, **extras),
        )

    def test_arma_el_examen_con_lo_que_pide_cada_renglon(self):
        respuesta = self.programar([(self.categoria, 2), (self.otra_categoria, 3)])

        self.assertRedirects(
            respuesta, reverse('evaluaciones:lista_evaluaciones')
        )
        evaluacion = Evaluacion.objects.get()
        self.assertEqual(evaluacion.preguntas.count(), 5)
        self.assertEqual(
            evaluacion.preguntas.filter(categoria=self.categoria).count(), 2
        )
        self.assertEqual(
            evaluacion.preguntas.filter(categoria=self.otra_categoria).count(), 3
        )

    def test_el_total_es_la_suma_de_los_renglones(self):
        # numero_preguntas es el divisor de la calificacion: si se desfasa de
        # las preguntas que de verdad tiene la evaluacion, todas las
        # calificaciones del grupo salen mal.
        self.programar([(self.categoria, 2), (self.otra_categoria, 3)])

        evaluacion = Evaluacion.objects.get()
        self.assertEqual(evaluacion.numero_preguntas, 5)
        self.assertEqual(evaluacion.numero_preguntas, evaluacion.preguntas.count())

    def test_guarda_los_renglones_de_la_tabla(self):
        self.programar([(self.categoria, 2), (self.otra_categoria, 3)])

        renglones = CategoriaEvaluacion.objects.order_by('id')
        self.assertEqual(renglones.count(), 2)
        self.assertEqual(renglones[0].categoria, self.categoria)
        self.assertEqual(renglones[0].numero_preguntas, 2)

    def test_solo_entran_preguntas_validadas(self):
        # Es la compuerta que sostiene la propuesta: una pregunta generada que
        # nadie ha revisado no puede colarse a un examen real.
        Pregunta.objects.update(estado=Pregunta.Estado.BORRADOR)
        buenas = [self.crear_pregunta() for _ in range(2)]

        self.programar([(self.categoria, 2)])

        evaluacion = Evaluacion.objects.get()
        self.assertEqual(
            set(evaluacion.preguntas.values_list('id', flat=True)),
            {pregunta.id for pregunta in buenas},
        )

    def test_una_pregunta_dada_de_baja_no_entra(self):
        # "Inactiva" es dar de baja una pregunta vieja, distinto de "todavia
        # no la revisan", y las dos tienen que dejarla fuera.
        Pregunta.objects.update(activa=False)
        buenas = [self.crear_pregunta() for _ in range(2)]

        self.programar([(self.categoria, 2)])

        evaluacion = Evaluacion.objects.get()
        self.assertEqual(
            set(evaluacion.preguntas.values_list('id', flat=True)),
            {pregunta.id for pregunta in buenas},
        )

    def test_rechaza_si_el_banco_no_alcanza(self):
        # El conteo del formulario y la seleccion de la vista tienen que mirar
        # el mismo banco: si el formulario dijera que hay veinte y la vista
        # armara con ocho, la evaluacion saldria mas corta sin avisar.
        respuesta = self.programar([(self.categoria, 50)])

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'solo tiene 5 preguntas disponibles')
        self.assertFalse(Evaluacion.objects.exists())

    def test_rechaza_la_tabla_vacia(self):
        respuesta = self.programar([])

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'al menos una asignatura')
        self.assertFalse(Evaluacion.objects.exists())

    def test_rechaza_categorias_repetidas(self):
        # La tabla se rechaza, pero conviene saber quien la rechaza: quien
        # avisa es la restriccion de unicidad del modelo, que el formulario de
        # Django comprueba antes de llegar a la validacion propia. El mensaje
        # escrito a mano en BaseCategoriasFormSet no alcanza a mostrarse.
        respuesta = self.programar([(self.categoria, 1), (self.categoria, 2)])

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Evaluacion.objects.exists())
        self.assertTrue(respuesta.context['filas'].non_form_errors())

    def test_rechaza_una_asignatura_de_otra_disciplina(self):
        otra_materia = Materia.objects.create(nombre='Literatura')
        ajena = Categoria.objects.create(
            materia=otra_materia, nombre='Comprensión'
        )
        self.crear_pregunta(materia=otra_materia, categoria=ajena)
        # Se le asigna al profesor para que el formulario acepte la asignatura;
        # asi la validacion que se prueba es la de disciplina, no la de choices.
        AsignacionDocente.objects.create(
            grupo=self.grupo, profesor=self.profesor, categoria=ajena
        )

        respuesta = self.programar([(ajena, 1)])

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'no pertenece a la disciplina elegida')
        self.assertFalse(Evaluacion.objects.exists())

    def test_rechaza_una_asignatura_que_no_imparte_en_el_grupo(self):
        # El profesor no puede evaluar una asignatura de la disciplina elegida
        # si no la imparte en ese grupo.
        no_asignada = Categoria.objects.create(
            materia=self.materia, nombre='Geometría'
        )
        for _ in range(3):
            self.crear_pregunta(categoria=no_asignada)

        respuesta = self.programar([(no_asignada, 1)])

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Evaluacion.objects.exists())

    def test_rechaza_que_termine_antes_de_empezar(self):
        ahora = timezone.now()
        respuesta = self.programar(
            [(self.categoria, 1)],
            fecha_inicio=(ahora + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
            fecha_fin=(ahora + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'posterior a la de inicio')
        self.assertFalse(Evaluacion.objects.exists())

    def test_el_profesor_solo_ve_sus_grupos(self):
        ajeno = Grupo.objects.create(
            nombre='Segundo B', institucion=self.institucion
        )

        respuesta = self.client.get(reverse('evaluaciones:crear_evaluacion'))

        grupos = respuesta.context['formulario'].fields['grupo'].queryset
        self.assertIn(self.grupo, grupos)
        self.assertNotIn(ajeno, grupos)

    def test_el_administrador_no_programa(self):
        # Programar es del profesor: el administrador da de alta el catalogo
        # pero no imparte clase.
        administrador = Persona.objects.create_user(
            correo='admin@prueba.mx', nombre='Caro', apellido='Solis',
            password='Edumetrica2026', rol=Persona.Rol.ADMINISTRADOR,
        )
        self.client.force_login(administrador)

        respuesta = self.client.get(reverse('evaluaciones:crear_evaluacion'))

        self.assertEqual(respuesta.status_code, 403)


class FinalizarEvaluacionTest(BaseEvaluacionesTest):
    """El profesor cierra la evaluacion antes de tiempo."""

    def setUp(self):
        super().setUp()
        self.otro_alumno = Persona.objects.create_user(
            correo='otro@prueba.mx', nombre='Dani', apellido='Mora',
            password='Edumetrica2026', rol=Persona.Rol.ALUMNO,
        )
        self.grupo.alumnos.add(self.otro_alumno)
        self.preguntas = [self.crear_pregunta() for _ in range(4)]
        self.evaluacion = self.crear_evaluacion(preguntas=self.preguntas)
        self.client.force_login(self.profesor)

    def finalizar(self):
        return self.client.post(reverse(
            'evaluaciones:finalizar_evaluacion', args=[self.evaluacion.id]
        ))

    def test_cierra_los_intentos_en_curso_con_su_parcial(self):
        # El alumno que iba a la mitad se queda con lo que llevaba, no con cero.
        intento = IntentoEvaluacion.objects.create(
            evaluacion=self.evaluacion, alumno=self.alumno
        )
        self.responder(intento, self.preguntas[0], True)
        self.responder(intento, self.preguntas[1], True)

        self.finalizar()

        intento.refresh_from_db()
        self.assertEqual(intento.estado, IntentoEvaluacion.Estado.FINALIZADO)
        self.assertEqual(float(intento.calificacion), 50)
        self.assertIsNotNone(intento.fecha_fin)

    def test_marca_la_evaluacion_como_finalizada(self):
        self.finalizar()

        self.evaluacion.refresh_from_db()
        self.assertEqual(self.evaluacion.estado, Evaluacion.Estado.FINALIZADA)

    def test_antes_de_la_hora_de_fin_queda_como_anticipada(self):
        # Es el dato que distingue "se acabo el tiempo" de "el profesor
        # decidio cerrarla", y se reporta en el capitulo de resultados.
        self.finalizar()

        self.evaluacion.refresh_from_db()
        self.assertTrue(self.evaluacion.finalizada_anticipadamente)

    def test_despues_de_la_hora_de_fin_no_es_anticipada(self):
        ahora = timezone.now()
        self.evaluacion.fecha_inicio = ahora - timedelta(hours=3)
        self.evaluacion.fecha_fin = ahora - timedelta(hours=1)
        self.evaluacion.save()

        self.finalizar()

        self.evaluacion.refresh_from_db()
        self.assertFalse(self.evaluacion.finalizada_anticipadamente)

    def test_no_toca_los_intentos_que_ya_estaban_cerrados(self):
        cerrado = IntentoEvaluacion.objects.create(
            evaluacion=self.evaluacion, alumno=self.alumno,
            estado=IntentoEvaluacion.Estado.FINALIZADO, calificacion=75,
        )

        self.finalizar()

        cerrado.refresh_from_db()
        self.assertEqual(float(cerrado.calificacion), 75)

    def test_el_alumno_que_no_empezo_no_gana_un_intento(self):
        self.finalizar()
        self.assertFalse(
            IntentoEvaluacion.objects.filter(alumno=self.otro_alumno).exists()
        )

    def test_otro_profesor_no_puede_finalizarla(self):
        ajeno = Persona.objects.create_user(
            correo='ajeno@prueba.mx', nombre='Eva', apellido='Pinto',
            password='Edumetrica2026', rol=Persona.Rol.PROFESOR,
        )
        self.client.force_login(ajeno)

        respuesta = self.finalizar()

        self.assertEqual(respuesta.status_code, 404)
        self.evaluacion.refresh_from_db()
        self.assertNotEqual(self.evaluacion.estado, Evaluacion.Estado.FINALIZADA)

    def test_una_visita_sin_confirmar_no_la_finaliza(self):
        # Se confirma con un envio; entrar a la direccion no debe cerrarla.
        self.client.get(reverse(
            'evaluaciones:finalizar_evaluacion', args=[self.evaluacion.id]
        ))

        self.evaluacion.refresh_from_db()
        self.assertNotEqual(self.evaluacion.estado, Evaluacion.Estado.FINALIZADA)


class MisGruposTest(BaseEvaluacionesTest):
    """La pantalla de grupos muestra que asignatura imparte cada profesor."""

    def test_lista_al_profesor_con_su_asignatura(self):
        self.client.force_login(self.profesor)

        respuesta = self.client.get(reverse('evaluaciones:lista_grupos'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Ana Ruiz')
        # La asignatura asignada en el grupo aparece junto al profesor.
        self.assertContains(respuesta, 'Aritmética')

    def test_una_segunda_asignatura_tambien_aparece(self):
        otra = Categoria.objects.create(materia=self.materia, nombre='Álgebra')
        AsignacionDocente.objects.create(
            grupo=self.grupo, profesor=self.profesor, categoria=otra
        )
        self.client.force_login(self.profesor)

        respuesta = self.client.get(reverse('evaluaciones:lista_grupos'))

        self.assertContains(respuesta, 'Aritmética')
        self.assertContains(respuesta, 'Álgebra')
