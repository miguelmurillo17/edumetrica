"""Construccion del detalle de un intento ya finalizado.

Lo usan tanto la API del alumno (apps.evaluaciones.api) como la pantalla de
exploracion de resultados del profesor (apps.reportes), asi que vive aparte
de las dos para no duplicar la logica ni arriesgar que se desincronicen.
"""


def construir_resultado(intento):
    """Arma el resultado final con el detalle de aciertos y errores."""
    evaluacion = intento.evaluacion
    respuestas = {
        respuesta.pregunta_id: respuesta
        for respuesta in intento.respuestas.select_related('opcion_seleccionada')
    }

    detalle = []
    preguntas = (
        evaluacion.preguntas.all()
        .select_related('categoria', 'nivel')
        .prefetch_related('opciones')
    )
    for pregunta in preguntas:
        respuesta = respuestas.get(pregunta.id)
        correcta = pregunta.opciones.filter(es_correcta=True).first()
        acerto = respuesta.es_correcta if respuesta else False
        detalle.append({
            'enunciado': pregunta.enunciado,
            'categoria': pregunta.categoria.nombre,
            'nivel_numero': pregunta.nivel.numero,
            'nivel_nombre': pregunta.nivel.nombre,
            'tu_respuesta': respuesta.opcion_seleccionada.texto if respuesta and respuesta.opcion_seleccionada else None,
            'respuesta_correcta': correcta.texto if correcta else None,
            'acerto': acerto,
            # El procedimiento solo viaja en las preguntas que el alumno fallo,
            # que son en las que ensena algo. Una pregunta sin responder cuenta
            # como fallada, y ahi tambien sirve. Se manda cadena vacia y no la
            # llave ausente para que la plantilla no tenga que distinguir entre
            # "no aplica" y "esta pregunta no trae procedimiento". Vale igual
            # para el profesor: el procedimiento es material de refuerzo, solo
            # hace falta donde el alumno no acerto.
            'procedimiento': '' if acerto else pregunta.procedimiento,
        })

    return {
        'calificacion': float(intento.calificacion or 0),
        'total': evaluacion.numero_preguntas,
        'aciertos': intento.respuestas.filter(es_correcta=True).count(),
        'detalle': detalle,
    }
