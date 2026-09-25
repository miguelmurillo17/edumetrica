"""
Lo que consume el resto del sistema.

Este modulo no conoce los modelos de Django: recibe la materia, la categoria y
el nivel como texto y numeros, y devuelve preguntas sueltas. Quien traduce
entre el catalogo del sistema y esto es la aplicacion catalogo.

El modo JSON del proveedor obliga a que la respuesta sea JSON valido, pero no a
que tenga la forma que esperamos. La validacion de aqui es la unica garantia
real de que lo recibido sirve.
"""

import logging

from .cliente import pedir_json
from .errores import ErrorRespuestaIA
from .esquemas import PreguntaGenerada, ResultadoGeneracion
from .prompts import PROMPT_SISTEMA, armar_prompt_usuario

registro = logging.getLogger(__name__)

# Se genera una pregunta a la vez, por decision del proyecto.
#
# Cuesta mas llamadas para armar el mismo banco, pero a cambio: una pregunta
# mala ya no tumba un lote entero, el profesor la revisa de inmediato en lugar
# de esperar veinte, y la espera por accion baja de minutos a segundos.
#
# Subir este numero es lo unico que hace falta para volver a los lotes; el
# resto del modulo ya lo soporta.
MAXIMO_PREGUNTAS = 1

NUMERO_OPCIONES = 4


def _texto(valor):
    return str(valor).strip() if valor is not None else ''


def _leer_pregunta(cruda, posicion, exige_expresion=False):
    """Revisa una pregunta del JSON y la convierte, o explica que le falto."""
    if not isinstance(cruda, dict):
        raise ErrorRespuestaIA(f'La pregunta {posicion} no es un objeto.')

    enunciado = _texto(cruda.get('enunciado'))
    if not enunciado:
        raise ErrorRespuestaIA(f'La pregunta {posicion} no trae enunciado.')

    opciones = cruda.get('opciones')
    if not isinstance(opciones, list) or len(opciones) != NUMERO_OPCIONES:
        raise ErrorRespuestaIA(
            f'La pregunta {posicion} debe traer {NUMERO_OPCIONES} opciones.'
        )

    opciones = [_texto(opcion) for opcion in opciones]
    if any(not opcion for opcion in opciones):
        raise ErrorRespuestaIA(f'La pregunta {posicion} trae opciones vacías.')
    if len(set(opciones)) != len(opciones):
        raise ErrorRespuestaIA(f'La pregunta {posicion} repite opciones.')

    indice = cruda.get('indice_correcto')
    if not isinstance(indice, int) or not 0 <= indice < NUMERO_OPCIONES:
        raise ErrorRespuestaIA(
            f'La pregunta {posicion} no señala bien cuál opción es la correcta.'
        )

    # Los valores simbolicos son opcionales: en las materias que no son de
    # matematicas el modelo los deja vacios a proposito.
    valores = cruda.get('valores') or []
    if isinstance(valores, list):
        valores = [_texto(valor) for valor in valores]
        if len(valores) != NUMERO_OPCIONES or any(not v for v in valores):
            valores = []
    else:
        valores = []

    procedimiento = cruda.get('procedimiento')
    if isinstance(procedimiento, list):
        # Un paso por elemento; se unen en un renglon cada uno.
        procedimiento = '\n'.join(_texto(paso) for paso in procedimiento if _texto(paso))
    procedimiento = _texto(procedimiento)
    if not procedimiento:
        # Sin procedimiento la pregunta no sirve para retroalimentar al alumno,
        # que es la mitad del proposito de generarla.
        raise ErrorRespuestaIA(f'La pregunta {posicion} no trae procedimiento.')

    expresion = _texto(cruda.get('expresion'))
    if exige_expresion and not expresion:
        # Sin expresion el verificador simbolico contesta "no aplica" y la
        # pregunta pasa sin revisarse. En una categoria de matematicas eso
        # seria esquivar la comprobacion, no una excepcion legitima.
        raise ErrorRespuestaIA(
            f'La pregunta {posicion} es de una categoría de matemáticas pero '
            f'no trae la expresión que permite verificarla.'
        )
    if exige_expresion and not valores:
        raise ErrorRespuestaIA(
            f'La pregunta {posicion} no trae los valores simbólicos de sus '
            f'opciones, que el verificador necesita.'
        )

    return PreguntaGenerada(
        enunciado=enunciado,
        opciones=opciones,
        indice_correcto=indice,
        procedimiento=procedimiento,
        expresion=expresion,
        valores=valores,
    )


def generar_preguntas(*, materia, categoria, nivel, cantidad=1,
                      descripcion_nivel='', exige_expresion=False):
    """Pide un lote de preguntas al proveedor activo.

    exige_expresion debe ir en verdadero cuando la categoria es de matematicas.
    Sin eso, una pregunta que llegue sin expresion pasaria como "no aplica" y
    se saltaria el verificador simbolico, que es justo lo que no debe ocurrir.
    Quien conoce la materia es el catalogo, por eso la decision se recibe de
    afuera y no se adivina aqui.

    Devuelve un ResultadoGeneracion. Puede levantar ErrorConfiguracionIA,
    ErrorProveedorIA o ErrorRespuestaIA.
    """
    materia = _texto(materia)
    categoria = _texto(categoria)
    if not materia or not categoria:
        raise ValueError('Hacen falta la materia y la categoría.')

    cantidad = int(cantidad)
    if not 1 <= cantidad <= MAXIMO_PREGUNTAS:
        raise ValueError(
            f'Solo se puede pedir {MAXIMO_PREGUNTAS} pregunta a la vez.'
            if MAXIMO_PREGUNTAS == 1
            else f'La cantidad debe estar entre 1 y {MAXIMO_PREGUNTAS}.'
        )

    datos, metadatos = pedir_json(
        prompt_sistema=PROMPT_SISTEMA,
        prompt_usuario=armar_prompt_usuario(
            materia=materia,
            categoria=categoria,
            nivel=nivel,
            cantidad=cantidad,
            descripcion_nivel=descripcion_nivel,
        ),
    )

    crudas = datos.get('preguntas')
    if not isinstance(crudas, list) or not crudas:
        raise ErrorRespuestaIA(
            'La respuesta no trae una lista de preguntas con contenido.'
        )

    preguntas = [
        _leer_pregunta(cruda, posicion, exige_expresion)
        for posicion, cruda in enumerate(crudas, start=1)
    ]

    # Los modelos a veces entregan de mas o de menos. No es un error, pero
    # conviene que quede en la bitacora.
    if len(preguntas) != cantidad:
        registro.warning(
            'Se pidieron %s preguntas y llegaron %s.', cantidad, len(preguntas)
        )
        preguntas = preguntas[:cantidad]

    return ResultadoGeneracion(preguntas=preguntas, **metadatos)
