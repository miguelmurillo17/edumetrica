"""
Endpoints en formato JSON que consume la aplicacion de Vue del alumno.

Se autentican con la misma sesion del navegador. La retroalimentacion (saber
que opcion era la correcta, y el procedimiento que lleva a ella) se entrega
solo al finalizar la evaluacion, nunca mientras el alumno la esta presentando.

Por eso los diccionarios se arman a mano en lugar de serializar el modelo
completo: es lo que garantiza que ni es_correcta ni procedimiento se cuelen en
la respuesta que el alumno recibe al iniciar.
"""

from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.catalogo.models import Pregunta, OpcionRespuesta

from .models import Evaluacion, IntentoEvaluacion, RespuestaAlumno


def _url_imagen(campo):
    """Regresa la direccion de una imagen o None si no tiene."""
    return campo.url if campo else None


def _serializar_preguntas(evaluacion):
    """Arma las preguntas con sus opciones, sin revelar la respuesta correcta."""
    preguntas = []
    for pregunta in evaluacion.preguntas.all().prefetch_related('opciones'):
        preguntas.append({
            'id': pregunta.id,
            'enunciado': pregunta.enunciado,
            'imagen': _url_imagen(pregunta.imagen),
            'opciones': [
                {
                    'id': opcion.id,
                    'texto': opcion.texto,
                    'imagen': _url_imagen(opcion.imagen),
                }
                for opcion in pregunta.opciones.all()
            ],
        })
    return preguntas


def _construir_resultado(intento):
    """Arma el resultado final con el detalle de aciertos y errores."""
    evaluacion = intento.evaluacion
    respuestas = {
        respuesta.pregunta_id: respuesta
        for respuesta in intento.respuestas.select_related('opcion_seleccionada')
    }

    detalle = []
    for pregunta in evaluacion.preguntas.all().prefetch_related('opciones'):
        respuesta = respuestas.get(pregunta.id)
        correcta = pregunta.opciones.filter(es_correcta=True).first()
        acerto = respuesta.es_correcta if respuesta else False
        detalle.append({
            'enunciado': pregunta.enunciado,
            'tu_respuesta': respuesta.opcion_seleccionada.texto if respuesta and respuesta.opcion_seleccionada else None,
            'respuesta_correcta': correcta.texto if correcta else None,
            'acerto': acerto,
            # El procedimiento solo viaja en las preguntas que el alumno fallo,
            # que son en las que ensena algo. Una pregunta sin responder cuenta
            # como fallada, y ahi tambien sirve. Se manda cadena vacia y no la
            # llave ausente para que la plantilla no tenga que distinguir entre
            # "no aplica" y "esta pregunta no trae procedimiento".
            'procedimiento': '' if acerto else pregunta.procedimiento,
        })

    return {
        'calificacion': float(intento.calificacion or 0),
        'total': evaluacion.numero_preguntas,
        'aciertos': intento.respuestas.filter(es_correcta=True).count(),
        'detalle': detalle,
    }


@api_view(['POST'])
def iniciar_evaluacion(request, evaluacion_id):
    """Inicia o reanuda el intento del alumno y entrega las preguntas."""
    alumno = request.user
    evaluacion = get_object_or_404(Evaluacion, id=evaluacion_id)

    # El alumno solo puede presentar evaluaciones de sus grupos.
    if not evaluacion.grupo.alumnos.filter(id=alumno.id).exists():
        return Response({'detalle': 'No tienes acceso a esta evaluación.'}, status=403)

    if not evaluacion.esta_disponible():
        return Response({'detalle': 'La evaluación no está disponible en este momento.'}, status=400)

    intento, _ = IntentoEvaluacion.objects.get_or_create(
        evaluacion=evaluacion, alumno=alumno
    )

    if intento.estado == IntentoEvaluacion.Estado.FINALIZADO:
        return Response({'detalle': 'Ya presentaste esta evaluación.'}, status=400)

    # Las respuestas que el alumno ya haya guardado, para poder reanudar.
    previas = {
        respuesta.pregunta_id: respuesta.opcion_seleccionada_id
        for respuesta in intento.respuestas.all()
    }

    return Response({
        'intento_id': intento.id,
        'titulo': evaluacion.titulo,
        'preguntas': _serializar_preguntas(evaluacion),
        'respuestas_previas': previas,
    })


@api_view(['POST'])
def responder_pregunta(request, intento_id):
    """Guarda la respuesta del alumno a una pregunta del intento."""
    intento = get_object_or_404(IntentoEvaluacion, id=intento_id, alumno=request.user)

    if intento.estado == IntentoEvaluacion.Estado.FINALIZADO:
        # El profesor pudo haber finalizado la evaluacion mientras el alumno respondia.
        return Response({'finalizada': True})

    pregunta_id = request.data.get('pregunta')
    opcion_id = request.data.get('opcion')

    # La pregunta debe formar parte de esta evaluacion.
    if not intento.evaluacion.preguntas.filter(id=pregunta_id).exists():
        return Response({'detalle': 'La pregunta no pertenece a la evaluación.'}, status=400)

    pregunta = get_object_or_404(Pregunta, id=pregunta_id)
    opcion = get_object_or_404(OpcionRespuesta, id=opcion_id, pregunta=pregunta)

    # Se guarda la respuesta y de una vez si fue correcta, sin avisarle al alumno.
    RespuestaAlumno.objects.update_or_create(
        intento=intento,
        pregunta=pregunta,
        defaults={'opcion_seleccionada': opcion, 'es_correcta': opcion.es_correcta},
    )

    return Response({'ok': True})


@api_view(['POST'])
def finalizar_intento(request, intento_id):
    """Cierra el intento, calcula la calificacion y entrega el resultado."""
    intento = get_object_or_404(IntentoEvaluacion, id=intento_id, alumno=request.user)

    if intento.estado != IntentoEvaluacion.Estado.FINALIZADO:
        intento.estado = IntentoEvaluacion.Estado.FINALIZADO
        intento.fecha_fin = timezone.now()
        intento.calificacion = intento.calcular_calificacion()
        intento.save()

    return Response(_construir_resultado(intento))


@api_view(['GET'])
def resultado_intento(request, intento_id):
    """Devuelve el resultado de un intento que el alumno ya finalizo.

    Se comprueba que de verdad este finalizado, y no se da por hecho porque la
    aplicacion de Vue solo lo pida al terminar. El resultado lleva la respuesta
    correcta y el procedimiento de cada pregunta: entregarlo a media evaluacion
    seria entregar el examen resuelto, que es justo lo que cuida
    iniciar_evaluacion al armar sus diccionarios a mano.
    """
    intento = get_object_or_404(IntentoEvaluacion, id=intento_id, alumno=request.user)

    if intento.estado != IntentoEvaluacion.Estado.FINALIZADO:
        return Response(
            {'detalle': 'Todavía no has terminado esta evaluación.'}, status=400
        )

    return Response(_construir_resultado(intento))


@api_view(['GET'])
def estado_intento(request, intento_id):
    """Sondeo ligero para saber si la evaluacion ya fue finalizada.

    La aplicacion del alumno lo consulta cada cierto tiempo para enterarse
    cuando el profesor termina la evaluacion antes de tiempo.
    """
    intento = get_object_or_404(IntentoEvaluacion, id=intento_id, alumno=request.user)
    return Response({
        'finalizada': intento.estado == IntentoEvaluacion.Estado.FINALIZADO,
    })
