"""
Puente entre el catalogo del sistema y el modulo de inteligencia artificial.

El modulo apps.ia no conoce los modelos de Django: recibe texto y devuelve
preguntas sueltas. Aqui se traduce en las dos direcciones: se arma la peticion
a partir de la materia, la categoria y el nivel del catalogo, y lo que regresa
se somete al verificador simbolico y se guarda como borrador.

Una pregunta generada NUNCA se guarda como validada. Nace en borrador y espera
a que el profesor la revise, aunque el verificador la haya aprobado.
"""

import logging

from django.db import transaction

from apps.ia.servicios import generar_preguntas

from .models import OpcionRespuesta, Pregunta, SolicitudGeneracion
from .verificador import verificar

registro = logging.getLogger(__name__)


def _guardar_pregunta(generada, dictamen, solicitud, profesor):
    """Guarda la pregunta con sus cuatro opciones y el fallo del verificador."""
    pregunta = Pregunta.objects.create(
        materia=solicitud.categoria.materia,
        categoria=solicitud.categoria,
        nivel=solicitud.nivel,
        enunciado=generada.enunciado,
        procedimiento=generada.procedimiento,
        creada_por=profesor,
        origen=Pregunta.Origen.IA,
        # Aunque el verificador la apruebe, la revisa una persona antes de que
        # pueda entrar a una evaluacion.
        estado=(
            Pregunta.Estado.BORRADOR if dictamen.aprobada
            else Pregunta.Estado.DESCARTADA
        ),
        # Queda en nulo cuando no habia expresion que comprobar.
        verificada_simbolicamente=dictamen.aprobada if dictamen.aplica else None,
        motivo_rechazo=dictamen.motivo,
        solicitud=solicitud,
    )

    for posicion, texto in enumerate(generada.opciones):
        OpcionRespuesta.objects.create(
            pregunta=pregunta,
            texto=texto,
            es_correcta=(posicion == generada.indice_correcto),
        )

    return pregunta


def generar_pregunta(*, profesor, categoria, nivel):
    """Genera una pregunta, la verifica y la guarda como borrador.

    Devuelve (pregunta, dictamen). La pregunta queda en borrador si paso el
    verificador y descartada si no, pero en los dos casos se guarda: las
    descartadas son el dato de cuantas rechazo la comprobacion, que es parte
    de lo que se quiere medir.

    Puede levantar ErrorConfiguracionIA, ErrorProveedorIA o ErrorRespuestaIA.
    La solicitud queda registrada tambien cuando falla, con el motivo.

    Ojo con las transacciones: el registro del fallo NO puede ir dentro de una
    transaccion que se revierta al relanzar la excepcion, o se perderia justo
    el dato de cuantos intentos hicieron falta. Por eso solo el guardado de la
    pregunta va en un bloque atomico, no la funcion completa.
    """
    materia = categoria.materia

    solicitud = SolicitudGeneracion.objects.create(
        profesor=profesor,
        materia=materia,
        categoria=categoria,
        nivel=nivel,
        cantidad_pedida=1,
    )

    try:
        resultado = generar_preguntas(
            materia=materia.nombre,
            categoria=categoria.nombre,
            nivel=nivel.numero,
            cantidad=1,
            descripcion_nivel=nivel.nombre,
            # Si la materia es cuantitativa, la pregunta tiene que traer la
            # expresion o se estaria saltando el verificador.
            exige_expresion=materia.es_cuantitativa,
        )
    except Exception as error:
        # La solicitud fallida tambien se guarda: sin ella no se sabria cuantos
        # intentos hicieron falta para armar el banco.
        solicitud.exitosa = False
        solicitud.detalle_error = str(error)[:2000]
        solicitud.save(update_fields=['exitosa', 'detalle_error'])
        raise

    solicitud.modelo = resultado.modelo
    solicitud.tokens_entrada = resultado.tokens_entrada
    solicitud.tokens_salida = resultado.tokens_salida
    solicitud.cantidad_recibida = len(resultado.preguntas)
    solicitud.exitosa = True

    generada = resultado.preguntas[0]
    dictamen = verificar(
        generada.expresion,
        generada.valores_para_verificar,
        generada.indice_correcto,
    )

    solicitud.cantidad_aprobada = 1 if dictamen.aprobada else 0
    solicitud.save()

    # La pregunta y sus opciones si van juntas: una pregunta a medio guardar,
    # sin sus cuatro opciones, seria peor que ninguna.
    with transaction.atomic():
        pregunta = _guardar_pregunta(generada, dictamen, solicitud, profesor)

    registro.info(
        'Pregunta %s generada para %s / %s: %s',
        pregunta.id, materia.nombre, categoria.nombre,
        'aprobada por el verificador' if dictamen.aprobada
        else f'rechazada ({dictamen.motivo})',
    )
    return pregunta, dictamen
