"""
Avisos del sistema: la campanita de la barra superior y el correo.

Vive en usuarios y no en evaluaciones porque una notificacion es de la persona
que la recibe, no de lo que la provoco. El modelo es generico, y quien avisa
-hoy solo evaluaciones- arma el texto y llama a estas funciones.

La campanita es lo que sostiene el flujo: el correo puede fallar, quedarse sin
configurar o tardar, y el aviso sigue estando cuando la persona entra.
"""

import logging
import threading

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.template.loader import render_to_string

from .models import Notificacion

registro = logging.getLogger(__name__)


def notificar(persona, titulo, descripcion='', url=''):
    """Deja un aviso en la campanita de una persona."""
    return Notificacion.objects.create(
        persona=persona,
        titulo=titulo,
        descripcion=descripcion,
        url=url,
    )


def notificar_a_varios(personas, titulo, descripcion='', url=''):
    """Deja el mismo aviso a varias personas de un solo golpe."""
    avisos = [
        Notificacion(
            persona=persona, titulo=titulo, descripcion=descripcion, url=url
        )
        for persona in personas
    ]
    return Notificacion.objects.bulk_create(avisos)


def direccion_absoluta(ruta):
    """Completa una ruta del sitio con el dominio configurado.

    Los enlaces de un correo se leen fuera del navegador, asi que una ruta
    relativa no lleva a ningun lado.
    """
    return f"{settings.SITIO_URL.rstrip('/')}/{ruta.lstrip('/')}"


def armar_correo(*, destinatario, plantilla_asunto, plantilla_cuerpo, contexto):
    """Arma el mensaje desde sus plantillas, sin mandarlo todavia."""
    # El asunto tiene que quedar en una sola linea: un salto colado en la
    # plantilla partiria la cabecera del mensaje.
    asunto = ' '.join(render_to_string(plantilla_asunto, contexto).split())
    cuerpo = render_to_string(plantilla_cuerpo, contexto)
    return EmailMessage(
        subject=asunto,
        body=cuerpo,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[destinatario],
    )


def enviar_correos(mensajes):
    """Entrega los mensajes, por omision en un hilo aparte.

    Se manda uno por destinatario y no uno solo con todos en copia: las
    direcciones de los alumnos no tienen por que verlas sus companeros.

    El hilo es por el profesor que programa la evaluacion: con un grupo de
    cuarenta alumnos son cuarenta entregas, y esperarlas dejaria la pantalla
    colgada. Es el mismo trato que le da catalogo a la generacion con IA, y
    por el mismo motivo: nadie esta esperando el resultado.
    """
    if not mensajes:
        return None

    if not settings.CORREO_EN_HILO:
        _entregar(mensajes)
        return None

    hilo = threading.Thread(target=_entregar, args=(mensajes,), daemon=True)
    hilo.start()
    return hilo


def _entregar(mensajes):
    """Manda los mensajes reusando una sola conexion de salida."""
    try:
        conexion = get_connection()
        conexion.send_messages(mensajes)
    except Exception:
        # Nadie espera este correo: si el servidor de salida falla, el aviso de
        # la campanita ya quedo guardado y la persona se entera al entrar. El
        # fallo solo deja rastro en la bitacora.
        registro.exception('No se pudieron enviar %s correos', len(mensajes))
