"""
Pruebas del puente entre el catalogo y el modulo de inteligencia artificial.

No llaman al proveedor: se sustituye la funcion que genera. Lo que se
comprueba aqui es la parte que le toca al catalogo, y sobre todo la regla que
sostiene la propuesta: una pregunta generada nunca queda utilizable sin que
una persona la valide.
"""

from unittest.mock import patch

from django.test import TestCase

from apps.ia.errores import ErrorProveedorIA
from apps.ia.esquemas import PreguntaGenerada, ResultadoGeneracion
from apps.usuarios.models import Persona

from .models import Categoria, Materia, Nivel, Pregunta, SolicitudGeneracion
from .servicios import generar_pregunta


def resultado_falso(expresion='2 + 3*4', valores=None, indice=0):
    """Arma lo que devolveria el modulo de IA, sin llamar al proveedor."""
    return ResultadoGeneracion(
        preguntas=[PreguntaGenerada(
            enunciado='¿Cuánto es 2 + 3 por 4?',
            opciones=['14', '20', '9', '24'],
            indice_correcto=indice,
            procedimiento='Primero multiplicas y luego sumas.',
            expresion=expresion,
            valores=valores if valores is not None else ['14', '20', '9', '24'],
        )],
        modelo='gemini/gemini-3.6-flash',
        proveedor='gemini',
        tokens_entrada=771,
        tokens_salida=976,
    )


class GenerarPreguntaTest(TestCase):
    """El camino completo: generar, verificar y guardar."""

    def setUp(self):
        self.profesor = Persona.objects.create_user(
            correo='profesor@prueba.mx', nombre='Ana', apellido='Ruiz',
            password='x', rol=Persona.Rol.PROFESOR,
        )
        self.materia = Materia.objects.create(
            nombre='Matemáticas', es_cuantitativa=True
        )
        self.categoria = Categoria.objects.create(
            materia=self.materia, nombre='Aritmética'
        )
        self.nivel = Nivel.objects.create(numero=2, nombre='Elemental')

    def generar(self, **extras):
        return generar_pregunta(
            profesor=self.profesor, categoria=self.categoria, nivel=self.nivel,
            **extras
        )

    @patch('apps.catalogo.servicios.generar_preguntas')
    def test_guarda_la_pregunta_con_sus_opciones(self, doble):
        doble.return_value = resultado_falso()

        pregunta, dictamen = self.generar()

        self.assertTrue(dictamen.aprobada)
        self.assertEqual(pregunta.enunciado, '¿Cuánto es 2 + 3 por 4?')
        self.assertEqual(pregunta.opciones.count(), 4)
        self.assertEqual(pregunta.opciones.filter(es_correcta=True).count(), 1)
        self.assertEqual(
            pregunta.opciones.get(es_correcta=True).texto, '14'
        )
        self.assertTrue(pregunta.procedimiento)
        self.assertEqual(pregunta.origen, Pregunta.Origen.IA)

    @patch('apps.catalogo.servicios.generar_preguntas')
    def test_una_pregunta_generada_nunca_nace_utilizable(self, doble):
        # Es la regla que sostiene toda la propuesta: aunque el verificador la
        # apruebe, no puede entrar a una evaluacion sin que alguien la valide.
        doble.return_value = resultado_falso()

        pregunta, dictamen = self.generar()

        self.assertTrue(dictamen.aprobada)
        self.assertEqual(pregunta.estado, Pregunta.Estado.BORRADOR)
        self.assertFalse(pregunta.es_utilizable)
        self.assertEqual(Pregunta.objects.utilizables().count(), 0)

    @patch('apps.catalogo.servicios.generar_preguntas')
    def test_la_que_rechaza_el_verificador_queda_descartada(self, doble):
        # La expresion da 14 pero se marco el 20 como correcto.
        doble.return_value = resultado_falso(indice=1)

        pregunta, dictamen = self.generar()

        self.assertFalse(dictamen.aprobada)
        self.assertEqual(pregunta.estado, Pregunta.Estado.DESCARTADA)
        self.assertIn('no coincide', pregunta.motivo_rechazo)
        self.assertFalse(pregunta.verificada_simbolicamente)

    @patch('apps.catalogo.servicios.generar_preguntas')
    def test_registra_el_consumo_de_tokens(self, doble):
        # Sin esto los tokens solo existirian en la bitacora de la consola y se
        # perderian; son el dato del capitulo de resultados.
        doble.return_value = resultado_falso()

        self.generar()

        solicitud = SolicitudGeneracion.objects.get()
        self.assertEqual(solicitud.tokens_entrada, 771)
        self.assertEqual(solicitud.tokens_salida, 976)
        self.assertEqual(solicitud.modelo, 'gemini/gemini-3.6-flash')
        self.assertTrue(solicitud.exitosa)
        self.assertEqual(solicitud.cantidad_pedida, 1)
        self.assertEqual(solicitud.cantidad_recibida, 1)
        self.assertEqual(solicitud.cantidad_aprobada, 1)

    @patch('apps.catalogo.servicios.generar_preguntas')
    def test_la_solicitud_fallida_sobrevive_al_error(self, doble):
        # El registro del fallo no puede irse con la transaccion revertida, o
        # se perderia cuantos intentos hicieron falta para armar el banco.
        doble.side_effect = ErrorProveedorIA('se agotó la cuota', proveedor='gemini')

        with self.assertRaises(ErrorProveedorIA):
            self.generar()

        solicitud = SolicitudGeneracion.objects.get()
        self.assertFalse(solicitud.exitosa)
        self.assertIn('cuota', solicitud.detalle_error)
        self.assertEqual(Pregunta.objects.count(), 0)

    @patch('apps.catalogo.servicios.generar_preguntas')
    def test_exige_expresion_en_materia_cuantitativa(self, doble):
        doble.return_value = resultado_falso()
        self.generar()
        self.assertTrue(doble.call_args.kwargs['exige_expresion'])

    @patch('apps.catalogo.servicios.generar_preguntas')
    def test_no_la_exige_en_materia_que_no_lo_es(self, doble):
        self.materia.es_cuantitativa = False
        self.materia.save()
        doble.return_value = resultado_falso(expresion='', valores=[])

        pregunta, dictamen = self.generar()

        self.assertFalse(doble.call_args.kwargs['exige_expresion'])
        # Sin expresion el verificador no aplica, y eso queda registrado como
        # nulo en lugar de como aprobada.
        self.assertFalse(dictamen.aplica)
        self.assertIsNone(pregunta.verificada_simbolicamente)
        # Aun asi nace en borrador: la revisa una persona.
        self.assertEqual(pregunta.estado, Pregunta.Estado.BORRADOR)

    @patch('apps.catalogo.servicios.generar_preguntas')
    def test_la_pregunta_queda_ligada_a_su_solicitud(self, doble):
        doble.return_value = resultado_falso()

        pregunta, _ = self.generar()

        solicitud = SolicitudGeneracion.objects.get()
        self.assertEqual(pregunta.solicitud, solicitud)
        # Todavia no la valida nadie.
        self.assertEqual(solicitud.cantidad_validada, 0)

        pregunta.estado = Pregunta.Estado.VALIDADA
        pregunta.save()
        self.assertEqual(solicitud.cantidad_validada, 1)
