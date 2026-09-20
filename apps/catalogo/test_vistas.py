"""
Pruebas de las pantallas de generacion y revision.

Ninguna llama al proveedor ni levanta el hilo de verdad: lo que se comprueba
aqui es lo que ve el profesor. Dos reglas importan mas que las demas y por eso
tienen prueba propia: que el texto crudo del proveedor nunca llegue a la
pantalla, y que el tope por hora cuente tambien los intentos fallidos.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.usuarios.models import Persona

from .models import (
    Categoria, Materia, Nivel, OpcionRespuesta, Pregunta, SolicitudGeneracion,
)


LLAVES_PUESTAS = {'gemini': 'una-llave-de-mentiras', 'groq': '', 'deepseek': ''}
LLAVES_VACIAS = {'gemini': '', 'groq': '', 'deepseek': ''}


class BaseCatalogoTest(TestCase):
    """Deja lista una institucion minima y un profesor con sesion iniciada."""

    def setUp(self):
        self.profesor = Persona.objects.create_user(
            correo='profesor@prueba.mx', nombre='Ana', apellido='Ruiz',
            password='Edumetrica2026', rol=Persona.Rol.PROFESOR,
        )
        self.materia = Materia.objects.create(
            nombre='Matemáticas', es_cuantitativa=True
        )
        self.categoria = Categoria.objects.create(
            materia=self.materia, nombre='Aritmética'
        )
        self.nivel = Nivel.objects.create(numero=2, nombre='Elemental')
        self.client.force_login(self.profesor)

    def crear_solicitud(self, **extras):
        return SolicitudGeneracion.objects.create(
            profesor=self.profesor, materia=self.materia,
            categoria=self.categoria, nivel=self.nivel, cantidad_pedida=1,
            **extras
        )

    def crear_pregunta(self, **extras):
        datos = {
            'materia': self.materia,
            'categoria': self.categoria,
            'nivel': self.nivel,
            'enunciado': '¿Cuánto es 2 + 3 por 4?',
            'procedimiento': 'Primero multiplicas y luego sumas.',
            'creada_por': self.profesor,
            'origen': Pregunta.Origen.IA,
            'estado': Pregunta.Estado.BORRADOR,
            'verificada_simbolicamente': True,
        }
        datos.update(extras)
        pregunta = Pregunta.objects.create(**datos)
        for posicion, texto in enumerate(['14', '20', '9', '24']):
            OpcionRespuesta.objects.create(
                pregunta=pregunta, texto=texto, es_correcta=(posicion == 0)
            )
        return pregunta


@override_settings(AI_LLAVES=LLAVES_PUESTAS)
class FormularioDeGeneracionTest(BaseCatalogoTest):
    """La pantalla que pide la categoria y el nivel."""

    def test_muestra_el_formulario(self):
        respuesta = self.client.get(reverse('catalogo:generar_pregunta'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Generar una pregunta')

    @patch('apps.catalogo.views.lanzar_generacion')
    def test_manda_a_la_pantalla_de_espera(self, doble):
        # No se espera al proveedor: la vista arranca el trabajo y redirige.
        solicitud = self.crear_solicitud()
        doble.return_value = solicitud

        respuesta = self.client.post(reverse('catalogo:generar_pregunta'), {
            'categoria': self.categoria.id, 'nivel': self.nivel.id,
        })

        self.assertRedirects(respuesta, reverse(
            'catalogo:esperar_generacion', args=[solicitud.id]
        ))
        self.assertEqual(doble.call_args.kwargs['categoria'], self.categoria)

    @override_settings(AI_LLAVES=LLAVES_VACIAS)
    def test_sin_llave_no_se_ofrece_la_pantalla(self):
        # Sin llave cada intento fallaria igual y el profesor no puede hacer
        # nada al respecto, asi que ni siquiera se le ofrece el formulario.
        respuesta = self.client.get(
            reverse('catalogo:generar_pregunta'), follow=True
        )
        self.assertContains(respuesta, 'no está configurada')

    @override_settings(AI_LLAVES=LLAVES_VACIAS)
    def test_sin_llave_el_boton_no_aparece_en_el_listado(self):
        respuesta = self.client.get(reverse('catalogo:lista_preguntas'))
        self.assertNotContains(respuesta, 'Generar con IA')

    def test_con_llave_el_boton_si_aparece(self):
        respuesta = self.client.get(reverse('catalogo:lista_preguntas'))
        self.assertContains(respuesta, 'Generar con IA')


@override_settings(AI_LLAVES=LLAVES_PUESTAS, AI_LIMITE_POR_HORA=3)
class TopePorProfesorTest(BaseCatalogoTest):
    """La cuota es de la institucion, no de cada usuario."""

    @patch('apps.catalogo.views.lanzar_generacion')
    def test_al_llegar_al_tope_ya_no_deja_generar(self, doble):
        for _ in range(3):
            self.crear_solicitud(estado=SolicitudGeneracion.Estado.EXITOSA)

        respuesta = self.client.post(reverse('catalogo:generar_pregunta'), {
            'categoria': self.categoria.id, 'nivel': self.nivel.id,
        }, follow=True)

        self.assertContains(respuesta, 'límite de 3 generaciones por hora')
        doble.assert_not_called()

    @patch('apps.catalogo.views.lanzar_generacion')
    def test_los_intentos_fallidos_tambien_cuentan(self, doble):
        # Si solo contaran los exitosos se podria insistir sin limite contra un
        # proveedor caido, que es justo el camino que mas se va a ver.
        for _ in range(3):
            self.crear_solicitud(estado=SolicitudGeneracion.Estado.FALLIDA)

        self.client.post(reverse('catalogo:generar_pregunta'), {
            'categoria': self.categoria.id, 'nivel': self.nivel.id,
        })

        doble.assert_not_called()

    @patch('apps.catalogo.views.lanzar_generacion')
    def test_las_solicitudes_viejas_ya_no_cuentan(self, doble):
        doble.return_value = self.crear_solicitud()
        viejas = [self.crear_solicitud() for _ in range(3)]
        # fecha se llena sola al crear, asi que se recorre a mano.
        SolicitudGeneracion.objects.filter(
            id__in=[solicitud.id for solicitud in viejas]
        ).update(fecha=timezone.now() - timedelta(hours=2))

        self.client.post(reverse('catalogo:generar_pregunta'), {
            'categoria': self.categoria.id, 'nivel': self.nivel.id,
        })

        doble.assert_called_once()

    def test_el_formulario_dice_cuantas_quedan(self):
        self.crear_solicitud()
        respuesta = self.client.get(reverse('catalogo:generar_pregunta'))
        self.assertEqual(respuesta.context['restantes'], 2)


@override_settings(AI_LLAVES=LLAVES_PUESTAS)
class SondeoDeGeneracionTest(BaseCatalogoTest):
    """Lo que contesta la pantalla de espera mientras corre el hilo."""

    def test_mientras_no_termina_contesta_en_proceso(self):
        solicitud = self.crear_solicitud()
        respuesta = self.client.get(reverse(
            'catalogo:estado_generacion', args=[solicitud.id]
        ))
        self.assertEqual(respuesta.json()['estado'], 'en_proceso')

    def test_al_terminar_entrega_la_pregunta(self):
        solicitud = self.crear_solicitud(
            estado=SolicitudGeneracion.Estado.EXITOSA
        )
        pregunta = self.crear_pregunta(solicitud=solicitud)

        respuesta = self.client.get(reverse(
            'catalogo:estado_generacion', args=[solicitud.id]
        ))

        self.assertEqual(respuesta.json()['estado'], 'lista')
        self.assertEqual(respuesta.json()['pregunta_id'], pregunta.id)

    def test_el_texto_crudo_del_proveedor_nunca_sale(self):
        # Es la regla de transparencia al reves: el profesor lee un mensaje que
        # explica de quien es el problema, y el volcado del proveedor se queda
        # en la bitacora. Si se colara, pareceria que el sistema se rompio.
        solicitud = self.crear_solicitud(
            estado=SolicitudGeneracion.Estado.FALLIDA,
            tipo_error='saturacion',
            mensaje_error='Google AI Studio está saturado en este momento.',
            detalle_error='{"error": {"code": 503, "status": "UNAVAILABLE"}}',
        )

        respuesta = self.client.get(reverse(
            'catalogo:estado_generacion', args=[solicitud.id]
        ))
        pantalla = self.client.get(reverse(
            'catalogo:esperar_generacion', args=[solicitud.id]
        ))

        self.assertEqual(respuesta.json()['estado'], 'fallida')
        self.assertIn('saturado', respuesta.json()['mensaje'])
        self.assertNotIn('UNAVAILABLE', respuesta.content.decode())
        self.assertNotContains(pantalla, 'UNAVAILABLE')
        self.assertContains(pantalla, 'saturado')

    def test_un_modelo_caducado_no_ofrece_reintentar(self):
        # Un identificador vencido es configuracion, no una falla pasajera:
        # reintentar solo repetiria el mismo error.
        solicitud = self.crear_solicitud(
            estado=SolicitudGeneracion.Estado.FALLIDA,
            tipo_error='modelo',
            mensaje_error='El modelo ya no está disponible.',
        )

        respuesta = self.client.get(reverse(
            'catalogo:estado_generacion', args=[solicitud.id]
        ))
        pantalla = self.client.get(reverse(
            'catalogo:esperar_generacion', args=[solicitud.id]
        ))

        self.assertFalse(respuesta.json()['reintentable'])
        self.assertNotContains(pantalla, 'Intentar de nuevo')
        self.assertContains(pantalla, 'Avisa al administrador')

    def test_una_saturacion_si_ofrece_reintentar(self):
        solicitud = self.crear_solicitud(
            estado=SolicitudGeneracion.Estado.FALLIDA,
            tipo_error='saturacion',
            mensaje_error='Está saturado en este momento.',
        )

        pantalla = self.client.get(reverse(
            'catalogo:esperar_generacion', args=[solicitud.id]
        ))

        self.assertContains(pantalla, 'Intentar de nuevo')

    def test_la_pantalla_de_espera_manda_a_revisar_cuando_ya_hay_pregunta(self):
        solicitud = self.crear_solicitud(
            estado=SolicitudGeneracion.Estado.EXITOSA
        )
        pregunta = self.crear_pregunta(solicitud=solicitud)

        respuesta = self.client.get(reverse(
            'catalogo:esperar_generacion', args=[solicitud.id]
        ))

        self.assertRedirects(respuesta, reverse(
            'catalogo:revisar_pregunta', args=[pregunta.id]
        ))


class RevisarPreguntaTest(BaseCatalogoTest):
    """La compuerta humana: validar o descartar lo que propuso el modelo."""

    def test_muestra_el_dictamen_aprobado(self):
        pregunta = self.crear_pregunta()
        respuesta = self.client.get(reverse(
            'catalogo:revisar_pregunta', args=[pregunta.id]
        ))
        self.assertContains(respuesta, 'La comprobación matemática la aprobó')
        self.assertContains(respuesta, 'Primero multiplicas')

    def test_muestra_el_motivo_cuando_el_verificador_la_rechazo(self):
        # Mostrarlo es lo que le da al profesor confianza en que el sistema si
        # revisa lo que el modelo propone.
        pregunta = self.crear_pregunta(
            estado=Pregunta.Estado.DESCARTADA,
            verificada_simbolicamente=False,
            motivo_rechazo='La opción marcada como correcta no coincide.',
        )

        respuesta = self.client.get(reverse(
            'catalogo:revisar_pregunta', args=[pregunta.id]
        ))

        self.assertContains(respuesta, 'no coincide')

    def test_validar_la_vuelve_utilizable(self):
        pregunta = self.crear_pregunta()

        self.client.post(
            reverse('catalogo:resolver_pregunta', args=[pregunta.id]),
            {'accion': 'validar'},
        )

        pregunta.refresh_from_db()
        self.assertEqual(pregunta.estado, Pregunta.Estado.VALIDADA)
        self.assertTrue(pregunta.es_utilizable)

    def test_descartar_la_deja_fuera(self):
        pregunta = self.crear_pregunta()

        self.client.post(
            reverse('catalogo:resolver_pregunta', args=[pregunta.id]),
            {'accion': 'descartar'},
        )

        pregunta.refresh_from_db()
        self.assertEqual(pregunta.estado, Pregunta.Estado.DESCARTADA)
        self.assertEqual(Pregunta.objects.utilizables().count(), 0)

    def test_rescatar_una_rechazada_conserva_el_dictamen(self):
        # El profesor puede validar una pregunta que el verificador rechazo,
        # porque hay rechazos de formato que no son errores de matematicas.
        # Lo que no se toca es la marca: en el capitulo de resultados tiene que
        # seguir distinguiendose lo que rechazo la maquina de lo que rescato
        # una persona.
        pregunta = self.crear_pregunta(
            estado=Pregunta.Estado.DESCARTADA,
            verificada_simbolicamente=False,
            motivo_rechazo='La respuesta trae unidades.',
        )

        self.client.post(
            reverse('catalogo:resolver_pregunta', args=[pregunta.id]),
            {'accion': 'validar'},
        )

        pregunta.refresh_from_db()
        self.assertEqual(pregunta.estado, Pregunta.Estado.VALIDADA)
        self.assertFalse(pregunta.verificada_simbolicamente)
        self.assertIn('unidades', pregunta.motivo_rechazo)

    def test_una_accion_desconocida_no_cambia_nada(self):
        pregunta = self.crear_pregunta()

        self.client.post(
            reverse('catalogo:resolver_pregunta', args=[pregunta.id]),
            {'accion': 'lo-que-sea'},
        )

        pregunta.refresh_from_db()
        self.assertEqual(pregunta.estado, Pregunta.Estado.BORRADOR)

    def test_no_se_resuelve_con_una_peticion_de_lectura(self):
        pregunta = self.crear_pregunta()
        respuesta = self.client.get(
            reverse('catalogo:resolver_pregunta', args=[pregunta.id])
        )
        self.assertEqual(respuesta.status_code, 405)

    def test_otro_profesor_puede_ayudar_a_revisarla(self):
        # Quien la genero es el responsable, pero no el unico que puede
        # revisarla: la pantalla lo dice en lugar de negar el acceso.
        pregunta = self.crear_pregunta()
        otro = Persona.objects.create_user(
            correo='otro@prueba.mx', nombre='Luis', apellido='Paz',
            password='Edumetrica2026', rol=Persona.Rol.PROFESOR,
        )
        self.client.force_login(otro)

        respuesta = self.client.get(reverse(
            'catalogo:revisar_pregunta', args=[pregunta.id]
        ))

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context['es_mia'])
        self.assertContains(respuesta, 'Ana Ruiz')

    def test_corregir_un_borrador_regresa_a_la_revision(self):
        pregunta = self.crear_pregunta()

        respuesta = self.client.post(
            reverse('catalogo:editar_pregunta', args=[pregunta.id]),
            self.datos_de_edicion(pregunta),
        )

        self.assertRedirects(respuesta, reverse(
            'catalogo:revisar_pregunta', args=[pregunta.id]
        ))

    def test_editar_arma_el_procedimiento_numerado(self):
        # Los pasos que se capturan por separado se guardan como un solo texto,
        # numerado y un paso por linea.
        pregunta = self.crear_pregunta()

        self.client.post(
            reverse('catalogo:editar_pregunta', args=[pregunta.id]),
            self.datos_de_edicion(pregunta),
        )

        pregunta.refresh_from_db()
        self.assertEqual(
            pregunta.procedimiento,
            '1. Primero multiplicas.\n2. Luego sumas.',
        )

    def datos_de_edicion(self, pregunta):
        """Arma el envio completo del formulario de la pregunta y sus opciones."""
        datos = {
            'categoria': self.categoria.id,
            'nivel': self.nivel.id,
            'enunciado': 'Un enunciado corregido a mano.',
            # El procedimiento ahora se captura por pasos, un valor por renglon.
            'paso': ['Primero multiplicas.', 'Luego sumas.'],
            'opciones-TOTAL_FORMS': '4',
            'opciones-INITIAL_FORMS': '4',
            'opciones-MIN_NUM_FORMS': '0',
            'opciones-MAX_NUM_FORMS': '4',
        }
        for posicion, opcion in enumerate(pregunta.opciones.all()):
            datos[f'opciones-{posicion}-id'] = opcion.id
            datos[f'opciones-{posicion}-pregunta'] = pregunta.id
            datos[f'opciones-{posicion}-texto'] = opcion.texto
            if opcion.es_correcta:
                datos[f'opciones-{posicion}-es_correcta'] = 'on'
        return datos


class FiltroDelListadoTest(BaseCatalogoTest):
    """El filtro de borradores pendientes de revision."""

    def setUp(self):
        super().setUp()
        self.borrador = self.crear_pregunta()
        self.validada = self.crear_pregunta(
            estado=Pregunta.Estado.VALIDADA, enunciado='Una ya validada.'
        )

    def test_sin_filtro_salen_todas(self):
        respuesta = self.client.get(reverse('catalogo:lista_preguntas'))
        self.assertEqual(len(respuesta.context['preguntas']), 2)

    def test_filtra_los_borradores(self):
        respuesta = self.client.get(
            reverse('catalogo:lista_preguntas'), {'estado': 'borrador'}
        )
        self.assertEqual(
            list(respuesta.context['preguntas']), [self.borrador]
        )

    def test_cuenta_los_borradores_pendientes(self):
        respuesta = self.client.get(reverse('catalogo:lista_preguntas'))
        self.assertEqual(respuesta.context['borradores'], 1)

    def test_un_estado_inventado_se_ignora(self):
        respuesta = self.client.get(
            reverse('catalogo:lista_preguntas'), {'estado': 'lo-que-sea'}
        )
        self.assertEqual(len(respuesta.context['preguntas']), 2)
        self.assertEqual(respuesta.context['estado'], '')

    def test_filtra_por_origen(self):
        # Las dos de setUp son de IA; se agrega una capturada a mano.
        manual = self.crear_pregunta(
            origen=Pregunta.Origen.MANUAL, enunciado='Capturada a mano.'
        )
        respuesta = self.client.get(
            reverse('catalogo:lista_preguntas'), {'origen': 'manual'}
        )
        self.assertEqual(list(respuesta.context['preguntas']), [manual])

    def test_filtra_por_materia(self):
        otra_materia = Materia.objects.create(nombre='Física')
        otra_categoria = Categoria.objects.create(
            materia=otra_materia, nombre='Cinemática'
        )
        de_fisica = self.crear_pregunta(
            materia=otra_materia, categoria=otra_categoria,
            enunciado='Una de física.'
        )
        respuesta = self.client.get(
            reverse('catalogo:lista_preguntas'), {'materia': otra_materia.id}
        )
        self.assertEqual(list(respuesta.context['preguntas']), [de_fisica])

    def test_filtra_por_nivel(self):
        otro_nivel = Nivel.objects.create(numero=5, nombre='Avanzado')
        avanzada = self.crear_pregunta(
            nivel=otro_nivel, enunciado='Una avanzada.'
        )
        respuesta = self.client.get(
            reverse('catalogo:lista_preguntas'), {'nivel': otro_nivel.id}
        )
        self.assertEqual(list(respuesta.context['preguntas']), [avanzada])

    def test_ordena_por_nivel_descendente(self):
        otro_nivel = Nivel.objects.create(numero=6, nombre='Superior')
        superior = self.crear_pregunta(
            nivel=otro_nivel, enunciado='La del nivel mas alto.'
        )
        respuesta = self.client.get(
            reverse('catalogo:lista_preguntas'),
            {'orden': 'nivel', 'dir': 'desc'},
        )
        # El nivel 6 (recien creado) debe quedar antes que los de nivel 2.
        self.assertEqual(respuesta.context['preguntas'][0], superior)
        self.assertEqual(respuesta.context['direccion'], 'desc')

    def test_un_orden_inventado_se_ignora(self):
        respuesta = self.client.get(
            reverse('catalogo:lista_preguntas'), {'orden': 'lo-que-sea'}
        )
        self.assertEqual(respuesta.context['orden'], '')
