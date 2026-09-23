"""Filtros de plantilla propios de las pantallas de reportes."""

import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def resaltar(texto, buscado):
    """Envuelve en <mark> cada aparicion de 'buscado' dentro de 'texto'.

    Se usa en el dialogo "Ver filtros aplicados" para mostrarle al profesor
    exactamente que parte del nombre de cada alumno coincidio con lo que
    escribio en el filtro de texto: una lista de "Flor Ramirez, Flor Gomez..."
    sola no dice si el texto encajo en el nombre, en el apellido o en los dos.
    """
    texto = str(texto)
    buscado = (buscado or '').strip()
    if not buscado:
        return texto

    patron = re.compile(re.escape(buscado), re.IGNORECASE)
    partes = []
    posicion = 0
    for coincidencia in patron.finditer(texto):
        partes.append(escape(texto[posicion:coincidencia.start()]))
        partes.append(f'<mark class="resaltado">{escape(coincidencia.group())}</mark>')
        posicion = coincidencia.end()
    partes.append(escape(texto[posicion:]))
    return mark_safe(''.join(partes))
