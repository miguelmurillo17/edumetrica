"""
Unica frontera con LiteLLM.

Ningun otro archivo del proyecto importa litellm. Si algun dia se cambia de
biblioteca, o se pasa al servicio intermediario de LiteLLM en lugar del paquete
de Python, solo se reescribe este archivo.
"""

import json
import logging
import re

import litellm
from django.conf import settings
from litellm import completion
from litellm.exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)

from .errores import ErrorConfiguracionIA, ErrorProveedorIA, ErrorRespuestaIA
from .proveedores import obtener_proveedor

registro = logging.getLogger(__name__)

# LiteLLM descarta en silencio los parametros que el proveedor activo no
# soporta, en lugar de fallar. Hace falta porque no todos aceptan lo mismo.
litellm.drop_params = True

# Aunque se pida modo JSON, un modelo puede envolver la respuesta en un bloque
# de codigo o anteponer una frase de cortesia. Estas expresiones aislan el
# objeto que interesa.
BLOQUE_CODIGO = re.compile(r'```(?:json)?\s*(.*?)\s*```', re.DOTALL)
OBJETO_JSON = re.compile(r'\{.*\}', re.DOTALL)


def proveedor_activo():
    return obtener_proveedor(settings.AI_PROVIDER)


def _llave_de(proveedor):
    llave = (settings.AI_LLAVES.get(proveedor.clave) or '').strip()
    if not llave:
        raise ErrorConfiguracionIA(
            f'Falta la variable {proveedor.variable_llave} para el proveedor '
            f'{proveedor.etiqueta}. Consigue una llave en {proveedor.consola} '
            f'y agrégala a tu archivo .env.'
        )
    return llave


def _aislar_json(texto):
    """Se queda con el objeto JSON que venga dentro de la respuesta."""
    encontrado = BLOQUE_CODIGO.search(texto)
    if encontrado:
        return encontrado.group(1)
    encontrado = OBJETO_JSON.search(texto)
    return encontrado.group(0) if encontrado else texto


