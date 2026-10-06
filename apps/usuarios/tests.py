"""
Pruebas del acceso al sistema: el modelo Persona, el inicio de sesion por
correo, el reparto a cada panel segun el rol y el restablecimiento de la
contrasena.

Dos reglas del proyecto se comprueban aqui porque no son evidentes y romperlas
deja a alguien fuera del sistema sin dar explicaciones: que se entra con el
correo y no con un nombre de usuario, y que EMAIL_FIELD apunte a ese mismo
campo, o Django buscaria uno llamado "email" -que este modelo no tiene- y el
restablecimiento no encontraria a nadie.
"""

import re
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Notificacion, Persona

# Las reglas de contrasena se apagan en desarrollo (ver settings.py); las
# pruebas que las comprueban las fijan aqui para no depender de DEBUG.
REGLAS_CONTRASENA = [
    {'NAME': 'apps.usuarios.validadores.SimilitudConDatosPersonales'},
    {'NAME': 'apps.usuarios.validadores.LargoMinimo'},
    {'NAME': 'apps.usuarios.validadores.ContrasenaComun'},
    {'NAME': 'apps.usuarios.validadores.SoloNumeros'},
]


CLAVE = 'Edumetrica2026'


class PersonaTest(TestCase):
    """El modelo de usuario y su administrador."""

    def crear(self, **extras):
        datos = {
            'correo': 'alguien@edumetrica.mx',
            'nombre': 'Beto',
            'apellido': 'Lara',
            'password': CLAVE,
        }
        datos.update(extras)
        return Persona.objects.create_user(**datos)

    def test_la_contrasena_se_guarda_cifrada(self):
        persona = self.crear()

        self.assertNotEqual(persona.password, CLAVE)
        self.assertTrue(persona.check_password(CLAVE))

    def test_sin_correo_no_se_puede_crear(self):
        # El correo no es un dato mas: es con lo que se inicia sesion.
        with self.assertRaises(ValueError):
            self.crear(correo='')

    def test_el_correo_se_normaliza(self):
        persona = self.crear(correo='Alguien@EDUMETRICA.MX')

        self.assertEqual(persona.correo, 'Alguien@edumetrica.mx')

    def test_el_correo_no_se_repite(self):
        self.crear()
        with self.assertRaises(Exception):
            self.crear(nombre='Otro')

    def test_el_rol_por_omision_es_alumno(self):
        # Es el rol sin privilegios: si alguna alta olvidara ponerlo, la
        # persona entra con los permisos mas bajos y no con los mas altos.
        self.assertEqual(self.crear().rol, Persona.Rol.ALUMNO)

    def test_el_superusuario_nace_administrador_y_con_acceso_al_panel(self):
        jefe = Persona.objects.create_superuser(
            correo='jefe@edumetrica.mx', nombre='Caro', apellido='Solís',
            password=CLAVE,
        )

        self.assertEqual(jefe.rol, Persona.Rol.ADMINISTRADOR)
        self.assertTrue(jefe.is_staff)
        self.assertTrue(jefe.is_superuser)

    def test_los_atajos_de_rol(self):
        alumno = self.crear()
        profesor = self.crear(
            correo='p@edumetrica.mx', rol=Persona.Rol.PROFESOR
        )
        administrador = self.crear(
            correo='a@edumetrica.mx', rol=Persona.Rol.ADMINISTRADOR
        )

        self.assertTrue(alumno.es_alumno)
        self.assertTrue(profesor.es_profesor)
        self.assertTrue(administrador.es_administrador)
        self.assertFalse(alumno.es_profesor)

    def test_nombre_completo(self):
        self.assertEqual(self.crear().nombre_completo, 'Lara Beto')

    def test_se_entra_con_el_correo_y_no_con_un_usuario(self):
        # Las dos constantes tienen que apuntar al correo. La segunda es la
        # que usa el restablecimiento para encontrar a la persona.
        self.assertEqual(get_user_model().USERNAME_FIELD, 'correo')
        self.assertEqual(get_user_model().EMAIL_FIELD, 'correo')

    def test_rechaza_fecha_nacimiento_hace_mas_de_80_anos(self):
        # Más de 80 años atrás debe ser rechazado.
        hace_80_anos_y_un_dia = date.today() - timedelta(days=80*365 + 1)
        persona = Persona(
            correo='viejo@edumetrica.mx',
            nombre='Beto',
            apellido='Lara',
            fecha_nacimiento=hace_80_anos_y_un_dia,
        )
        with self.assertRaises(ValidationError):
            persona.full_clean()

    def test_permite_fecha_nacimiento_hace_menos_de_80_anos(self):
        # Menos de 80 años atrás debe ser permitido.
        hace_79_anos = date.today() - timedelta(days=79*365)
        persona = Persona(
            correo='joven@edumetrica.mx',
            nombre='Beto',
            apellido='Lara',
            fecha_nacimiento=hace_79_anos,
        )
        try:
            persona.full_clean()
        except ValidationError as e:
            if 'fecha_nacimiento' in e.error_dict:
                self.fail('No debería rechazar fecha de nacimiento hace menos de 80 años')

    def test_permite_fecha_nacimiento_exactamente_80_anos(self):
        # Exactamente 80 años atrás debe ser permitido.
        hace_80_anos = date.today() - timedelta(days=80*365)
        persona = Persona(
            correo='exacto@edumetrica.mx',
            nombre='Beto',
            apellido='Lara',
            fecha_nacimiento=hace_80_anos,
        )
        try:
            persona.full_clean()
        except ValidationError as e:
            if 'fecha_nacimiento' in e.error_dict:
                self.fail('No debería rechazar fecha de nacimiento exactamente hace 80 años')

    def test_permite_sin_fecha_nacimiento(self):
        # Sin fecha de nacimiento debe ser permitido (campo es opcional).
        persona = Persona(
            correo='sin_fecha@edumetrica.mx',
            nombre='Beto',
            apellido='Lara',
            fecha_nacimiento=None,
        )
        try:
            persona.full_clean()
        except ValidationError as e:
            if 'fecha_nacimiento' in e.error_dict:
                self.fail('No debería rechazar sin fecha de nacimiento')


