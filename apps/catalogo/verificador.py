"""
Verificador simbolico de preguntas de matematicas.

Un modelo de lenguaje redacta preguntas convincentes y de vez en cuando se
equivoca en la aritmetica. En un sistema de evaluacion eso no es un detalle:
una clave de respuesta equivocada reprueba injustamente al alumno y le ensena
algo falso.

El error mas dificil de ver a simple vista son los distractores que en realidad
equivalen a la respuesta correcta. Una opcion dice "1/2" y otra dice "0.5"; una
dice "2*x" y otra "x + x". Como cadenas de texto son distintas, pero
matematicamente son la misma, y el alumno se queda con dos opciones correctas.
Comparar los textos no lo detecta; compararlos como expresiones si.

Este modulo no depende de la red ni de la base de datos, asi que se puede
probar por completo sin gastar un peso.

LIMITACIONES CONOCIDAS
----------------------

Aprobar aqui no significa que la pregunta sea buena. Significa unicamente que
no se le encontro ninguno de los errores que este modulo sabe buscar. Conviene
tener presentes sus huecos, que estan fijados en las pruebas de la clase
LimitesConocidosTest:

1. Comprueba consistencia interna, no veracidad. La respuesta se compara contra
   la expresion que venga declarada, NO contra el enunciado en prosa: esta
   funcion ni siquiera lo recibe. Una pregunta que diga "cuanto es 7 por 8" con
   la expresion "2+2" y la respuesta "4" se aprueba sin problema. La aritmetica
   es impecable y la pregunta es inservible. Detectar eso le toca al profesor.

2. Tampoco juzga el nivel de dificultad, la claridad de la redaccion ni si la
   pregunta corresponde a su categoria.

3. Solo cubre lo cuantitativo. En categorias como Comprension o Gramatica no
   hay expresion que revisar y el dictamen sale con aplica en falso.

4. Rechaza formatos que son legitimos: unidades ("5 cm"), ecuaciones ("x = 3"),
   incognitas de mas de una letra ("theta", "x1") y coma decimal ("0,5"). Eso
   no produce preguntas malas sino preguntas buenas descartadas, y se corrige
   diciendole al modelo en que formato debe responder, no aflojando estas
   reglas.

5. Las respuestas redondeadas se rechazan a proposito: 0.33 no es un tercio.
   Aceptarlas debilitaria la deteccion de distractores equivalentes, que es la
   regla mas valiosa del modulo.

6. Los numeros complejos se aceptan: la raiz de menos uno da I, que es un
   numero valido y no un valor indefinido, aunque quede fuera del temario de
   nivel medio superior.
"""

import re
from dataclasses import dataclass

import sympy
from sympy.parsing.sympy_parser import parse_expr, standard_transformations

# Numero de opciones que debe tener toda pregunta del sistema.
NUMERO_OPCIONES = 4

# Largo maximo de una expresion. Es un tope de sentido comun: mas alla de esto
# no hay preguntas de bachillerato, y evita que una expresion enredada deje a
# SymPy dando vueltas mucho tiempo.
LARGO_MAXIMO = 200

# Solo se aceptan estos caracteres. Es la primera barrera y la mas importante:
# lo que no pase de aqui nunca llega al analizador de SymPy.
CARACTERES_PERMITIDOS = re.compile(r'^[0-9a-zA-Z+\-*/^().,=<> \t]+$')

# Nombres que puede usar una expresion. Cualquier otro se rechaza, de modo que
# no se pueda alcanzar nada del interprete de Python desde el texto recibido.
NOMBRES_PERMITIDOS = {
    'sqrt': sympy.sqrt,
    'abs': sympy.Abs,
    'Abs': sympy.Abs,
    'log': sympy.log,
    'ln': sympy.log,
    'exp': sympy.exp,
    'sin': sympy.sin,
    'cos': sympy.cos,
    'tan': sympy.tan,
    'pi': sympy.pi,
    'e': sympy.E,
    'E': sympy.E,
}
# Las literales que se pueden usar como incognitas.
LETRAS_INCOGNITA = 'abcdmnpqrstuvwxyz'
for letra in LETRAS_INCOGNITA:
    NOMBRES_PERMITIDOS.setdefault(letra, sympy.Symbol(letra))