def pedir_json(*, prompt_sistema, prompt_usuario, temperatura=None,
               maximo_tokens=None):
    """Hace la llamada y devuelve (datos, metadatos).

    Cualquier fallo de LiteLLM sale de aqui convertido en un error propio.
    """
    proveedor = proveedor_activo()
    llave = _llave_de(proveedor)
    modelo = settings.AI_MODEL or proveedor.modelo_por_omision

    argumentos = {
        'model': modelo,
        'api_key': llave,
        'messages': [
            {'role': 'system', 'content': prompt_sistema},
            {'role': 'user', 'content': prompt_usuario},
        ],
        'temperature': (
            settings.AI_TEMPERATURE if temperatura is None else temperatura
        ),
        'max_tokens': (
            settings.AI_MAX_TOKENS if maximo_tokens is None else maximo_tokens
        ),
        'timeout': settings.AI_TIMEOUT,
        'num_retries': settings.AI_MAX_RETRIES,
    }
    if proveedor.acepta_modo_json:
        # Obliga a que la respuesta sea JSON valido. Ojo: no obliga a que tenga
        # la forma que esperamos, por eso la validacion propia no sobra.
        argumentos['response_format'] = {'type': 'json_object'}

    registro.info('Pidiendo preguntas a %s (modelo %s)', proveedor.clave, modelo)

    # Regla de todas las ramas de abajo: el texto crudo del proveedor va
    # siempre en detalle y jamas dentro del mensaje. El mensaje lo lee el
    # profesor en la pantalla de espera, y un volcado de JSON ahi hace pensar
    # que el sistema se rompio cuando el problema es de quien atiende.
    try:
        respuesta = completion(**argumentos)
    except AuthenticationError as error:
        raise ErrorConfiguracionIA(
            f'{proveedor.etiqueta} rechazó la llave. '
            f'Revisa {proveedor.variable_llave} en tu archivo .env.'
        ) from error
    except RateLimitError as error:
        registro.warning('Cuota agotada en %s: %s', proveedor.clave, error)
        raise ErrorProveedorIA(
            f'Se alcanzó el límite de solicitudes de {proveedor.etiqueta}. '
            f'No es una falla de Edumétrica: el proveedor limita cuántas '
            f'peticiones se le pueden hacer por minuto y por día, y en los '
            f'planes gratuitos ese límite es más bajo. Espera unos minutos y '
            f'vuelve a intentarlo.',
            reintentable=True,
            proveedor=proveedor.clave,
            tipo=ErrorProveedorIA.CUOTA,
            detalle=str(error),
        ) from error
    except ServiceUnavailableError as error:
        # El proveedor esta saturado. Es frecuente y pasa solo; lo importante
        # es que el profesor entienda que el problema no es del sistema.
        registro.warning('Proveedor saturado (%s): %s', proveedor.clave, error)
        raise ErrorProveedorIA(
            f'{proveedor.etiqueta} está saturado en este momento y no pudo '
            f'atender la solicitud. No es una falla de Edumétrica: le están '
            f'llegando más peticiones de las que alcanza a responder. Suele '
            f'durar poco; vuelve a intentarlo en un momento.',
            reintentable=True,
            proveedor=proveedor.clave,
            tipo=ErrorProveedorIA.SATURACION,
            detalle=str(error),
        ) from error
    except (Timeout, APIConnectionError) as error:
        registro.warning('Sin conexion con %s: %s', proveedor.clave, error)
        raise ErrorProveedorIA(
            f'No se pudo contactar a {proveedor.etiqueta}. Revisa tu conexión '
            f'a internet y vuelve a intentarlo.',
            reintentable=True,
            proveedor=proveedor.clave,
            tipo=ErrorProveedorIA.CONEXION,
            detalle=str(error),
        ) from error
    except NotFoundError as error:
        # El identificador del modelo ya no existe. Los proveedores los retiran
        # cada tanto, asi que conviene decir exactamente que hay que cambiar.
        registro.error('Modelo inexistente en %s: %s', proveedor.clave, error)
        raise ErrorProveedorIA(
            f'El modelo {modelo} ya no está disponible en '
            f'{proveedor.etiqueta}. Revisa el identificador vigente en '
            f'{proveedor.consola} y ajústalo con AI_MODEL en el archivo .env.',
            reintentable=False,
            proveedor=proveedor.clave,
            tipo=ErrorProveedorIA.MODELO,
            detalle=str(error),
        ) from error
    except BadRequestError as error:
        # Casi siempre: el modelo no existe, o el prompt es demasiado largo.
        # Las dos son configuracion del servidor, asi que se marca del mismo
        # tipo que el modelo caducado: reintentar repetiria el mismo error.
        registro.error('Peticion rechazada por %s: %s', proveedor.clave, error)
        raise ErrorProveedorIA(
            f'{proveedor.etiqueta} rechazó la solicitud enviada al modelo '
            f'{modelo}. Es un problema de configuración del servidor, no algo '
            f'que se arregle reintentando. Avisa al administrador.',
            reintentable=False,
            proveedor=proveedor.clave,
            tipo=ErrorProveedorIA.MODELO,
            detalle=str(error),
        ) from error
    except APIError as error:
        registro.warning('Error de %s: %s', proveedor.clave, error)
        raise ErrorProveedorIA(
            f'{proveedor.etiqueta} respondió con un error al atender la '
            f'solicitud. No es una falla de Edumétrica; vuelve a intentarlo en '
            f'un momento.',
            reintentable=True,
            proveedor=proveedor.clave,
            detalle=str(error),
        ) from error
    except Exception as error:
        # Red de seguridad. LiteLLM no siempre levanta sus propias excepciones:
        # por ejemplo, si falta una dependencia opcional suya lanza un Exception
        # pelon. Sin esto, el resto del sistema veria un error crudo de la
        # biblioteca, que es justo lo que este modulo promete evitar.
        registro.exception('Fallo no previsto al llamar a %s', proveedor.clave)
        raise ErrorProveedorIA(
            f'No se pudo completar la solicitud a {proveedor.etiqueta} por un '
            f'fallo inesperado. Vuelve a intentarlo; si sigue ocurriendo, '
            f'avisa al administrador.',
            reintentable=True,
            proveedor=proveedor.clave,
            detalle=str(error),
        ) from error

    try:
        contenido = respuesta.choices[0].message.content or ''
    except (AttributeError, IndexError) as error:
        raise ErrorRespuestaIA(
            'La respuesta del proveedor no tiene la forma esperada.'
        ) from error

    contenido = _aislar_json(contenido.strip())
    if not contenido:
        raise ErrorRespuestaIA('El proveedor devolvió una respuesta vacía.')

    try:
        datos = json.loads(contenido)
    except json.JSONDecodeError as error:
        registro.warning(
            'JSON invalido de %s. Primeros 500 caracteres: %s',
            proveedor.clave, contenido[:500],
        )
        raise ErrorRespuestaIA(
            'El modelo no devolvió un JSON válido. Puedes reintentar el lote.'
        ) from error

    consumo = getattr(respuesta, 'usage', None)
    metadatos = {
        'modelo': modelo,
        'proveedor': proveedor.clave,
        'tokens_entrada': getattr(consumo, 'prompt_tokens', 0) or 0,
        'tokens_salida': getattr(consumo, 'completion_tokens', 0) or 0,
    }
    registro.info(
        'Respuesta de %s: %s tokens de entrada, %s de salida',
        proveedor.clave, metadatos['tokens_entrada'], metadatos['tokens_salida'],
    )
    return datos, metadatos
