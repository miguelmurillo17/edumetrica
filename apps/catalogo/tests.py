"""
Pruebas de la compuerta de validacion de preguntas.

Solo las preguntas activas y validadas pueden entrar a una evaluacion. Es la
regla que impide que una pregunta generada por inteligencia artificial llegue
a un examen real sin que nadie la haya revisado, asi que conviene tenerla
amarrada con pruebas.
"""

from django.test import TestCase

from .models import Materia, Categoria, Nivel, Pregunta


class PreguntasUtilizablesTest(TestCase):
    """Revisa que el filtro de preguntas utilizables deje pasar lo correcto."""

    def setUp(self):
        self.materia = Materia.objects.create(nombre='Matemáticas')
        self.categoria = Categoria.objects.create(
            materia=self.materia, nombre='Álgebra'
        )
        self.nivel = Nivel.objects.create(numero=1, nombre='Básico')

    def crear_pregunta(self, **campos):
        """Arma una pregunta con lo minimo y los campos que se le indiquen."""
        datos = {
            'materia': self.materia,
            'categoria': self.categoria,
            'nivel': self.nivel,
            'enunciado': 'Cuanto es 2 + 2?',
        }
        datos.update(campos)
        return Pregunta.objects.create(**datos)

    def test_una_pregunta_nace_en_borrador(self):
        # El valor por omision es borrador a proposito: si una ruta nueva
        # olvida marcarla, se queda fuera en lugar de colarse sin revision.
        pregunta = self.crear_pregunta()
        self.assertEqual(pregunta.estado, Pregunta.Estado.BORRADOR)
        self.assertFalse(pregunta.es_utilizable)

    def test_la_validada_si_es_utilizable(self):
        pregunta = self.crear_pregunta(estado=Pregunta.Estado.VALIDADA)
        self.assertTrue(pregunta.es_utilizable)
        self.assertIn(pregunta, Pregunta.objects.utilizables())

    def test_el_borrador_no_entra(self):
        self.crear_pregunta(estado=Pregunta.Estado.BORRADOR)
        self.assertEqual(Pregunta.objects.utilizables().count(), 0)

    def test_la_descartada_no_entra(self):
        self.crear_pregunta(estado=Pregunta.Estado.DESCARTADA)
        self.assertEqual(Pregunta.objects.utilizables().count(), 0)

    def test_la_validada_pero_inactiva_no_entra(self):
        # Dar de baja una pregunta vieja es distinto de no haberla revisado,
        # pero cualquiera de las dos cosas la deja fuera de las evaluaciones.
        self.crear_pregunta(estado=Pregunta.Estado.VALIDADA, activa=False)
        self.assertEqual(Pregunta.objects.utilizables().count(), 0)

    def test_solo_cuenta_las_utilizables_entre_varias(self):
        self.crear_pregunta(estado=Pregunta.Estado.VALIDADA)
        self.crear_pregunta(estado=Pregunta.Estado.VALIDADA)
        self.crear_pregunta(estado=Pregunta.Estado.BORRADOR)
        self.crear_pregunta(estado=Pregunta.Estado.DESCARTADA)
        self.crear_pregunta(estado=Pregunta.Estado.VALIDADA, activa=False)

        self.assertEqual(Pregunta.objects.count(), 5)
        self.assertEqual(Pregunta.objects.utilizables().count(), 2)