# El analizador de SymPy reescribe los numeros antes de evaluarlos: el "2" que
# uno escribe se convierte en Integer(2), y una literal suelta en Symbol('x').
# Por eso estos constructores tienen que estar disponibles aunque nadie los
# escriba a mano, o hasta "2 + 2" falla.
NOMBRES_PERMITIDOS.update({
    'Integer': sympy.Integer,
    'Float': sympy.Float,
    'Rational': sympy.Rational,
    'Symbol': sympy.Symbol,
})

# Palabras reservadas de Python. El filtro de caracteres no las ataja porque
# son puras letras, y aunque no permiten llamar a nada (las comillas, los
# corchetes y el guion bajo estan bloqueados) si dejarian evaluar sintaxis del
# lenguaje donde solo deberia haber matematicas: "1 if True else 2" no es una
# expresion matematica valida y no tiene por que pasar.
PALABRAS_RESERVADAS = {
    'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue',
    'def', 'del', 'elif', 'else', 'except', 'False', 'finally', 'for', 'from',
    'global', 'if', 'import', 'in', 'is', 'lambda', 'None', 'nonlocal', 'not',
    'or', 'pass', 'raise', 'return', 'True', 'try', 'while', 'with', 'yield',
}

# Nombres de incognita aceptables en el resultado. Sirve para atajar el texto
# que no es matematicas: "seis" pasaria el filtro de caracteres y el analizador
# lo convertiria en una incognita llamada seis, en lugar de rechazarlo.
INCOGNITAS_VALIDAS = set(LETRAS_INCOGNITA)


@dataclass
class Dictamen:
    """Resultado de revisar una pregunta.

    - aplica: falso cuando la pregunta no es de matematicas y por lo tanto no
      habia expresion que comprobar. En ese caso la revision queda enteramente
      en manos del profesor.
    - aprobada: si paso todas las reglas.
    - motivo: que regla fallo. Se le muestra al profesor, por eso va redactado
      en espanol corriente y no como codigo de error.
    """

    aprobada: bool
    aplica: bool
    motivo: str = ''


class ExpresionInvalida(ValueError):
    """La expresion no se pudo interpretar como matematicas."""


