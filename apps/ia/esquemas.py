"""
Estructura de lo que se le pide al modelo y de lo que se recibe.

La especificacion generica de LiteLLM propone enunciado, opciones, indice de la
correcta, una explicacion breve y una dificultad. Aqui hacen falta dos cosas
mas, sin las cuales el resto del sistema no funciona:

- expresion: la operacion de la que sale la respuesta. Es el insumo del
  verificador simbolico; sin ella no habria nada que comprobar.
- valores: el valor simbolico de cada opcion. El verificador compara
  expresiones, no cadenas de texto.

Y la explicacion breve se cambia por el procedimiento: los pasos para llegar al
resultado. Justificar en una oracion por que la respuesta es correcta no le
ensena nada al alumno; el procedimiento si.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PreguntaGenerada:
    """Una pregunta tal como la devolvio el modelo, antes de verificarse."""

    enunciado: str
    opciones: list
    indice_correcto: int
    procedimiento: str
    # La operacion de la que sale la respuesta, para el verificador simbolico.
    # Viene vacia en las materias que no son de matematicas.
    expresion: str = ''
    # Valor simbolico de cada opcion, en el mismo orden que opciones. Cuando el
    # modelo no lo entrega se usan las propias opciones.
    valores: list = field(default_factory=list)

    @property
    def respuesta_correcta(self):
        return self.opciones[self.indice_correcto]

    @property
    def valores_para_verificar(self):
        """Los valores simbolicos, o las opciones si no vinieron aparte."""
        return self.valores if self.valores else self.opciones


@dataclass(frozen=True)
class ResultadoGeneracion:
    """Lo que devuelve un lote, con los datos que necesita la bitacora."""

    preguntas: list
    modelo: str
    proveedor: str
    tokens_entrada: int
    tokens_salida: int