class InicioSesionTest(TestCase):
    """La pantalla de acceso."""

    def setUp(self):
        self.persona = Persona.objects.create_user(
            correo='alumno@edumetrica.mx', nombre='Beto', apellido='Lara',
            password=CLAVE, rol=Persona.Rol.ALUMNO,
        )

    def entrar(self, **extras):
        datos = {'username': 'alumno@edumetrica.mx', 'password': CLAVE}
        datos.update(extras)
        return self.client.post(reverse('usuarios:inicio_sesion'), datos)

    def test_entra_con_su_correo(self):
        respuesta = self.entrar()

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)

    def test_la_contrasena_equivocada_no_entra(self):
        respuesta = self.entrar(password='otra-cosa')

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_un_correo_que_no_existe_no_entra(self):
        respuesta = self.entrar(username='nadie@edumetrica.mx')

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_una_persona_dada_de_baja_no_entra(self):
        self.persona.is_active = False
        self.persona.save()

        self.entrar()

        self.assertNotIn('_auth_user_id', self.client.session)

    def test_la_pantalla_pide_el_correo_con_todas_sus_letras(self):
        respuesta = self.client.get(reverse('usuarios:inicio_sesion'))

        self.assertContains(respuesta, 'Correo electrónico')

    def test_quien_ya_entro_no_vuelve_a_ver_la_pantalla(self):
        self.client.force_login(self.persona)

        respuesta = self.client.get(reverse('usuarios:inicio_sesion'))

        self.assertEqual(respuesta.status_code, 302)

    def test_salir_cierra_la_sesion(self):
        self.client.force_login(self.persona)

        self.client.post(reverse('usuarios:cerrar_sesion'))

        self.assertNotIn('_auth_user_id', self.client.session)


