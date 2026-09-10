"""
Pruebas del puente entre el catalogo y el modulo de inteligencia artificial.

No llaman al proveedor: se sustituye la funcion que genera. Lo que se
comprueba aqui es la parte que le toca al catalogo, y sobre todo la regla que
sostiene la propuesta: una pregunta generada nunca queda utilizable sin que
una persona la valide.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.ia.errores import ErrorProveedorIA
from apps.ia.esquemas import PreguntaGenerada, ResultadoGeneracion
from apps.usuarios.models import Persona

from .models import Categoria, Materia, Nivel, Pregunta, SolicitudGeneracion
from .servicios import generar_pregunta, lanzar_generacion, mensaje_de_espera


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
        self.assertEqual(solicitud.estado, SolicitudGeneracion.Estado.EXITOSA)
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
        self.assertEqual(solicitud.estado, SolicitudGeneracion.Estado.FALLIDA)
        self.assertIn('cuota', solicitud.mensaje_error)
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


class EstadoDeLaSolicitudTest(TestCase):
    """Lo que la pantalla de espera alcanza a ver mientras corre el hilo."""

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

    def crear_solicitud(self, **extras):
        return SolicitudGeneracion.objects.create(
            profesor=self.profesor, materia=self.materia,
            categoria=self.categoria, nivel=self.nivel, cantidad_pedida=1,
            **extras
        )

    @patch('apps.catalogo.servicios._guardar_pregunta')
    @patch('apps.catalogo.servicios.generar_preguntas')
    def test_nunca_queda_exitosa_sin_su_pregunta(self, doble, guardado):
        # La pantalla de espera deduce del estado que ya hay algo que revisar.
        # Si el estado se guardara antes que la pregunta, un fallo al guardarla
        # dejaria una solicitud exitosa y vacia para siempre, y el sondeo que
        # cayera en esa rendija veria un lote terminado sin nada dentro.
        doble.return_value = resultado_falso()
        guardado.side_effect = RuntimeError('la base de datos se cayo')

        with self.assertRaises(RuntimeError):
            generar_pregunta(
                profesor=self.profesor, categoria=self.categoria,
                nivel=self.nivel,
            )

        solicitud = SolicitudGeneracion.objects.get()
        self.assertEqual(Pregunta.objects.count(), 0)
        self.assertNotEqual(
            solicitud.estado, SolicitudGeneracion.Estado.EXITOSA
        )

    def test_mientras_el_hilo_puede_seguir_vivo_contesta_en_proceso(self):
        solicitud = self.crear_solicitud()
        self.assertEqual(mensaje_de_espera(solicitud)['estado'], 'en_proceso')

    @override_settings(AI_TIMEOUT=30, AI_MAX_RETRIES=1)
    def test_una_generacion_interrumpida_deja_de_esperarse(self):
        # El hilo muere con el proceso, asi que un reinicio del servidor a
        # media llamada dejaria a la pantalla contando segundos sin remedio.
        solicitud = self.crear_solicitud()
        SolicitudGeneracion.objects.filter(id=solicitud.id).update(
            fecha=timezone.now() - timedelta(minutes=10)
        )
        solicitud.refresh_from_db()

        situacion = mensaje_de_espera(solicitud)

        self.assertEqual(situacion['estado'], 'fallida')
        self.assertTrue(situacion['reintentable'])
        self.assertIn('se interrumpió', situacion['mensaje'])
        # Y queda anotado en la solicitud: de esta tabla salen los numeros del
        # capitulo de resultados y una fila en proceso para siempre los ensucia.
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, SolicitudGeneracion.Estado.FALLIDA)


@override_settings(AI_LIMITE_POR_HORA=2)
class TopeEnElServicioTest(TestCase):
    """El tope no puede depender de que la pantalla se acuerde de mirarlo."""

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

    @patch('apps.catalogo.servicios.threading.Thread')
    def test_al_llegar_al_tope_no_arranca_el_hilo(self, hilo):
        for _ in range(2):
            SolicitudGeneracion.objects.create(
                profesor=self.profesor, materia=self.materia,
                categoria=self.categoria, nivel=self.nivel, cantidad_pedida=1,
            )

        with self.assertRaises(ValueError):
            lanzar_generacion(
                profesor=self.profesor, categoria=self.categoria,
                nivel=self.nivel,
            )

        # Ni hilo ni solicitud nueva: la cuota es de la institucion y un
        # intento de mas ya la habria tocado.
        hilo.assert_not_called()
        self.assertEqual(SolicitudGeneracion.objects.count(), 2)
