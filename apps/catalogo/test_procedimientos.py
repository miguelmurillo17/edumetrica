"""Pruebas de la conversion del procedimiento entre pasos y texto."""

from django.test import SimpleTestCase

from .procedimientos import pasos_a_texto, texto_a_pasos


class PasosATextoTest(SimpleTestCase):
    """Unir la lista de pasos capturados en un solo texto numerado."""

    def test_numera_los_pasos_uno_por_linea(self):
        texto = pasos_a_texto(['Multiplicas.', 'Luego sumas.'])
        self.assertEqual(texto, '1. Multiplicas.\n2. Luego sumas.')

    def test_ignora_los_pasos_vacios(self):
        # Los renglones en blanco del formulario no cuentan.
        texto = pasos_a_texto(['Uno.', '   ', '', 'Dos.'])
        self.assertEqual(texto, '1. Uno.\n2. Dos.')

    def test_quita_la_numeracion_que_escribio_el_humano(self):
        # Si el profesor o el modelo ya numeraron, no se duplica.
        texto = pasos_a_texto(['1. Uno.', '2) Dos.', '3.- Tres.'])
        self.assertEqual(texto, '1. Uno.\n2. Dos.\n3. Tres.')

    def test_sin_pasos_devuelve_cadena_vacia(self):
        self.assertEqual(pasos_a_texto([]), '')
        self.assertEqual(pasos_a_texto(['', '  ']), '')


class TextoAPasosTest(SimpleTestCase):
    """Partir el texto guardado en la lista de pasos, sin numeracion."""

    def test_parte_por_lineas_y_quita_la_numeracion(self):
        pasos = texto_a_pasos('1. Multiplicas.\n2. Luego sumas.')
        self.assertEqual(pasos, ['Multiplicas.', 'Luego sumas.'])

    def test_un_procedimiento_en_prosa_es_un_solo_paso(self):
        # Lo que devuelve la IA en un parrafo entra como un unico paso, que el
        # profesor puede separar despues.
        prosa = 'Primero esto y luego lo otro.'
        self.assertEqual(texto_a_pasos(prosa), [prosa])

    def test_vacio_devuelve_lista_vacia(self):
        self.assertEqual(texto_a_pasos(''), [])
        self.assertEqual(texto_a_pasos(None), [])

    def test_ida_y_vuelta_es_estable(self):
        # Guardar y volver a leer no altera los pasos.
        pasos = ['Uno.', 'Dos.', 'Tres.']
        self.assertEqual(texto_a_pasos(pasos_a_texto(pasos)), pasos)