class RepartoPorRolTest(TestCase):
    """La direccion de entrada manda a cada quien a su panel."""

    def crear_y_entrar(self, rol, **extras):
        persona = Persona.objects.create_user(
            correo=f'{rol}@edumetrica.mx', nombre='Ana', apellido='Ruiz',
            password=CLAVE, rol=rol, **extras
        )
        self.client.force_login(persona)
        return persona

    def test_el_alumno_va_a_su_panel(self):
        self.crear_y_entrar(Persona.Rol.ALUMNO)

        respuesta = self.client.get(reverse('usuarios:inicio'))

        self.assertRedirects(respuesta, reverse('evaluaciones:panel_alumno'))

    def test_el_profesor_va_al_suyo(self):
        self.crear_y_entrar(Persona.Rol.PROFESOR)

        respuesta = self.client.get(reverse('usuarios:inicio'))

        self.assertRedirects(respuesta, reverse('evaluaciones:panel_profesor'))

    def test_el_administrador_va_a_su_panel(self):
        self.crear_y_entrar(Persona.Rol.ADMINISTRADOR)

        respuesta = self.client.get(reverse('usuarios:inicio'))

        self.assertRedirects(respuesta, reverse('usuarios:panel_administrador'))

    def test_el_superusuario_elige_entre_los_tres(self):
        # No se le manda a uno porque puede trabajar desde cualquiera.
        jefe = Persona.objects.create_superuser(
            correo='jefe@edumetrica.mx', nombre='Caro', apellido='Solís',
            password=CLAVE,
        )
        self.client.force_login(jefe)

        respuesta = self.client.get(reverse('usuarios:inicio'))

        self.assertEqual(respuesta.status_code, 200)

    def test_sin_sesion_manda_a_la_pantalla_de_acceso(self):
        respuesta = self.client.get(reverse('usuarios:inicio'))

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse('usuarios:inicio_sesion'), respuesta.url)


