"""
Carga un banco de preguntas de matematicas capturadas a mano.

Sirve para tener con que trabajar sin depender del proveedor de inteligencia
artificial: son treinta preguntas de nivel medio superior repartidas en seis
categorias y seis niveles de dificultad, con su procedimiento para que el
alumno vea como se resuelve lo que fallo.

Cada pregunta pasa por el mismo verificador simbolico que revisa a las
generadas antes de guardarse. No es un adorno: comprueba que la opcion marcada
sea de verdad el resultado de la operacion y que ningun distractor equivalga a
la respuesta correcta, que es el error mas dificil de ver leyendo.

Las preguntas quedan con origen manual, porque las escribio una persona y no el
modelo. Mezclarlas con las generadas falsearia las metricas del capitulo de
resultados.

    python manage.py banco_matematicas

Se puede correr las veces que haga falta: las preguntas que ya existen no se
vuelven a dar de alta.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalogo.models import (
    Categoria, Materia, Nivel, OpcionRespuesta, Pregunta,
)
from apps.catalogo.verificador import verificar
from apps.usuarios.models import Persona


# Cada pregunta trae dos cosas distintas a proposito. El texto de las opciones
# es lo que lee el alumno, con su ortografia y sus unidades; los valores son
# los que revisa el verificador, que no entiende ni unidades ni simbolos y
# necesita la expresion en caracteres simples.
PREGUNTAS = [
    # ------------------------------------------------------------------ #
    # Aritmetica
    # ------------------------------------------------------------------ #
    {
        'categoria': 'Aritmética',
        'nivel': 1,
        'enunciado': '¿Cuál es el resultado de 2 + 3 × 4?',
        'expresion': '2 + 3*4',
        'opciones': ['14', '20', '24', '11'],
        'valores': ['14', '20', '24', '11'],
        'correcta': 0,
        'procedimiento': (
            'La multiplicación se resuelve antes que la suma.\n'
            'Primero 3 × 4 = 12.\n'
            'Después 2 + 12 = 14.\n'
            'Si sumas primero obtienes 20, que es el error más común.'
        ),
    },
    {
        'categoria': 'Aritmética',
        'nivel': 1,
        'enunciado': '¿Cuánto es 3/4 + 1/6?',
        'expresion': '3/4 + 1/6',
        'opciones': ['11/12', '2/5', '1', '7/12'],
        'valores': ['11/12', '2/5', '1', '7/12'],
        'correcta': 0,
        'procedimiento': (
            'Para sumar fracciones hacen falta denominadores iguales.\n'
            'El mínimo común múltiplo de 4 y 6 es 12.\n'
            '3/4 = 9/12 y 1/6 = 2/12.\n'
            '9/12 + 2/12 = 11/12.'
        ),
    },
    {
        'categoria': 'Aritmética',
        'nivel': 2,
        'enunciado': (
            'Un artículo cuesta $850 y está rebajado 20 %. '
            '¿Cuánto se paga por él?'
        ),
        'expresion': '850*(1 - 20/100)',
        'opciones': ['$680', '$170', '$830', '$700'],
        'valores': ['680', '170', '830', '700'],
        'correcta': 0,
        'procedimiento': (
            'El descuento es 20 % de 850, es decir 850 × 0.20 = 170.\n'
            'Lo que se paga es el precio menos el descuento.\n'
            '850 − 170 = 680.\n'
            'También puedes pagar el 80 %: 850 × 0.80 = 680.'
        ),
    },
    {
        'categoria': 'Aritmética',
        'nivel': 2,
        'enunciado': '¿Cuál es el resultado de (−5) + (8)(−2)?',
        'expresion': '-5 + 8*(-2)',
        'opciones': ['−21', '−26', '11', '21'],
        'valores': ['-21', '-26', '11', '21'],
        'correcta': 0,
        'procedimiento': (
            'Primero la multiplicación: 8 × (−2) = −16.\n'
            'Un positivo por un negativo da negativo.\n'
            'Luego la suma: −5 + (−16) = −21.'
        ),
    },
    {
        'categoria': 'Aritmética',
        'nivel': 3,
        'enunciado': '¿Cuánto vale √144 + √81?',
        'expresion': 'sqrt(144) + sqrt(81)',
        'opciones': ['21', '15', '225', '3'],
        'valores': ['21', '15', '225', '3'],
        'correcta': 0,
        'procedimiento': (
            'Cada raíz se resuelve por separado.\n'
            '√144 = 12, porque 12 × 12 = 144.\n'
            '√81 = 9, porque 9 × 9 = 81.\n'
            '12 + 9 = 21.\n'
            'Ojo: la raíz de una suma no es la suma de las raíces.'
        ),
    },

    # ------------------------------------------------------------------ #
    # Algebra
    # ------------------------------------------------------------------ #
    {
        'categoria': 'Álgebra',
        'nivel': 2,
        'enunciado': 'Si 3x + 7 = 22, ¿cuánto vale x?',
        'expresion': '(22 - 7)/3',
        'opciones': ['5', '3', '15', '29/3'],
        'valores': ['5', '3', '15', '29/3'],
        'correcta': 0,
        'procedimiento': (
            'Se despeja x dejándola sola de un lado.\n'
            'Restas 7 en los dos lados: 3x = 22 − 7 = 15.\n'
            'Divides entre 3 en los dos lados: x = 15 / 3 = 5.\n'
            'Comprueba: 3(5) + 7 = 22.'
        ),
    },
    {
        'categoria': 'Álgebra',
        'nivel': 2,
        'enunciado': '¿Cuánto vale 2x² − 3x + 1 cuando x = 4?',
        'expresion': '2*4^2 - 3*4 + 1',
        'opciones': ['21', '53', '45', '17'],
        'valores': ['21', '53', '45', '17'],
        'correcta': 0,
        'procedimiento': (
            'Sustituyes x por 4 en cada término.\n'
            'El exponente va antes que la multiplicación: 4² = 16.\n'
            '2(16) = 32, y 3(4) = 12.\n'
            '32 − 12 + 1 = 21.'
        ),
    },
    {
        'categoria': 'Álgebra',
        'nivel': 3,
        'enunciado': '¿Cuál es el desarrollo de (x + 3)(x − 3)?',
        'expresion': '(x + 3)*(x - 3)',
        'opciones': ['x² − 9', 'x² + 9', 'x² − 6x + 9', 'x² + 6x − 9'],
        'valores': ['x^2 - 9', 'x^2 + 9', 'x^2 - 6*x + 9', 'x^2 + 6*x - 9'],
        'correcta': 0,
        'procedimiento': (
            'Es el producto de una suma por su diferencia.\n'
            'Al multiplicar término a término, −3x y +3x se cancelan.\n'
            'Queda el cuadrado del primero menos el cuadrado del segundo.\n'
            'x² − 9.'
        ),
    },
    {
        'categoria': 'Álgebra',
        'nivel': 3,
        'enunciado': 'Simplifica la expresión (x² − 4) / (x − 2), con x ≠ 2.',
        'expresion': '(x^2 - 4)/(x - 2)',
        'opciones': ['x + 2', 'x − 2', '2x', 'x² − 2'],
        'valores': ['x + 2', 'x - 2', '2*x', 'x^2 - 2'],
        'correcta': 0,
        'procedimiento': (
            'El numerador es una diferencia de cuadrados.\n'
            'x² − 4 = (x + 2)(x − 2).\n'
            'La expresión queda (x + 2)(x − 2) / (x − 2).\n'
            'Se cancela (x − 2) y sobra x + 2.'
        ),
    },
    {
        'categoria': 'Álgebra',
        'nivel': 4,
        'enunciado': 'De las raíces de x² − 5x + 6 = 0, ¿cuál es la mayor?',
        'expresion': '(5 + sqrt(5^2 - 4*6))/2',
        'opciones': ['3', '2', '6', '5'],
        'valores': ['3', '2', '6', '5'],
        'correcta': 0,
        'procedimiento': (
            'Buscas dos números que multiplicados den 6 y sumados den 5.\n'
            'Son 2 y 3, así que x² − 5x + 6 = (x − 2)(x − 3).\n'
            'Las raíces son x = 2 y x = 3.\n'
            'La mayor es 3.'
        ),
    },

    # ------------------------------------------------------------------ #
    # Geometria
    # ------------------------------------------------------------------ #
    {
        'categoria': 'Geometría',
        'nivel': 1,
        'enunciado': (
            '¿Cuál es el área de un triángulo de 12 cm de base '
            'y 7 cm de altura?'
        ),
        'expresion': '12*7/2',
        'opciones': ['42 cm²', '84 cm²', '19 cm²', '38 cm²'],
        'valores': ['42', '84', '19', '38'],
        'correcta': 0,
        'procedimiento': (
            'El área de un triángulo es base por altura entre dos.\n'
            '12 × 7 = 84.\n'
            '84 / 2 = 42 cm².\n'
            'Olvidar dividir entre dos da 84, que es el área del rectángulo.'
        ),
    },
    {
        'categoria': 'Geometría',
        'nivel': 1,
        'enunciado': (
            '¿Cuál es el perímetro de un rectángulo de 8 m de largo '
            'y 5 m de ancho?'
        ),
        'expresion': '2*(8 + 5)',
        'opciones': ['26 m', '40 m', '13 m', '80 m'],
        'valores': ['26', '40', '13', '80'],
        'correcta': 0,
        'procedimiento': (
            'El perímetro es la suma de los cuatro lados.\n'
            'Hay dos lados de 8 y dos de 5.\n'
            '2(8) + 2(5) = 16 + 10 = 26 m.\n'
            'Si multiplicas en vez de sumar obtienes el área, que son 40 m².'
        ),
    },
    {
        'categoria': 'Geometría',
        'nivel': 3,
        'enunciado': (
            'En un triángulo rectángulo los catetos miden 9 cm y 12 cm. '
            '¿Cuánto mide la hipotenusa?'
        ),
        'expresion': 'sqrt(9^2 + 12^2)',
        'opciones': ['15 cm', '21 cm', '10.5 cm', '225 cm'],
        'valores': ['15', '21', '21/2', '225'],
        'correcta': 0,
        'procedimiento': (
            'Por el teorema de Pitágoras, la hipotenusa al cuadrado es la '
            'suma de los cuadrados de los catetos.\n'
            '9² + 12² = 81 + 144 = 225.\n'
            'La hipotenusa es √225 = 15 cm.\n'
            'Sumar los catetos sin elevarlos al cuadrado da 21 y es incorrecto.'
        ),
    },
    {
        'categoria': 'Geometría',
        'nivel': 3,
        'enunciado': '¿Cuál es el área de un círculo de 5 cm de radio?',
        'expresion': 'pi*5^2',
        'opciones': ['25π cm²', '10π cm²', '5π cm²', '50π cm²'],
        'valores': ['25*pi', '10*pi', '5*pi', '50*pi'],
        'correcta': 0,
        'procedimiento': (
            'El área de un círculo es π por el radio al cuadrado.\n'
            'El radio es 5, así que 5² = 25.\n'
            'El área es 25π cm².\n'
            '10π es el perímetro, no el área.'
        ),
    },
    {
        'categoria': 'Geometría',
        'nivel': 4,
        'enunciado': (
            '¿Cuál es el volumen de un cilindro de 3 cm de radio '
            'y 10 cm de altura?'
        ),
        'expresion': 'pi*3^2*10',
        'opciones': ['90π cm³', '60π cm³', '30π cm³', '900π cm³'],
        'valores': ['90*pi', '60*pi', '30*pi', '900*pi'],
        'correcta': 0,
        'procedimiento': (
            'El volumen de un cilindro es el área de la base por la altura.\n'
            'La base es un círculo de radio 3: π(3²) = 9π.\n'
            'Multiplicas por la altura: 9π × 10 = 90π cm³.'
        ),
    },

    # ------------------------------------------------------------------ #
    # Trigonometria
    # ------------------------------------------------------------------ #
    {
        'categoria': 'Trigonometría',
        'nivel': 3,
        'enunciado': '¿Cuánto vale sen 30°?',
        'expresion': 'sin(pi/6)',
        'opciones': ['1/2', '√3/2', '√2/2', '1'],
        'valores': ['1/2', 'sqrt(3)/2', 'sqrt(2)/2', '1'],
        'correcta': 0,
        'procedimiento': (
            'Es uno de los ángulos notables que conviene memorizar.\n'
            'En un triángulo rectángulo con un ángulo de 30°, el cateto '
            'opuesto mide la mitad de la hipotenusa.\n'
            'Por eso sen 30° = 1/2.\n'
            'Cuidado: √3/2 es el coseno de 30°, no su seno.'
        ),
    },
    {
        'categoria': 'Trigonometría',
        'nivel': 3,
        'enunciado': '¿Cuánto vale tan 45°?',
        'expresion': 'tan(pi/4)',
        'opciones': ['1', '0', '√3', '√3/3'],
        'valores': ['1', '0', 'sqrt(3)', 'sqrt(3)/3'],
        'correcta': 0,
        'procedimiento': (
            'La tangente es el cateto opuesto entre el adyacente.\n'
            'En un ángulo de 45° los dos catetos miden lo mismo.\n'
            'Al dividir un número entre sí mismo el resultado es 1.'
        ),
    },
    {
        'categoria': 'Trigonometría',
        'nivel': 4,
        'enunciado': '¿Cuánto vale cos 30°?',
        'expresion': 'cos(pi/6)',
        'opciones': ['√3/2', '1/2', '√2/2', '2/√3'],
        'valores': ['sqrt(3)/2', '1/2', 'sqrt(2)/2', '2/sqrt(3)'],
        'correcta': 0,
        'procedimiento': (
            'Es otro de los ángulos notables.\n'
            'En el triángulo de 30° y 60°, el cateto adyacente al ángulo de '
            '30° mide √3/2 de la hipotenusa.\n'
            'Por eso cos 30° = √3/2, un poco menos que 1.'
        ),
    },
    {
        'categoria': 'Trigonometría',
        'nivel': 4,
        'enunciado': (
            'En un triángulo rectángulo la hipotenusa mide 13 cm y un cateto '
            'mide 5 cm. ¿Cuánto mide el otro cateto?'
        ),
        'expresion': 'sqrt(13^2 - 5^2)',
        'opciones': ['12 cm', '8 cm', '18 cm', '√194 cm'],
        'valores': ['12', '8', '18', 'sqrt(194)'],
        'correcta': 0,
        'procedimiento': (
            'Aquí Pitágoras se usa al revés: se despeja el cateto que falta.\n'
            'El cateto al cuadrado es 13² − 5² = 169 − 25 = 144.\n'
            'El cateto es √144 = 12 cm.\n'
            'Restar directamente 13 − 5 da 8 y es incorrecto.'
        ),
    },
    {
        'categoria': 'Trigonometría',
        'nivel': 5,
        'enunciado': '¿A qué es igual sen²x + cos²x para cualquier ángulo x?',
        'expresion': 'sin(x)^2 + cos(x)^2',
        'opciones': ['1', '0', '2 sen x cos x', 'cos²x − sen²x'],
        'valores': ['1', '0', '2*sin(x)*cos(x)', 'cos(x)^2 - sin(x)^2'],
        'correcta': 0,
        'procedimiento': (
            'Es la identidad pitagórica, la más usada de la trigonometría.\n'
            'Sale de aplicar el teorema de Pitágoras a un triángulo cuya '
            'hipotenusa vale 1.\n'
            'Vale 1 para cualquier ángulo, no solo para algunos.'
        ),
    },

    # ------------------------------------------------------------------ #
    # Geometria analitica
    # ------------------------------------------------------------------ #
    {
        'categoria': 'Geometría analítica',
        'nivel': 3,
        'enunciado': '¿Cuál es la distancia entre los puntos (1, 2) y (4, 6)?',
        'expresion': 'sqrt((4 - 1)^2 + (6 - 2)^2)',
        'opciones': ['5', '7', '25', '√7'],
        'valores': ['5', '7', '25', 'sqrt(7)'],
        'correcta': 0,
        'procedimiento': (
            'La distancia sale del teorema de Pitágoras sobre las diferencias '
            'de cada coordenada.\n'
            'La diferencia en x es 4 − 1 = 3, y en y es 6 − 2 = 4.\n'
            '√(3² + 4²) = √(9 + 16) = √25 = 5.'
        ),
    },
    {
        'categoria': 'Geometría analítica',
        'nivel': 3,
        'enunciado': (
            '¿Cuál es la pendiente de la recta que pasa por '
            '(2, 3) y (6, 11)?'
        ),
        'expresion': '(11 - 3)/(6 - 2)',
        'opciones': ['2', '1/2', '4', '8'],
        'valores': ['2', '1/2', '4', '8'],
        'correcta': 0,
        'procedimiento': (
            'La pendiente es cuánto sube la recta por cada unidad que avanza.\n'
            'Se divide la diferencia de las y entre la diferencia de las x.\n'
            '(11 − 3) / (6 − 2) = 8 / 4 = 2.\n'
            'Invertir la división da 1/2 y es el error típico.'
        ),
    },
    {
        'categoria': 'Geometría analítica',
        'nivel': 4,
        'enunciado': (
            '¿Cuál es la abscisa, es decir la coordenada x, del punto medio '
            'entre (−2, 4) y (6, 10)?'
        ),
        'expresion': '(-2 + 6)/2',
        'opciones': ['2', '4', '7', '−4'],
        'valores': ['2', '4', '7', '-4'],
        'correcta': 0,
        'procedimiento': (
            'La coordenada x del punto medio es el promedio de las dos x.\n'
            '(−2 + 6) / 2 = 4 / 2 = 2.\n'
            'El 7 sería la coordenada y, que se calcula igual con las y.'
        ),
    },
    {
        'categoria': 'Geometría analítica',
        'nivel': 4,
        'enunciado': 'En la recta y = 3x − 5, ¿cuánto vale y cuando x = 4?',
        'expresion': '3*4 - 5',
        'opciones': ['7', '17', '12', '−5'],
        'valores': ['7', '17', '12', '-5'],
        'correcta': 0,
        'procedimiento': (
            'Sustituyes x por 4 en la ecuación de la recta.\n'
            'y = 3(4) − 5.\n'
            'y = 12 − 5 = 7.\n'
            'El −5 es la ordenada al origen, el valor de y cuando x vale cero.'
        ),
    },
    {
        'categoria': 'Geometría analítica',
        'nivel': 5,
        'enunciado': (
            'La circunferencia x² + y² = 49 tiene su centro en el origen. '
            '¿Cuánto mide su radio?'
        ),
        'expresion': 'sqrt(49)',
        'opciones': ['7', '49', '24.5', '14'],
        'valores': ['7', '49', '49/2', '14'],
        'correcta': 0,
        'procedimiento': (
            'La ecuación de una circunferencia con centro en el origen es '
            'x² + y² = r².\n'
            'Aquí r² = 49.\n'
            'El radio es √49 = 7.\n'
            'El 49 es el radio al cuadrado, no el radio.'
        ),
    },

    # ------------------------------------------------------------------ #
    # Probabilidad y estadistica
    # ------------------------------------------------------------------ #
    {
        'categoria': 'Probabilidad y estadística',
        'nivel': 2,
        'enunciado': '¿Cuál es la media aritmética de 4, 8, 10 y 14?',
        'expresion': '(4 + 8 + 10 + 14)/4',
        'opciones': ['9', '36', '10', '8'],
        'valores': ['9', '36', '10', '8'],
        'correcta': 0,
        'procedimiento': (
            'La media es la suma de todos los datos entre cuántos son.\n'
            '4 + 8 + 10 + 14 = 36.\n'
            'Son cuatro datos: 36 / 4 = 9.'
        ),
    },
    {
        'categoria': 'Probabilidad y estadística',
        'nivel': 2,
        'enunciado': (
            'Al lanzar un dado de seis caras, ¿cuál es la probabilidad de '
            'que salga un número par?'
        ),
        'expresion': '3/6',
        'opciones': ['1/2', '1/3', '2/3', '1/6'],
        'valores': ['1/2', '1/3', '2/3', '1/6'],
        'correcta': 0,
        'procedimiento': (
            'Los casos favorables son los pares: 2, 4 y 6, o sea tres.\n'
            'Los casos posibles son las seis caras.\n'
            '3 / 6 = 1/2.'
        ),
    },
    {
        'categoria': 'Probabilidad y estadística',
        'nivel': 3,
        'enunciado': (
            'Si lanzas una moneda dos veces, ¿cuál es la probabilidad de '
            'obtener águila las dos veces?'
        ),
        'expresion': '(1/2)*(1/2)',
        'opciones': ['1/4', '1/2', '1', '3/4'],
        'valores': ['1/4', '1/2', '1', '3/4'],
        'correcta': 0,
        'procedimiento': (
            'Los dos lanzamientos son independientes: el primero no cambia '
            'lo que pasa en el segundo.\n'
            'En ese caso las probabilidades se multiplican.\n'
            '1/2 × 1/2 = 1/4.\n'
            'Sumarlas daría 1, que significaría certeza y no tiene sentido.'
        ),
    },
    {
        'categoria': 'Probabilidad y estadística',
        'nivel': 4,
        'enunciado': (
            'De una baraja de 52 cartas se saca una al azar. '
            '¿Cuál es la probabilidad de que sea un as?'
        ),
        'expresion': '4/52',
        'opciones': ['1/13', '1/52', '1/4', '4/13'],
        'valores': ['1/13', '1/52', '1/4', '4/13'],
        'correcta': 0,
        'procedimiento': (
            'En una baraja hay cuatro ases, uno por cada palo.\n'
            'La probabilidad es 4 entre 52.\n'
            'Al simplificar dividiendo ambos entre 4 queda 1/13.'
        ),
    },
    {
        'categoria': 'Probabilidad y estadística',
        'nivel': 5,
        'enunciado': (
            '¿De cuántas maneras distintas se pueden elegir 2 personas '
            'de un grupo de 5, sin importar el orden?'
        ),
        'expresion': '5*4/2',
        'opciones': ['10', '20', '25', '5'],
        'valores': ['10', '20', '25', '5'],
        'correcta': 0,
        'procedimiento': (
            'Para la primera persona hay 5 opciones y para la segunda quedan 4, '
            'lo que da 20 parejas ordenadas.\n'
            'Como el orden no importa, cada pareja se contó dos veces.\n'
            '20 / 2 = 10.'
        ),
    },
]


class Command(BaseCommand):
    help = 'Carga treinta preguntas de matematicas capturadas a mano y verificadas.'

    def handle(self, *args, **opciones):
        materia, _ = Materia.objects.get_or_create(
            nombre='Matemáticas',
            defaults={'es_cuantitativa': True},
        )
        # Si la materia ya existia sin la bandera, se corrige: sus preguntas
        # generadas tienen que traer expresion o se saltarian el verificador.
        if not materia.es_cuantitativa:
            materia.es_cuantitativa = True
            materia.save(update_fields=['es_cuantitativa'])

        # El profesor de ejemplo queda como autor cuando existe.
        autor = Persona.objects.filter(rol=Persona.Rol.PROFESOR).first()

        creadas = 0
        repetidas = 0
        rechazadas = []

        for datos in PREGUNTAS:
            # La misma comprobacion por la que pasan las preguntas generadas.
            dictamen = verificar(
                datos['expresion'], datos['valores'], datos['correcta']
            )
            if not dictamen.aprobada:
                rechazadas.append((datos['enunciado'], dictamen.motivo))
                continue

            if Pregunta.objects.filter(enunciado=datos['enunciado']).exists():
                repetidas += 1
                continue

            categoria, _ = Categoria.objects.get_or_create(
                materia=materia, nombre=datos['categoria']
            )
            nivel = Nivel.objects.get(numero=datos['nivel'])

            with transaction.atomic():
                pregunta = Pregunta.objects.create(
                    materia=materia,
                    categoria=categoria,
                    nivel=nivel,
                    enunciado=datos['enunciado'],
                    procedimiento=datos['procedimiento'],
                    creada_por=autor,
                    origen=Pregunta.Origen.MANUAL,
                    estado=Pregunta.Estado.VALIDADA,
                    verificada_simbolicamente=True,
                )
                for posicion, texto in enumerate(datos['opciones']):
                    OpcionRespuesta.objects.create(
                        pregunta=pregunta,
                        texto=texto,
                        es_correcta=(posicion == datos['correcta']),
                    )
            creadas += 1

        for enunciado, motivo in rechazadas:
            self.stdout.write(self.style.ERROR(
                f'RECHAZADA: {enunciado}\n           {motivo}'
            ))

        self.stdout.write(self.style.SUCCESS(
            f'{creadas} preguntas nuevas, {repetidas} ya existían, '
            f'{len(rechazadas)} rechazadas por el verificador.'
        ))