def interpretar(texto):
    """Convierte el texto en una expresion de SymPy, o levanta ExpresionInvalida.

    No se usa sympify sobre el texto recibido: esa funcion evalua lo que le
    llegue y es peligrosa con entradas que uno no escribio. Aqui se filtra
    primero por caracteres y despues se analiza con un diccionario de nombres
    cerrado, de modo que la expresion no pueda alcanzar nada mas.
    """
    if texto is None:
        raise ExpresionInvalida('La expresión viene vacía.')

    texto = str(texto).strip()
    if not texto:
        raise ExpresionInvalida('La expresión viene vacía.')
    if len(texto) > LARGO_MAXIMO:
        raise ExpresionInvalida('La expresión es demasiado larga.')
    if not CARACTERES_PERMITIDOS.match(texto):
        raise ExpresionInvalida('La expresión tiene caracteres que no se aceptan.')

    reservadas = PALABRAS_RESERVADAS.intersection(re.findall(r'[A-Za-z_]+', texto))
    if reservadas:
        raise ExpresionInvalida(
            'La expresión usa palabras del lenguaje de programación, '
            'no de las matemáticas.'
        )

    # En notacion escolar el acento circunflejo es la potencia, no el "o
    # exclusivo" que significa en Python.
    texto = texto.replace('^', '**')

    try:
        expresion = parse_expr(
            texto,
            global_dict=NOMBRES_PERMITIDOS,
            transformations=standard_transformations,
            evaluate=True,
        )
    except Exception:
        raise ExpresionInvalida('La expresión no se pudo interpretar.')

    if not isinstance(expresion, sympy.Basic):
        raise ExpresionInvalida('La expresión no es una operación matemática.')

    # Division entre cero, indeterminaciones e infinitos. SymPy no revienta con
    # ellos, los representa (zoo, nan, oo), asi que si no se atajan aqui una
    # pregunta cuya respuesta no existe podria darse por buena.
    if expresion.has(sympy.S.NaN, sympy.S.ComplexInfinity,
                     sympy.S.Infinity, sympy.S.NegativeInfinity):
        raise ExpresionInvalida(
            'La expresión no tiene un valor definido: hay una división entre '
            'cero, una indeterminación o un infinito.'
        )

    # Una palabra suelta como "seis" se convierte en una incognita con ese
    # nombre. Eso no es una expresion matematica, es texto, y hay que atajarlo.
    ajenas = {
        simbolo.name for simbolo in expresion.free_symbols
        if simbolo.name not in INCOGNITAS_VALIDAS
    }
    if ajenas:
        nombres = ', '.join(sorted(ajenas))
        raise ExpresionInvalida(f'La expresión usa nombres que no son matemáticas: {nombres}.')

    return expresion


# Margen para comparar numeros. Tiene que ser lo bastante estrecho para que
# 0.33 siga siendo distinto de 1/3 (se diferencian en 3 milesimas) y lo bastante
# holgado para absorber el error del punto flotante binario, que es del orden de
# la diezmilbillonesima parte.
TOLERANCIA = 1e-12


def _valor_numerico(expresion):
    """Regresa el valor de la expresion cuando no tiene incognitas, o None."""
    if expresion.free_symbols:
        return None
    try:
        valor = sympy.N(expresion, 25)
    except Exception:
        return None
    if not valor.is_number or valor.is_finite is False:
        return None
    return valor


def _casi_iguales(una, otra):
    """Compara dos numeros con un margen. Regresa None si alguno no es numero.

    Hace falta porque la computadora guarda los decimales en binario y ahi
    0.1 + 0.2 no da exactamente 0.3, aunque en decimal sean el mismo numero.
    Sin este margen se rechazarian preguntas correctas.
    """
    valor_una = _valor_numerico(una)
    valor_otra = _valor_numerico(otra)
    if valor_una is None or valor_otra is None:
        return None

    try:
        diferencia = abs(valor_una - valor_otra)
        # La escala hace que el margen sea absoluto cerca del cero y relativo
        # en los numeros grandes.
        escala = max(abs(valor_una), abs(valor_otra), 1)
        return bool(float(diferencia / escala) < TOLERANCIA)
    except Exception:
        return None


def son_equivalentes(una, otra):
    """Indica si dos expresiones valen lo mismo.

    Regresa None cuando no se pudo determinar. Quien llama decide que hacer con
    esa duda; aqui no se inventa una respuesta.
    """
    try:
        respuesta = una.equals(otra)
    except Exception:
        respuesta = None

    if respuesta is True:
        return True

    # Cuando las dos son numeros, la comparacion con margen es la que manda:
    # es la unica que ve iguales a 0.1 + 0.2 y 0.3.
    aproximado = _casi_iguales(una, otra)
    if aproximado is not None:
        return aproximado

    if respuesta is not None:
        return bool(respuesta)

    # equals no pudo decidir. Se intenta el camino de simplificar la resta.
    try:
        return sympy.simplify(una - otra) == 0
    except Exception:
        return None