class RestablecerContrasenaTest(TestCase):
    """Los cuatro pasos para recuperar el acceso."""

    def setUp(self):
        self.persona = Persona.objects.create_user(
            correo='alumno@edumetrica.mx', nombre='Beto', apellido='Lara',
            password=CLAVE, rol=Persona.Rol.ALUMNO,
        )

    def pedir(self, correo='alumno@edumetrica.mx'):
        return self.client.post(reverse('usuarios:restablecer'), {'email': correo})

    def enlace_del_mensaje(self):
        """Saca del correo la direccion con el identificador y el token."""
        cuerpo = mail.outbox[0].body
        return re.search(r'/restablecer/[^/]+/[^/\s]+/', cuerpo).group(0)

    @override_settings(SITIO_URL='https://edumetrica.mx')
    def test_el_enlace_apunta_al_dominio_configurado(self):
        """El correo no debe heredar el dominio de la peticion que llego.

        Django arma el enlace con el Host de la peticion, asi que sin esto el
        mensaje saldria apuntando a donde corre el servidor -127.0.0.1 si la
        solicitud se hizo desde ahi- y la persona no podria entrar.
        """
        self.pedir()

        cuerpo = mail.outbox[0].body
        self.assertIn(f'https://edumetrica.mx{self.enlace_del_mensaje()}', cuerpo)
        self.assertNotIn('testserver', cuerpo)

    @override_settings(SITIO_URL='http://127.0.0.1:8000')
    def test_respeta_el_protocolo_de_la_configuracion(self):
        """En desarrollo el sitio no va cifrado y el enlace debe decir http."""
        self.pedir()

        self.assertIn(
            f'http://127.0.0.1:8000{self.enlace_del_mensaje()}',
            mail.outbox[0].body,
        )

    def test_manda_el_mensaje_y_avisa(self):
        respuesta = self.pedir()

        self.assertRedirects(
            respuesta, reverse('usuarios:restablecer_enviado')
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_el_mensaje_llega_al_correo_de_la_persona(self):
        # Es la prueba de que EMAIL_FIELD esta bien puesto: sin el, Django
        # buscaria un campo "email" que Persona no tiene y no mandaria nada.
        self.pedir()

        self.assertEqual(mail.outbox[0].to, ['alumno@edumetrica.mx'])
        self.assertIn('Edumétrica', mail.outbox[0].body)

    def test_un_correo_desconocido_no_delata_que_no_existe(self):
        # Contestar distinto permitiria averiguar quien tiene cuenta.
        respuesta = self.pedir('nadie@edumetrica.mx')

        self.assertRedirects(
            respuesta, reverse('usuarios:restablecer_enviado')
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_el_enlace_permite_elegir_una_contrasena_nueva(self):
        self.pedir()
        nueva = 'Trigonometria2027'

        # El enlace redirige a la pantalla donde se captura la contrasena.
        paso = self.client.get(self.enlace_del_mensaje(), follow=True)
        respuesta = self.client.post(paso.redirect_chain[-1][0], {
            'new_password1': nueva, 'new_password2': nueva,
        })

        self.assertRedirects(respuesta, reverse('usuarios:restablecer_listo'))
        self.persona.refresh_from_db()
        self.assertTrue(self.persona.check_password(nueva))
        self.assertFalse(self.persona.check_password(CLAVE))

    def test_el_enlace_sirve_una_sola_vez(self):
        self.pedir()
        enlace = self.enlace_del_mensaje()
        nueva = 'Trigonometria2027'

        paso = self.client.get(enlace, follow=True)
        self.client.post(paso.redirect_chain[-1][0], {
            'new_password1': nueva, 'new_password2': nueva,
        })

        # El mismo enlace, ya usado, no debe volver a servir.
        segundo = self.client.get(enlace, follow=True)
        self.assertContains(segundo, 'Enlace vencido')

    def test_un_enlace_inventado_no_sirve(self):
        identificador = urlsafe_base64_encode(force_bytes(self.persona.pk))

        respuesta = self.client.get(
            reverse('usuarios:restablecer_confirmar', kwargs={
                'uidb64': identificador, 'token': 'token-inventado',
            }),
            follow=True,
        )

        self.assertContains(respuesta, 'Enlace vencido')

    @override_settings(AUTH_PASSWORD_VALIDATORS=REGLAS_CONTRASENA)
    def test_una_contrasena_nueva_invalida_se_rechaza(self):
        self.pedir()

        paso = self.client.get(self.enlace_del_mensaje(), follow=True)
        respuesta = self.client.post(paso.redirect_chain[-1][0], {
            'new_password1': '12345678', 'new_password2': '12345678',
        })

        self.assertEqual(respuesta.status_code, 200)
        self.persona.refresh_from_db()
        self.assertTrue(self.persona.check_password(CLAVE))

    def test_el_token_lo_reconoce_el_generador_de_django(self):
        self.assertTrue(default_token_generator.check_token(
            self.persona, default_token_generator.make_token(self.persona)
        ))


@override_settings(AUTH_PASSWORD_VALIDATORS=REGLAS_CONTRASENA)
class ValidadoresTest(TestCase):
    """Los mensajes de las reglas de contrasena, que tutean a la persona."""

    def setUp(self):
        self.persona = Persona.objects.create_user(
            correo='beto.lara@edumetrica.mx', nombre='Beto', apellido='Lara',
            password=CLAVE,
        )

    def motivo(self, contrasena):
        with self.assertRaises(ValidationError) as capturado:
            validate_password(contrasena, self.persona)
        return ' '.join(capturado.exception.messages)

    def test_rechaza_la_muy_corta(self):
        self.assertIn('muy corta', self.motivo('Ab3d'))

    def test_rechaza_la_de_puros_numeros(self):
        self.assertIn('solo números', self.motivo('84726150'))

    def test_rechaza_la_demasiado_comun(self):
        self.assertIn('demasiado común', self.motivo('password'))

    def test_rechaza_la_parecida_a_los_datos_de_la_persona(self):
        # La regla es la de Django y solo se le cambio el texto: compara la
        # contrasena completa contra cada dato completo, asi que salta con el
        # correo entero y no con variaciones como "betolara2026", que si pasan.
        self.assertIn('datos personales', self.motivo('beto.lara@edumetrica.mx'))

    def test_los_mensajes_tutean(self):
        # Django los trae hablando de usted; el resto del sistema tutea y las
        # dos formas mezcladas en la misma pantalla se notan.
        motivo = self.motivo('Ab3d')

        self.assertIn('Tu contraseña', motivo)
        self.assertNotIn('usted', motivo.lower())

    def test_una_buena_pasa(self):
        self.assertIsNone(validate_password('Trigonometria2027', self.persona))


class NotificacionesTest(TestCase):
    """La campanita de la barra superior y la lista de avisos."""

    def setUp(self):
        self.persona = Persona.objects.create_user(
            correo='alumno@prueba.mx', nombre='Beto', apellido='Lara',
            password='Edumetrica2026', rol=Persona.Rol.ALUMNO,
        )
        self.otra = Persona.objects.create_user(
            correo='otra@prueba.mx', nombre='Ana', apellido='Ruiz',
            password='Edumetrica2026', rol=Persona.Rol.ALUMNO,
        )
        self.client.force_login(self.persona)

    def crear_aviso(self, persona=None, **extras):
        datos = {
            'persona': persona or self.persona,
            'titulo': 'Nueva evaluación programada',
            'descripcion': 'Diagnóstico de Matemáticas.',
            'url': '/alumno/',
        }
        datos.update(extras)
        return Notificacion.objects.create(**datos)

    def abrir(self, aviso):
        return self.client.get(
            reverse('usuarios:abrir_notificacion', args=[aviso.id])
        )

    def test_la_campanita_cuenta_las_sin_leer(self):
        self.crear_aviso()
        self.crear_aviso()
        self.crear_aviso(estado=Notificacion.Estado.LEIDA)

        respuesta = self.client.get(reverse('usuarios:notificaciones'))

        self.assertEqual(respuesta.context['notificaciones_sin_leer'], 2)

    def test_la_campanita_no_cuenta_las_de_otra_persona(self):
        self.crear_aviso(persona=self.otra)

        respuesta = self.client.get(reverse('usuarios:notificaciones'))

        self.assertEqual(respuesta.context['notificaciones_sin_leer'], 0)

    def test_la_campanita_solo_trae_las_cinco_mas_recientes(self):
        for _ in range(7):
            self.crear_aviso()

        respuesta = self.client.get(reverse('usuarios:notificaciones'))

        self.assertEqual(len(respuesta.context['notificaciones_recientes']), 5)

    def test_abrirla_la_marca_leida_y_lleva_a_su_destino(self):
        aviso = self.crear_aviso()

        respuesta = self.abrir(aviso)

        self.assertRedirects(respuesta, '/alumno/')
        aviso.refresh_from_db()
        self.assertEqual(aviso.estado, Notificacion.Estado.LEIDA)
        self.assertIsNotNone(aviso.fecha_lectura)

    def test_una_direccion_de_fuera_no_saca_del_sistema(self):
        # La direccion la escribe el sistema, pero el administrador puede
        # editarla desde el panel: la campanita no debe servir de trampolin.
        aviso = self.crear_aviso(url='https://ejemplo.mx/')

        respuesta = self.abrir(aviso)

        self.assertRedirects(respuesta, reverse('usuarios:notificaciones'))

    def test_no_se_abre_la_notificacion_de_otra_persona(self):
        ajena = self.crear_aviso(persona=self.otra)

        respuesta = self.abrir(ajena)

        self.assertEqual(respuesta.status_code, 404)
        ajena.refresh_from_db()
        self.assertEqual(ajena.estado, Notificacion.Estado.ENVIADA)

    def test_marcar_todas_como_leidas(self):
        self.crear_aviso()
        self.crear_aviso()

        self.client.post(reverse('usuarios:marcar_notificaciones_leidas'))

        self.assertEqual(
            self.persona.notificaciones.filter(
                estado=Notificacion.Estado.ENVIADA
            ).count(),
            0,
        )

    def test_marcar_todas_no_toca_las_de_otra_persona(self):
        ajena = self.crear_aviso(persona=self.otra)

        self.client.post(reverse('usuarios:marcar_notificaciones_leidas'))

        ajena.refresh_from_db()
        self.assertEqual(ajena.estado, Notificacion.Estado.ENVIADA)

    def test_la_lista_solo_muestra_las_propias(self):
        self.crear_aviso(titulo='Aviso propio')
        self.crear_aviso(persona=self.otra, titulo='Aviso ajeno')

        respuesta = self.client.get(reverse('usuarios:notificaciones'))

        self.assertContains(respuesta, 'Aviso propio')
        self.assertNotContains(respuesta, 'Aviso ajeno')
