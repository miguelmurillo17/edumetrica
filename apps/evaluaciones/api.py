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

from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.catalogo.models import Pregunta, OpcionRespuesta

from .models import Evaluacion, IntentoEvaluacion, RespuestaAlumno
from .servicios import (
    construir_resultado, entregar_intento, motivo_cierre, poner_al_dia,
)


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


@api_view(['POST'])
def iniciar_evaluacion(request, evaluacion_id):
    """Inicia o reanuda el intento del alumno y entrega las preguntas."""
    alumno = request.user
    evaluacion = get_object_or_404(Evaluacion, id=evaluacion_id)
    poner_al_dia(evaluacion)

    # El alumno solo puede presentar evaluaciones de sus grupos.
    if not evaluacion.grupo.alumnos.filter(id=alumno.id).exists():
        return Response({'detalle': 'No tienes acceso a esta evaluación.'}, status=403)

    intento = IntentoEvaluacion.objects.filter(
        evaluacion=evaluacion, alumno=alumno
    ).first()

    # Lo primero que se mira es si ya presento, antes que la disponibilidad:
    # quien vuelve por su retroalimentacion casi siempre lo hace con la
    # evaluacion ya cerrada, que es justo cuando el plazo dice que no.
    #
    # El resultado no lleva motivo, porque el aviso de "se acabo el tiempo"
    # explica una interrupcion y aqui no se interrumpio nada: el alumno entro
    # por su cuenta a leer lo que ya termino.
    if intento and intento.estado == IntentoEvaluacion.Estado.FINALIZADO:
        return Response({
            'intento_id': intento.id,
            'titulo': evaluacion.titulo,
            'finalizado': True,
            'resultado': construir_resultado(intento),
        })

    if not evaluacion.esta_disponible():
        return Response({'detalle': 'La evaluación no está disponible en este momento.'}, status=400)

    if intento is None:
        intento = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=alumno
        )

    # Las respuestas que el alumno ya haya guardado, para poder reanudar.
    previas = {
        respuesta.pregunta_id: respuesta.opcion_seleccionada_id
        for respuesta in intento.respuestas.all()
    }

    preguntas = _serializar_preguntas(evaluacion)

    # Se reanuda en la primera sin responder y no en la primera de todas: el
    # alumno que vuelve tras un corte no tiene que pasar otra vez por las que
    # ya contesto. Si no queda ninguna, se abre en la primera.
    indice_inicial = next(
        (
            posicion
            for posicion, pregunta in enumerate(preguntas)
            if pregunta['id'] not in previas
        ),
        0,
    )

    return Response({
        'intento_id': intento.id,
        'titulo': evaluacion.titulo,
        'preguntas': preguntas,
        'respuestas_previas': previas,
        'indice_inicial': indice_inicial,
        # El tiempo lo dice el servidor; el reloj del navegador no manda.
        'segundos_restantes': evaluacion.segundos_restantes(),
    })


@api_view(['POST'])
def responder_pregunta(request, intento_id):
    """Guarda la respuesta del alumno a una pregunta del intento.

    Aqui se vigila el plazo, y no solo al iniciar: con la pestana abierta, un
    alumno podria seguir respondiendo horas despues de que la evaluacion cerro y
    recalcular su calificacion. El reloj del servidor es el que manda.
    """
    intento = get_object_or_404(
        IntentoEvaluacion.objects.select_related('evaluacion'),
        id=intento_id, alumno=request.user,
    )
    evaluacion = poner_al_dia(intento.evaluacion)
    # Si el plazo acababa de vencer, poner_al_dia ya cerro este intento.
    intento.refresh_from_db()

    if intento.estado == IntentoEvaluacion.Estado.FINALIZADO:
        # Se le acabo el tiempo, o el profesor finalizo la evaluacion mientras
        # el alumno respondia.
        return Response({'finalizada': True, 'motivo': motivo_cierre(evaluacion)})

    if not evaluacion.esta_disponible():
        # Solo se llega aqui si el profesor movio las fechas a media
        # presentacion: la respuesta no se guarda, pero el intento sigue abierto.
        return Response(
            {'detalle': 'La evaluación no está disponible en este momento.'}, status=400
        )

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
    intento = get_object_or_404(
        IntentoEvaluacion.objects.select_related('evaluacion'),
        id=intento_id, alumno=request.user,
    )
    # Si entrega justo cuando el plazo vencia, el cierre ya lo hizo el servicio.
    poner_al_dia(intento.evaluacion)
    intento.refresh_from_db()

    entregar_intento(intento)

    return Response(construir_resultado(intento))


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

    return Response(construir_resultado(intento))


@api_view(['GET'])
def estado_intento(request, intento_id):
    """Sondeo ligero para saber si la evaluacion ya fue finalizada.

    La aplicacion del alumno lo consulta cada cierto tiempo para enterarse
    cuando el profesor termina la evaluacion antes de tiempo. Es tambien el
    sondeo el que cierra el intento cuando se acaba el plazo mientras el alumno
    tiene la pantalla abierta, porque nadie mas vigila el reloj.
    """
    intento = get_object_or_404(
        IntentoEvaluacion.objects.select_related('evaluacion'),
        id=intento_id, alumno=request.user,
    )
    evaluacion = poner_al_dia(intento.evaluacion)
    intento.refresh_from_db()

    finalizada = intento.estado == IntentoEvaluacion.Estado.FINALIZADO
    return Response({
        'finalizada': finalizada,
        'motivo': motivo_cierre(evaluacion) if finalizada else '',
    })
