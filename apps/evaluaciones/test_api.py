"""
Pruebas de los endpoints que consume la aplicacion del alumno.

Lo que se comprueba aqui es la regla que sostiene la retroalimentacion: el
procedimiento se entrega al terminar el intento y jamas al iniciarlo. Es la
misma regla que ya cuidaba es_correcta, y por el mismo motivo: conocerlo
durante el examen equivale a conocer la respuesta.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalogo.models import (
    Categoria, Institucion, Materia, Nivel, OpcionRespuesta, Pregunta,
)
from apps.usuarios.models import Persona

from .models import (
    AsignacionDocente, Evaluacion, Grupo, IntentoEvaluacion, RespuestaAlumno,
)


PROCEDIMIENTO = 'Primero multiplicas y luego sumas: 3 por 4 son 12, mas 2 son 14.'


class ResultadoDelAlumnoTest(TestCase):
    """El procedimiento en la pantalla de resultado."""

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
        AsignacionDocente.objects.create(
            grupo=self.grupo, profesor=self.profesor, categoria=self.categoria
        )

        # Dos preguntas: el alumno acertara la primera y fallara la segunda.
        self.acertada = self.crear_pregunta('¿Cuánto es 2 + 2?')
        self.fallada = self.crear_pregunta('¿Cuánto es 2 + 3 por 4?')

        ahora = timezone.now()
        self.evaluacion = Evaluacion.objects.create(
            titulo='Diagnóstico', profesor=self.profesor, grupo=self.grupo,
            materia=self.materia, numero_preguntas=2,
            fecha_inicio=ahora - timedelta(hours=1),
            fecha_fin=ahora + timedelta(hours=1),
        )
        self.evaluacion.preguntas.add(self.acertada, self.fallada)

        self.client.force_login(self.alumno)

    def crear_pregunta(self, enunciado):
        pregunta = Pregunta.objects.create(
            materia=self.materia, categoria=self.categoria, nivel=self.nivel,
            enunciado=enunciado, procedimiento=PROCEDIMIENTO,
            creada_por=self.profesor, origen=Pregunta.Origen.IA,
            estado=Pregunta.Estado.VALIDADA,
        )
        for posicion, texto in enumerate(['14', '20', '9', '24']):
            OpcionRespuesta.objects.create(
                pregunta=pregunta, texto=texto, es_correcta=(posicion == 0)
            )
        return pregunta

    def responder(self, intento, pregunta, acerto):
        opcion = pregunta.opciones.filter(es_correcta=acerto).first()
        RespuestaAlumno.objects.create(
            intento=intento, pregunta=pregunta,
            opcion_seleccionada=opcion, es_correcta=acerto,
        )

    def intento_resuelto(self):
        """Un intento con una acertada y una fallada, todavia sin finalizar."""
        intento = IntentoEvaluacion.objects.create(
            evaluacion=self.evaluacion, alumno=self.alumno
        )
        self.responder(intento, self.acertada, True)
        self.responder(intento, self.fallada, False)
        return intento

    def fila_de(self, detalle, enunciado):
        return next(f for f in detalle if f['enunciado'] == enunciado)

    def test_al_iniciar_no_se_filtra_el_procedimiento(self):
        # Es la regla que no debe romperse: durante el examen el procedimiento
        # es tan delator como saber cual opcion es la correcta.
        respuesta = self.client.post(reverse(
            'evaluaciones:api_iniciar', args=[self.evaluacion.id]
        ))

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn(PROCEDIMIENTO, respuesta.content.decode())
        for pregunta in respuesta.json()['preguntas']:
            self.assertNotIn('procedimiento', pregunta)

    def test_al_finalizar_llega_el_de_la_pregunta_fallada(self):
        intento = self.intento_resuelto()

        respuesta = self.client.post(reverse(
            'evaluaciones:api_finalizar', args=[intento.id]
        ))

        fila = self.fila_de(respuesta.json()['detalle'], self.fallada.enunciado)
        self.assertFalse(fila['acerto'])
        self.assertEqual(fila['procedimiento'], PROCEDIMIENTO)

    def test_la_acertada_no_lo_trae(self):
        # En la que acerto no ensena nada y solo alargaria la pantalla.
        intento = self.intento_resuelto()

        respuesta = self.client.post(reverse(
            'evaluaciones:api_finalizar', args=[intento.id]
        ))

        fila = self.fila_de(respuesta.json()['detalle'], self.acertada.enunciado)
        self.assertTrue(fila['acerto'])
        self.assertEqual(fila['procedimiento'], '')

    def test_una_pregunta_sin_responder_tambien_lo_trae(self):
        # Cuenta como fallada, y es justo donde el alumno mas necesita ver como
        # se resolvia.
        intento = IntentoEvaluacion.objects.create(
            evaluacion=self.evaluacion, alumno=self.alumno
        )

        respuesta = self.client.post(reverse(
            'evaluaciones:api_finalizar', args=[intento.id]
        ))

        fila = self.fila_de(respuesta.json()['detalle'], self.fallada.enunciado)
        self.assertIsNone(fila['tu_respuesta'])
        self.assertEqual(fila['procedimiento'], PROCEDIMIENTO)

    def test_al_consultar_el_resultado_tambien_llega(self):
        # El alumno que vuelve a su resultado debe poder leerlo otra vez.
        intento = self.intento_resuelto()
        self.client.post(reverse('evaluaciones:api_finalizar', args=[intento.id]))

        respuesta = self.client.get(reverse(
            'evaluaciones:api_resultado', args=[intento.id]
        ))

        fila = self.fila_de(respuesta.json()['detalle'], self.fallada.enunciado)
        self.assertEqual(fila['procedimiento'], PROCEDIMIENTO)

    def test_una_pregunta_sin_procedimiento_no_rompe_el_resultado(self):
        # Las preguntas capturadas a mano pueden no traerlo, y el resultado
        # tiene que salir igual.
        self.fallada.procedimiento = ''
        self.fallada.save()
        intento = self.intento_resuelto()

        respuesta = self.client.post(reverse(
            'evaluaciones:api_finalizar', args=[intento.id]
        ))

        fila = self.fila_de(respuesta.json()['detalle'], self.fallada.enunciado)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(fila['procedimiento'], '')

    def test_el_resultado_no_se_entrega_a_media_evaluacion(self):
        # El resultado lleva la respuesta correcta y el procedimiento de cada
        # pregunta. Si se entregara sin comprobar que el intento ya termino,
        # bastaria con pedirlo desde otra pestaña para tener el examen
        # resuelto, y las dos reglas que cuida iniciar_evaluacion no servirian
        # de nada.
        intento = self.intento_resuelto()
        self.assertEqual(intento.estado, IntentoEvaluacion.Estado.EN_CURSO)

        respuesta = self.client.get(reverse(
            'evaluaciones:api_resultado', args=[intento.id]
        ))

        self.assertEqual(respuesta.status_code, 400)
        cuerpo = respuesta.content.decode()
        self.assertNotIn(PROCEDIMIENTO, cuerpo)
        self.assertNotIn('respuesta_correcta', cuerpo)
