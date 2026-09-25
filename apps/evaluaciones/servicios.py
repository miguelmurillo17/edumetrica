"""Reglas del ciclo de vida de una evaluacion y de sus intentos.

Aqui vive lo que comparten la API del alumno (apps.evaluaciones.api), las
vistas del profesor y la exploracion de resultados (apps.reportes): el detalle
de un intento ya finalizado, y el cierre de las evaluaciones cuando se les
acaba el plazo. Vive aparte de las tres para no duplicar la logica ni
arriesgar que se desincronicen.

Nada corre en segundo plano para vigilar el reloj -no hay Celery ni tareas
programadas, igual que no hay WebSockets en el sondeo del alumno-, asi que el
cierre es perezoso: se pone al dia cada vez que alguien mira una evaluacion,
sea su panel, su listado, su detalle o cualquier peticion del alumno. El
comando cerrar_evaluaciones hace lo mismo desde cron, para que el cierre
tambien ocurra cuando nadie tiene el navegador abierto.
"""

from django.utils import timezone

from .avisos import (
    avisar_evaluacion_cerrada, avisar_grupo_termino, avisar_resultado_disponible,
)
from .models import Evaluacion, IntentoEvaluacion


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


def cerrar_intento(intento, ahora=None):
    """Finaliza un intento con la calificacion de lo que llevaba respondido."""
    if intento.estado == IntentoEvaluacion.Estado.FINALIZADO:
        return intento

    intento.estado = IntentoEvaluacion.Estado.FINALIZADO
    intento.fecha_fin = ahora or timezone.now()
    intento.calificacion = intento.calcular_calificacion()
    intento.save(update_fields=['estado', 'fecha_fin', 'calificacion'])
    return intento


def cerrar_intentos_en_curso(evaluacion, ahora=None):
    """Cierra los intentos que siguen abiertos y devuelve los que cerro."""
    ahora = ahora or timezone.now()
    return [
        cerrar_intento(intento, ahora)
        for intento in evaluacion.intentos.filter(
            estado=IntentoEvaluacion.Estado.EN_CURSO
        ).select_related('alumno')
    ]


def entregar_intento(intento):
    """Cierra el intento que el alumno entrega por su cuenta.

    Se distingue de cerrar_intento porque aqui hay alguien decidiendo terminar:
    si con esta entrega ya no queda nadie presentando y la evaluacion sigue
    abierta, al profesor le sirve enterarse para poder cerrarla con tranquilidad.
    """
    if intento.estado == IntentoEvaluacion.Estado.FINALIZADO:
        return intento

    cerrar_intento(intento)

    evaluacion = intento.evaluacion
    if evaluacion.estado != Evaluacion.Estado.FINALIZADA:
        total = evaluacion.grupo.alumnos.count()
        entregados = evaluacion.intentos.filter(
            estado=IntentoEvaluacion.Estado.FINALIZADO
        ).count()
        if total and entregados >= total:
            avisar_grupo_termino(evaluacion, total)

    return intento


def cerrar_evaluacion(evaluacion, ahora=None, anticipada=False):
    """Finaliza la evaluacion y cierra los intentos que quedaron abiertos.

    Quien llama decide si fue anticipada, porque esa bandera es del profesor
    que cerro antes de tiempo: en el capitulo de resultados sirve justo para
    distinguir su decision de que se acabara el plazo.
    """
    if evaluacion.estado == Evaluacion.Estado.FINALIZADA:
        return []

    ahora = ahora or timezone.now()
    evaluacion.estado = Evaluacion.Estado.FINALIZADA
    evaluacion.finalizada_anticipadamente = anticipada
    evaluacion.save(update_fields=['estado', 'finalizada_anticipadamente'])

    cerrados = cerrar_intentos_en_curso(evaluacion, ahora)

    # A quien se le cerro el intento sin haber entregado se le avisa que su
    # resultado ya esta listo, porque no estaba mirando la pantalla.
    avisar_resultado_disponible(
        evaluacion, [intento.alumno for intento in cerrados]
    )

    # Al profesor se le avisa solo cuando fue el plazo el que cerro la
    # evaluacion: si la cerro el, ya lo sabe.
    if not anticipada:
        avisar_evaluacion_cerrada(
            evaluacion,
            evaluacion.intentos.count(),
            evaluacion.grupo.alumnos.count(),
        )

    return cerrados


def actualizar_estados(consulta=None):
    """Pone al dia el estado de las evaluaciones segun el reloj.

    Una evaluacion programada pasa a en curso cuando entra su ventana, y a
    finalizada cuando la ventana se cierra; al cerrarla se cierran tambien los
    intentos de quienes no alcanzaron a entregar, con la calificacion de lo que
    llevaban.

    Sin esto una evaluacion vencida seguiria diciendo "Programada", y el
    intento de quien cerro el navegador se quedaria en curso para siempre: como
    el tablero solo cuenta los intentos finalizados, ese alumno desapareceria
    de los promedios del grupo.

    Se trabaja sobre identificadores y no sobre la consulta que llega porque
    las vistas la traen filtrada por otras tablas -los alumnos del grupo, por
    ejemplo-, y un update() sobre esos cruces no es de fiar.
    """
    ahora = timezone.now()
    if consulta is None:
        consulta = Evaluacion.objects.all()

    pendientes = list(
        consulta
        .exclude(estado=Evaluacion.Estado.FINALIZADA)
        .values_list('id', flat=True)
    )
    if not pendientes:
        return

    por_revisar = Evaluacion.objects.filter(id__in=pendientes)

    # Las vencidas se cierran una por una porque cada una tiene que arrastrar
    # sus intentos; las que apenas entraron a su ventana se marcan de golpe.
    for evaluacion in por_revisar.filter(fecha_fin__lte=ahora):
        cerrar_evaluacion(evaluacion, ahora)

    por_revisar.filter(
        estado=Evaluacion.Estado.PROGRAMADA,
        fecha_inicio__lte=ahora,
        fecha_fin__gt=ahora,
    ).update(estado=Evaluacion.Estado.EN_CURSO)


def poner_al_dia(evaluacion):
    """Actualiza el estado de una sola evaluacion y la refresca en memoria."""
    actualizar_estados(Evaluacion.objects.filter(id=evaluacion.id))
    evaluacion.refresh_from_db()
    return evaluacion


def motivo_cierre(evaluacion):
    """Por que se cerro la evaluacion, en los terminos que lee el alumno."""
    return 'profesor' if evaluacion.finalizada_anticipadamente else 'tiempo'
