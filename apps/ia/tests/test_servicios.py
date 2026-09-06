"""
Pruebas del modulo de inteligencia artificial.

Ninguna llama a la interfaz real: se sustituye litellm.completion por un doble.
Asi corren en cualquier maquina, sin llave y sin gastar cuota del plan gratuito.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.ia.errores import (
    ErrorConfiguracionIA, ErrorProveedorIA, ErrorRespuestaIA,
)
from apps.ia.servicios import generar_preguntas


def respuesta_falsa(contenido, tokens_entrada=100, tokens_salida=200):
    """Imita la forma de lo que devuelve litellm.completion()."""
    if not isinstance(contenido, str):
        contenido = json.dumps(contenido)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=contenido))],
        usage=SimpleNamespace(
            prompt_tokens=tokens_entrada, completion_tokens=tokens_salida
        ),
    )


PREGUNTA_BUENA = {
    'enunciado': '¿Cuánto es 2 + 3 por 4?',
    'expresion': '2 + 3*4',
    'opciones': ['14', '20', '9', '24'],
    'valores': ['14', '20', '9', '24'],
    'indice_correcto': 0,
    'procedimiento': 'Primero resuelves la multiplicación y luego sumas.',
}

LOTE_BUENO = {'preguntas': [PREGUNTA_BUENA]}


@override_settings(AI_PROVIDER='gemini', AI_LLAVES={'gemini': 'llave-de-prueba'},
                   AI_MODEL=None)
class GenerarPreguntasTest(SimpleTestCase):
    """El camino feliz y las formas de fallar."""

    def pedir(self, **extras):
        return generar_preguntas(
            materia='Matemáticas', categoria='Aritmética', nivel=3,
            cantidad=1, **extras
        )

    @patch('apps.ia.cliente.completion')
    def test_devuelve_las_preguntas_del_lote(self, doble):
        doble.return_value = respuesta_falsa(LOTE_BUENO)

        resultado = self.pedir()

        self.assertEqual(len(resultado.preguntas), 1)
        pregunta = resultado.preguntas[0]
        self.assertEqual(pregunta.respuesta_correcta, '14')
        self.assertEqual(pregunta.expresion, '2 + 3*4')
        self.assertTrue(pregunta.procedimiento)
        self.assertEqual(resultado.proveedor, 'gemini')
        self.assertEqual(resultado.tokens_salida, 200)

    @patch('apps.ia.cliente.completion')
    def test_usa_el_modelo_por_omision_del_proveedor(self, doble):
        doble.return_value = respuesta_falsa(LOTE_BUENO)
        self.pedir()
        self.assertEqual(
            doble.call_args.kwargs['model'], 'gemini/gemini-3.6-flash'
        )

    @override_settings(AI_MODEL='gemini/otro-modelo')
    @patch('apps.ia.cliente.completion')
    def test_ai_model_sobrescribe_el_modelo(self, doble):
        doble.return_value = respuesta_falsa(LOTE_BUENO)
        self.pedir()
        self.assertEqual(doble.call_args.kwargs['model'], 'gemini/otro-modelo')

    @patch('apps.ia.cliente.completion')
    def test_aisla_el_json_envuelto_en_bloque_de_codigo(self, doble):
        # Pasa aunque se pida modo JSON: el modelo a veces lo envuelve.
        envuelto = f'Claro, aquí tienes:\n```json\n{json.dumps(LOTE_BUENO)}\n```'
        doble.return_value = respuesta_falsa(envuelto)

        resultado = self.pedir()

        self.assertEqual(len(resultado.preguntas), 1)

    @patch('apps.ia.cliente.completion')
    def test_recorta_si_llegan_de_mas(self, doble):
        doble.return_value = respuesta_falsa(
            {'preguntas': [PREGUNTA_BUENA, PREGUNTA_BUENA, PREGUNTA_BUENA]}
        )
        resultado = self.pedir()
        self.assertEqual(len(resultado.preguntas), 1)


@override_settings(AI_PROVIDER='gemini', AI_LLAVES={'gemini': 'llave-de-prueba'},
                   AI_MODEL=None)
class RespuestasInvalidasTest(SimpleTestCase):
    """El modo JSON garantiza JSON valido, no que traiga la forma esperada."""

    def pedir(self):
        return generar_preguntas(
            materia='Matemáticas', categoria='Aritmética', nivel=3, cantidad=1
        )

    def con_lote(self, lote):
        with patch('apps.ia.cliente.completion') as doble:
            doble.return_value = respuesta_falsa(lote)
            with self.assertRaises(ErrorRespuestaIA):
                self.pedir()

    @patch('apps.ia.cliente.completion')
    def test_rechaza_json_mal_formado(self, doble):
        doble.return_value = respuesta_falsa('esto no es json')
        with self.assertRaises(ErrorRespuestaIA):
            self.pedir()

    def test_rechaza_si_no_trae_lista_de_preguntas(self):
        self.con_lote({'otra_cosa': []})

    def test_rechaza_la_lista_vacia(self):
        self.con_lote({'preguntas': []})

    def test_rechaza_una_pregunta_sin_enunciado(self):
        mala = dict(PREGUNTA_BUENA, enunciado='')
        self.con_lote({'preguntas': [mala]})

    def test_rechaza_si_no_trae_cuatro_opciones(self):
        mala = dict(PREGUNTA_BUENA, opciones=['14', '20'])
        self.con_lote({'preguntas': [mala]})

    def test_rechaza_opciones_repetidas(self):
        mala = dict(PREGUNTA_BUENA, opciones=['14', '14', '9', '24'])
        self.con_lote({'preguntas': [mala]})

    def test_rechaza_el_indice_fuera_de_rango(self):
        mala = dict(PREGUNTA_BUENA, indice_correcto=7)
        self.con_lote({'preguntas': [mala]})

    def test_rechaza_el_indice_que_no_es_entero(self):
        mala = dict(PREGUNTA_BUENA, indice_correcto='0')
        self.con_lote({'preguntas': [mala]})

    def test_rechaza_una_pregunta_sin_procedimiento(self):
        # Sin procedimiento no sirve para retroalimentar al alumno.
        mala = dict(PREGUNTA_BUENA, procedimiento='')
        self.con_lote({'preguntas': [mala]})

    @patch('apps.ia.cliente.completion')
    def test_ignora_los_valores_incompletos(self, doble):
        # Si los valores simbolicos vienen a medias se descartan y se usan las
        # opciones. Mejor que dejar pasar una lista desalineada.
        mala = dict(PREGUNTA_BUENA, valores=['14', '20'])
        doble.return_value = respuesta_falsa({'preguntas': [mala]})

        resultado = self.pedir()

        pregunta = resultado.preguntas[0]
        self.assertEqual(pregunta.valores, [])
        self.assertEqual(pregunta.valores_para_verificar, pregunta.opciones)


class ConfiguracionTest(SimpleTestCase):
    """Errores que son culpa nuestra, no del proveedor."""

    @override_settings(AI_PROVIDER='gemini', AI_LLAVES={'gemini': ''})
    def test_sin_llave_avisa_cual_falta(self):
        with self.assertRaises(ErrorConfiguracionIA) as capturado:
            generar_preguntas(
                materia='Matemáticas', categoria='Aritmética', nivel=1,
                cantidad=1,
            )
        mensaje = str(capturado.exception)
        self.assertIn('GEMINI_API_KEY', mensaje)
        self.assertIn('aistudio.google.com', mensaje)

    @override_settings(AI_PROVIDER='inventado', AI_LLAVES={})
    def test_proveedor_desconocido_lista_los_validos(self):
        with self.assertRaises(ErrorConfiguracionIA) as capturado:
            generar_preguntas(
                materia='Matemáticas', categoria='Aritmética', nivel=1,
                cantidad=1,
            )
        self.assertIn('gemini', str(capturado.exception))

    @override_settings(AI_PROVIDER='gemini', AI_LLAVES={'gemini': 'x'})
    def test_solo_acepta_una_pregunta_a_la_vez(self):
        # Decision del proyecto: se genera de una en una para que el profesor
        # revise cada pregunta enseguida y una mala no tumbe un lote entero.
        for cantidad in [0, 2, 20, 21, -1]:
            with self.assertRaises(ValueError):
                generar_preguntas(
                    materia='Matemáticas', categoria='Aritmética', nivel=1,
                    cantidad=cantidad,
                )


@override_settings(AI_PROVIDER='gemini', AI_LLAVES={'gemini': 'llave-de-prueba'},
                   AI_MODEL=None)
class FallasDelProveedorTest(SimpleTestCase):
    """Cada falla del proveedor sale traducida, nunca como error de LiteLLM."""

    def pedir(self):
        return generar_preguntas(
            materia='Matemáticas', categoria='Aritmética', nivel=3, cantidad=1
        )

    @patch('apps.ia.cliente.completion')
    def test_la_cuota_agotada_es_reintentable(self, doble):
        from litellm.exceptions import RateLimitError

        doble.side_effect = RateLimitError(
            message='rate limit', llm_provider='gemini',
            model='gemini/gemini-3.6-flash',
        )
        with self.assertRaises(ErrorProveedorIA) as capturado:
            self.pedir()

        self.assertTrue(capturado.exception.reintentable)
        self.assertIn('cuota', str(capturado.exception).lower())

    @patch('apps.ia.cliente.completion')
    def test_la_llave_rechazada_es_error_de_configuracion(self, doble):
        from litellm.exceptions import AuthenticationError

        doble.side_effect = AuthenticationError(
            message='clave mala', llm_provider='gemini',
            model='gemini/gemini-3.6-flash',
        )
        # No es ErrorProveedorIA: reintentar no sirve de nada.
        with self.assertRaises(ErrorConfiguracionIA):
            self.pedir()

    @patch('apps.ia.cliente.completion')
    def test_el_modelo_inexistente_no_es_reintentable(self, doble):
        from litellm.exceptions import BadRequestError

        doble.side_effect = BadRequestError(
            message='modelo no existe', llm_provider='gemini',
            model='gemini/inventado',
        )
        with self.assertRaises(ErrorProveedorIA) as capturado:
            self.pedir()

        self.assertFalse(capturado.exception.reintentable)


@override_settings(AI_PROVIDER='gemini', AI_LLAVES={'gemini': 'llave-de-prueba'},
                   AI_MODEL=None)
class ExigirExpresionTest(SimpleTestCase):
    """El hueco por donde una pregunta podria esquivar al verificador.

    Si el modelo omite la expresion, el verificador contesta "no aplica" y la
    pregunta pasa sin revisarse. En una categoria de matematicas eso no es una
    excepcion legitima sino saltarse la comprobacion.
    """

    def pedir(self, exige):
        return generar_preguntas(
            materia='Matemáticas', categoria='Aritmética', nivel=3,
            cantidad=1, exige_expresion=exige,
        )

    @patch('apps.ia.cliente.completion')
    def test_sin_expresion_pasa_cuando_no_se_exige(self, doble):
        # Comprensión o Gramática no tienen expresión, y eso está bien.
        sin_expresion = dict(PREGUNTA_BUENA, expresion='', valores=[])
        doble.return_value = respuesta_falsa({'preguntas': [sin_expresion]})

        resultado = self.pedir(exige=False)

        self.assertEqual(resultado.preguntas[0].expresion, '')

    @patch('apps.ia.cliente.completion')
    def test_sin_expresion_se_rechaza_cuando_se_exige(self, doble):
        sin_expresion = dict(PREGUNTA_BUENA, expresion='', valores=[])
        doble.return_value = respuesta_falsa({'preguntas': [sin_expresion]})

        with self.assertRaises(ErrorRespuestaIA) as capturado:
            self.pedir(exige=True)

        self.assertIn('verificarla', str(capturado.exception))

    @patch('apps.ia.cliente.completion')
    def test_sin_valores_simbolicos_se_rechaza_cuando_se_exige(self, doble):
        sin_valores = dict(PREGUNTA_BUENA, valores=[])
        doble.return_value = respuesta_falsa({'preguntas': [sin_valores]})

        with self.assertRaises(ErrorRespuestaIA):
            self.pedir(exige=True)

    @patch('apps.ia.cliente.completion')
    def test_con_expresion_completa_pasa(self, doble):
        doble.return_value = respuesta_falsa(LOTE_BUENO)
        resultado = self.pedir(exige=True)
        self.assertEqual(resultado.preguntas[0].expresion, '2 + 3*4')
