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

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Persona


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
        self.assertEqual(self.crear().nombre_completo, 'Beto Lara')

    def test_se_entra_con_el_correo_y_no_con_un_usuario(self):
        # Las dos constantes tienen que apuntar al correo. La segunda es la
        # que usa el restablecimiento para encontrar a la persona.
        self.assertEqual(get_user_model().USERNAME_FIELD, 'correo')
        self.assertEqual(get_user_model().EMAIL_FIELD, 'correo')


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

    def test_el_administrador_va_al_panel_de_django(self):
        self.crear_y_entrar(Persona.Rol.ADMINISTRADOR)

        respuesta = self.client.get(reverse('usuarios:inicio'))

        self.assertRedirects(respuesta, '/admin/', target_status_code=302)

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