def verificar(expresion, opciones, indice_correcta):
    """Revisa una pregunta de opcion multiple y regresa su Dictamen.

    - expresion: la operacion de la que sale la respuesta, por ejemplo "2 + 2".
      Si viene vacia se entiende que la pregunta no es de matematicas.
    - opciones: los valores de las cuatro opciones, como texto.
    - indice_correcta: posicion de la opcion marcada como correcta.

    Cuando una comprobacion no se puede resolver, la pregunta NO se aprueba.
    Mas vale mandarla a revision humana que dejar pasar una clave equivocada.
    """
    # Las preguntas que no son de matematicas no tienen nada que comprobar.
    if expresion is None or not str(expresion).strip():
        return Dictamen(aprobada=True, aplica=False)

    if len(opciones) != NUMERO_OPCIONES:
        return Dictamen(
            aprobada=False,
            aplica=True,
            motivo=f'La pregunta debe tener {NUMERO_OPCIONES} opciones y trae {len(opciones)}.',
        )

    if not 0 <= indice_correcta < NUMERO_OPCIONES:
        return Dictamen(
            aprobada=False,
            aplica=True,
            motivo='No se indicó cuál de las opciones es la correcta.',
        )

    # Primera regla: todo tiene que interpretarse.
    try:
        resultado = interpretar(expresion)
    except ExpresionInvalida as error:
        return Dictamen(aprobada=False, aplica=True, motivo=f'{error} (enunciado)')

    valores = []
    for numero, opcion in enumerate(opciones, start=1):
        try:
            valores.append(interpretar(opcion))
        except ExpresionInvalida as error:
            return Dictamen(
                aprobada=False,
                aplica=True,
                motivo=f'{error} (opción {numero})',
            )

    correcta = valores[indice_correcta]
    distractores = [
        (numero, valor)
        for numero, valor in enumerate(valores, start=1)
        if numero - 1 != indice_correcta
    ]

    # Segunda regla: la opcion marcada como correcta debe ser la que resulta
    # de la expresion. Aqui se cachan las claves de respuesta equivocadas.
    coincide = son_equivalentes(resultado, correcta)
    if coincide is None:
        return Dictamen(
            aprobada=False,
            aplica=True,
            motivo='No se pudo comprobar que la respuesta marcada sea la correcta.',
        )
    if not coincide:
        return Dictamen(
            aprobada=False,
            aplica=True,
            motivo=(
                f'La respuesta marcada como correcta no coincide con el resultado: '
                f'la expresión da {resultado} y la opción dice {correcta}.'
            ),
        )

    # Tercera regla: ningun distractor puede valer lo mismo que la correcta.
    # Este es el error que una comparacion de textos nunca detectaria.
    for numero, distractor in distractores:
        igual = son_equivalentes(correcta, distractor)
        if igual is None:
            return Dictamen(
                aprobada=False,
                aplica=True,
                motivo=f'No se pudo comparar la opción {numero} con la respuesta correcta.',
            )
        if igual:
            return Dictamen(
                aprobada=False,
                aplica=True,
                motivo=(
                    f'La opción {numero} ({distractor}) vale lo mismo que la '
                    f'respuesta correcta ({correcta}), así que habría dos correctas.'
                ),
            )

    # Cuarta regla: tampoco puede haber dos distractores iguales entre si, o el
    # alumno tendria tres opciones reales en lugar de cuatro.
    for posicion, (numero, distractor) in enumerate(distractores):
        for otro_numero, otro in distractores[posicion + 1:]:
            igual = son_equivalentes(distractor, otro)
            if igual is None:
                return Dictamen(
                    aprobada=False,
                    aplica=True,
                    motivo=f'No se pudieron comparar las opciones {numero} y {otro_numero}.',
                )
            if igual:
                return Dictamen(
                    aprobada=False,
                    aplica=True,
                    motivo=(
                        f'Las opciones {numero} y {otro_numero} valen lo mismo, '
                        f'así que en realidad solo hay tres opciones distintas.'
                    ),
                )

    return Dictamen(aprobada=True, aplica=True)
