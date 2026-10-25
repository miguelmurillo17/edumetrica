"""
Pruebas del comando de consola generar_preguntas.

Las de test_servicios cubren el servicio y el cliente; esta capa, la que el
profesor ve en la terminal, no estaba cubierta. Aqui se revisa lo que imprime
y, sobre todo, que no guarde nada: el comando es una prueba de humo y si
empezara a escribir en la base de datos dejaria de serlo.

Como en las otras, litellm.completion se sustituye por un doble, asi que no
hace falta llave ni se gasta cuota.
"""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from .test_servicios import PREGUNTA_BUENA, respuesta_falsa


def correr(**extras):
    """Ejecuta el comando y regresa lo que imprimio."""
    salida = StringIO()
    opciones = {
        'materia': 'Matemáticas',
        'categoria': 'Aritmética',
        'nivel': 3,
        'cantidad': 1,
        'stdout': salida,
        'no_color': True,
    }
    opciones.update(extras)
    call_command('generar_preguntas', **opciones)
    return salida.getvalue()


@override_settings(AI_PROVIDER='gemini', AI_LLAVES={'gemini': 'llave-de-prueba'},
                   AI_MODEL=None)
class ComandoGenerarPreguntasTest(SimpleTestCase):
    """Lo que el comando imprime en el camino feliz."""

    @patch('apps.ia.cliente.completion')
    def test_imprime_el_enunciado_y_las_opciones(self, doble):
        doble.return_value = respuesta_falsa({'preguntas': [PREGUNTA_BUENA]})

        salida = correr()

        self.assertIn(PREGUNTA_BUENA['enunciado'], salida)
        for opcion in PREGUNTA_BUENA['opciones']:
            self.assertIn(opcion, salida)

    @patch('apps.ia.cliente.completion')
    def test_marca_con_asterisco_la_opcion_correcta(self, doble):
        doble.return_value = respuesta_falsa({'preguntas': [PREGUNTA_BUENA]})

        salida = correr()

        # La correcta es la primera, que se lista como "a)".
        self.assertIn('* a) 14', salida)
        # Y las demas van sin marca.
        self.assertIn('  b) 20', salida)

    @patch('apps.ia.cliente.completion')
    def test_informa_el_proveedor_el_modelo_y_los_tokens(self, doble):
        doble.return_value = respuesta_falsa(
            {'preguntas': [PREGUNTA_BUENA]}, tokens_entrada=11, tokens_salida=22
        )

        salida = correr()

        self.assertIn('gemini', salida)
        self.assertIn('11 tokens de entrada', salida)
        self.assertIn('22', salida)

    @patch('apps.ia.cliente.completion')
    def test_muestra_el_procedimiento(self, doble):
        doble.return_value = respuesta_falsa({'preguntas': [PREGUNTA_BUENA]})

        salida = correr()

        self.assertIn(PREGUNTA_BUENA['procedimiento'], salida)


@override_settings(AI_PROVIDER='gemini', AI_LLAVES={'gemini': 'llave-de-prueba'},
                   AI_MODEL=None)
class DictamenEnConsolaTest(SimpleTestCase):
    """El comando pasa cada pregunta por el verificador y lo dice."""

    @patch('apps.ia.cliente.completion')
    def test_la_pregunta_correcta_sale_aprobada(self, doble):
        doble.return_value = respuesta_falsa({'preguntas': [PREGUNTA_BUENA]})

        salida = correr()

        self.assertIn('verificador: aprobada', salida)
        self.assertIn('Aprobadas por el verificador: 1 de 1', salida)

    @patch('apps.ia.cliente.completion')
    def test_la_clave_equivocada_sale_rechazada_con_su_motivo(self, doble):
        # La expresion da 14 pero se marca como correcta la opcion que dice 20.
        mal_marcada = dict(PREGUNTA_BUENA, indice_correcto=1)
        doble.return_value = respuesta_falsa({'preguntas': [mal_marcada]})

        salida = correr()

        self.assertIn('verificador: rechazada', salida)
        self.assertIn('no coincide con el resultado', salida)
        self.assertIn('Aprobadas por el verificador: 0 de 1', salida)

    @patch('apps.ia.cliente.completion')
    def test_sin_expresion_avisa_que_no_aplica(self, doble):
        # Una categoria que no es cuantitativa no trae expresion que revisar.
        sin_expresion = dict(PREGUNTA_BUENA, expresion='', valores=[])
        doble.return_value = respuesta_falsa({'preguntas': [sin_expresion]})

        salida = correr(categoria='Comprensión')

        self.assertIn('no aplica', salida)
        self.assertIn('revisión humana', salida)


@override_settings(AI_PROVIDER='gemini', AI_LLAVES={'gemini': 'llave-de-prueba'},
                   AI_MODEL=None)
class SalidaJsonTest(SimpleTestCase):
    """Con --json se ve la respuesta cruda y nada mas."""

    @patch('apps.ia.cliente.completion')
    def test_json_trae_los_campos_de_la_pregunta(self, doble):
        import json

        doble.return_value = respuesta_falsa({'preguntas': [PREGUNTA_BUENA]})

        salida = correr(json=True)
        crudas = json.loads(salida)

        self.assertEqual(len(crudas), 1)
        self.assertEqual(crudas[0]['enunciado'], PREGUNTA_BUENA['enunciado'])
        self.assertEqual(crudas[0]['expresion'], PREGUNTA_BUENA['expresion'])
        self.assertEqual(crudas[0]['indice_correcto'], 0)

    @patch('apps.ia.cliente.completion')
    def test_json_no_imprime_el_dictamen(self, doble):
        doble.return_value = respuesta_falsa({'preguntas': [PREGUNTA_BUENA]})

        salida = correr(json=True)

        # Con --json se sale antes de verificar: la salida debe ser JSON puro,
        # para poder encauzarla a otro programa.
        self.assertNotIn('verificador', salida)


@override_settings(AI_PROVIDER='gemini', AI_LLAVES={'gemini': 'llave-de-prueba'},
                   AI_MODEL=None)
class ErroresEnConsolaTest(SimpleTestCase):
    """Un fallo del proveedor sale como error de comando, no como traza."""

    @patch('apps.ia.cliente.completion')
    def test_la_cuota_agotada_se_vuelve_error_de_comando(self, doble):
        from litellm.exceptions import RateLimitError

        doble.side_effect = RateLimitError(
            message='rate limit', llm_provider='gemini',
            model='gemini/gemini-3.6-flash',
        )

        with self.assertRaises(CommandError) as capturado:
            correr()

        self.assertIn('límite de solicitudes', str(capturado.exception).lower())

    def test_sin_llave_configurada_se_vuelve_error_de_comando(self):
        with override_settings(AI_LLAVES={'gemini': ''}):
            with self.assertRaises(CommandError):
                correr()


@override_settings(AI_PROVIDER='gemini', AI_LLAVES={'gemini': 'llave-de-prueba'},
                   AI_MODEL=None)
class NoGuardaNadaTest(TestCase):
    """El comando es una prueba de humo: la base queda intacta."""

    @patch('apps.ia.cliente.completion')
    def test_no_crea_preguntas_ni_solicitudes(self, doble):
        from apps.catalogo.models import Pregunta, SolicitudGeneracion

        doble.return_value = respuesta_falsa({'preguntas': [PREGUNTA_BUENA]})

        correr()

        self.assertEqual(Pregunta.objects.count(), 0)
        self.assertEqual(SolicitudGeneracion.objects.count(), 0)
