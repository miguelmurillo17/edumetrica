"""Convierte el procedimiento entre las dos formas en que vive.

En la base de datos el procedimiento es un solo texto, un paso por linea y
numerado. En el formulario del profesor se captura como una lista de pasos, un
campo por paso, para que la estructura no dependa de que la persona recuerde
numerar ni respetar el formato. Estas dos funciones traducen de una forma a la
otra; la numeracion la pone el sistema, nunca el humano.
"""

import re

# Quita una numeracion escrita al inicio del paso ("1.", "2)", "3.-", "4 -"),
# venga del profesor que la tecleo de mas o del modelo que la devolvio asi. El
# sistema la vuelve a poner al guardar, para que no se duplique ni se descuadre.
_NUMERO_AL_INICIO = re.compile(r'^\s*\d+\s*[.)\-]+\s*')


def texto_a_pasos(texto):
    """Parte el procedimiento guardado en la lista de pasos, sin numeracion."""
    if not texto:
        return []
    pasos = []
    for linea in texto.splitlines():
        limpia = _NUMERO_AL_INICIO.sub('', linea).strip()
        if limpia:
            pasos.append(limpia)
    return pasos


def pasos_a_texto(pasos):
    """Une los pasos capturados en un texto, numerado y un paso por linea."""
    limpios = []
    for paso in pasos:
        limpia = _NUMERO_AL_INICIO.sub('', paso).strip()
        if limpia:
            limpios.append(limpia)
    return '\n'.join(
        f'{numero}. {paso}' for numero, paso in enumerate(limpios, start=1)
    )
