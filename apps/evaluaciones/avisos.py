"""
Los avisos que manda el modulo de evaluaciones, con su redaccion.

Estan juntos y aparte de la logica para que se vean de un vistazo los cuatro
momentos en que el sistema interrumpe a alguien, y para poder corregir un texto
sin entrar a tocar el cierre de las evaluaciones.

Solo el primero sale ademas por correo. Los otros tres ocurren mientras la
persona usa la plataforma, o le esperan en la campanita hasta que entre; el
correo se reserva para lo que pasa cuando no esta.
"""

from django.urls import reverse
from django.utils import timezone

from apps.usuarios.servicios import (
    armar_correo, direccion_absoluta, enviar_correos, notificar,
    notificar_a_varios,
)


def _cuando(momento):
    """Fecha y hora como se leen en las pantallas del sistema."""
    return timezone.localtime(momento).strftime('%d/%m/%Y %H:%M')


def avisar_evaluacion_programada(evaluacion):
    """Avisa a los alumnos del grupo que tienen una evaluacion nueva."""
    alumnos = list(evaluacion.grupo.alumnos.all())
    if not alumnos:
        return

    url = reverse('evaluaciones:panel_alumno')
    notificar_a_varios(
        alumnos,
        'Nueva evaluación programada',
        f'{evaluacion.titulo} ({evaluacion.materia.nombre}). Podrás '
        f'presentarla del {_cuando(evaluacion.fecha_inicio)} '
        f'al {_cuando(evaluacion.fecha_fin)}.',
        url,
    )

    # Este es el unico aviso que tambien sale por correo: es el que tiene que
    # alcanzar al alumno cuando no esta en la plataforma.
    enviar_correos([
        armar_correo(
            destinatario=alumno.correo,
            plantilla_asunto='evaluaciones/correo_evaluacion_asunto.txt',
            plantilla_cuerpo='evaluaciones/correo_evaluacion.txt',
            contexto={
                'alumno': alumno,
                'evaluacion': evaluacion,
                'inicio': _cuando(evaluacion.fecha_inicio),
                'fin': _cuando(evaluacion.fecha_fin),
                'url': direccion_absoluta(url),
            },
        )
        for alumno in alumnos
    ])


def avisar_resultado_disponible(evaluacion, alumnos):
    """Avisa a quien se quedo a medias que su resultado ya esta listo.

    Solo a esos: quien entrego por su cuenta vio el resultado en pantalla en
    ese momento y no necesita que se lo anuncien.
    """
    if not alumnos:
        return

    notificar_a_varios(
        alumnos,
        'Ya puedes ver tu resultado',
        f'La evaluación {evaluacion.titulo} terminó. Revisa tu calificación y '
        f'el procedimiento de las preguntas que fallaste.',
        # Lleva directo al resultado, que es lo que el alumno viene a leer.
        reverse('evaluaciones:presentar_evaluacion', args=[evaluacion.id]),
    )


def avisar_evaluacion_cerrada(evaluacion, presentaron, total):
    """Avisa al profesor que a su evaluacion se le acabo el plazo."""
    notificar(
        evaluacion.profesor,
        'Una evaluación llegó a su fin',
        f'{evaluacion.titulo} ({evaluacion.grupo.nombre}) se cerró al terminar '
        f'su plazo. La presentaron {presentaron} de {total} alumnos.',
        reverse('evaluaciones:detalle_evaluacion', args=[evaluacion.id]),
    )


def avisar_grupo_termino(evaluacion, total):
    """Avisa al profesor que ya no queda nadie presentando."""
    notificar(
        evaluacion.profesor,
        'Tu grupo terminó la evaluación',
        f'Los {total} alumnos de {evaluacion.grupo.nombre} ya entregaron '
        f'{evaluacion.titulo}. Puedes finalizarla y revisar los resultados.',
        reverse('evaluaciones:detalle_evaluacion', args=[evaluacion.id]),
    )
