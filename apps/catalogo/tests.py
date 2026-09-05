"""
Pruebas de la compuerta de validacion de preguntas y del verificador simbolico.

Solo las preguntas activas y validadas pueden entrar a una evaluacion. Es la
regla que impide que una pregunta generada por inteligencia artificial llegue
a un examen real sin que nadie la haya revisado, asi que conviene tenerla
amarrada con pruebas.
"""

from django.test import TestCase, SimpleTestCase

from .models import Materia, Categoria, Nivel, Pregunta
from .verificador import (
    verificar, interpretar, son_equivalentes, ExpresionInvalida,
)


class PreguntasUtilizablesTest(TestCase):
    """Revisa que el filtro de preguntas utilizables deje pasar lo correcto."""

    def setUp(self):
        self.materia = Materia.objects.create(nombre='Matemáticas')
        self.categoria = Categoria.objects.create(
            materia=self.materia, nombre='Álgebra'
        )
        self.nivel = Nivel.objects.create(numero=1, nombre='Básico')

    def crear_pregunta(self, **campos):
        """Arma una pregunta con lo minimo y los campos que se le indiquen."""
        datos = {
            'materia': self.materia,
            'categoria': self.categoria,
            'nivel': self.nivel,
            'enunciado': 'Cuanto es 2 + 2?',
        }
        datos.update(campos)
        return Pregunta.objects.create(**datos)

    def test_una_pregunta_nace_en_borrador(self):
        # El valor por omision es borrador a proposito: si una ruta nueva
        # olvida marcarla, se queda fuera en lugar de colarse sin revision.
        pregunta = self.crear_pregunta()
        self.assertEqual(pregunta.estado, Pregunta.Estado.BORRADOR)
        self.assertFalse(pregunta.es_utilizable)

    def test_la_validada_si_es_utilizable(self):
        pregunta = self.crear_pregunta(estado=Pregunta.Estado.VALIDADA)
        self.assertTrue(pregunta.es_utilizable)
        self.assertIn(pregunta, Pregunta.objects.utilizables())

    def test_el_borrador_no_entra(self):
        self.crear_pregunta(estado=Pregunta.Estado.BORRADOR)
        self.assertEqual(Pregunta.objects.utilizables().count(), 0)

    def test_la_descartada_no_entra(self):
        self.crear_pregunta(estado=Pregunta.Estado.DESCARTADA)
        self.assertEqual(Pregunta.objects.utilizables().count(), 0)

    def test_la_validada_pero_inactiva_no_entra(self):
        # Dar de baja una pregunta vieja es distinto de no haberla revisado,
        # pero cualquiera de las dos cosas la deja fuera de las evaluaciones.
        self.crear_pregunta(estado=Pregunta.Estado.VALIDADA, activa=False)
        self.assertEqual(Pregunta.objects.utilizables().count(), 0)

    def test_solo_cuenta_las_utilizables_entre_varias(self):
        self.crear_pregunta(estado=Pregunta.Estado.VALIDADA)
        self.crear_pregunta(estado=Pregunta.Estado.VALIDADA)
        self.crear_pregunta(estado=Pregunta.Estado.BORRADOR)
        self.crear_pregunta(estado=Pregunta.Estado.DESCARTADA)
        self.crear_pregunta(estado=Pregunta.Estado.VALIDADA, activa=False)

        self.assertEqual(Pregunta.objects.count(), 5)
        self.assertEqual(Pregunta.objects.utilizables().count(), 2)


class InterpretarExpresionesTest(SimpleTestCase):
    """Revisa el analisis de expresiones y su barrera de seguridad."""

    def test_interpreta_una_operacion_sencilla(self):
        self.assertEqual(interpretar('2 + 2'), 4)

    def test_el_acento_circunflejo_es_potencia(self):
        # En notacion escolar 2^3 son ocho, no el "o exclusivo" de Python.
        self.assertEqual(interpretar('2^3'), 8)

    def test_rechaza_una_expresion_mal_formada(self):
        # Debe levantar la excepcion propia, no reventar de otra manera.
        with self.assertRaises(ExpresionInvalida):
            interpretar('2 +* / 3')

    def test_rechaza_caracteres_que_no_son_matematicas(self):
        # La primera barrera: lo que trae simbolos raros nunca llega a SymPy.
        for texto in ['__import__("os")', 'open("/etc/passwd")', '2 + 2; print(1)']:
            with self.assertRaises(ExpresionInvalida):
                interpretar(texto)

    def test_rechaza_nombres_fuera_de_la_lista(self):
        # "eval" solo tiene letras, asi que pasa el filtro de caracteres; lo
        # que lo detiene es el diccionario cerrado de nombres.
        with self.assertRaises(ExpresionInvalida):
            interpretar('eval(1)')

    def test_rechaza_lo_que_no_tiene_valor_definido(self):
        # SymPy no revienta con estos: los representa como zoo, nan u oo. Si no
        # se atajan, una pregunta cuya respuesta no existe se daria por buena.
        for texto in ['1/0', '0/0', '1/0 + 1']:
            with self.assertRaises(ExpresionInvalida):
                interpretar(texto)

    def test_rechaza_sintaxis_de_python(self):
        # Estas son puras letras, asi que el filtro de caracteres no las ataja;
        # las detiene la lista de palabras reservadas.
        for texto in ['1 if True else 2', '1 and 2', 'not 1', '1 or 2']:
            with self.assertRaises(ExpresionInvalida):
                interpretar(texto)

    def test_rechaza_una_expresion_larguisima(self):
        with self.assertRaises(ExpresionInvalida):
            interpretar('1+' * 500 + '1')

    def test_rechaza_lo_vacio(self):
        for texto in ['', '   ', None]:
            with self.assertRaises(ExpresionInvalida):
                interpretar(texto)


class EquivalenciaTest(SimpleTestCase):
    """Los casos que una comparacion de textos no detectaria."""

    def comparar(self, una, otra):
        return son_equivalentes(interpretar(una), interpretar(otra))

    def test_un_medio_y_cero_punto_cinco_son_lo_mismo(self):
        self.assertTrue(self.comparar('1/2', '0.5'))

    def test_dos_equis_y_equis_mas_equis_son_lo_mismo(self):
        self.assertTrue(self.comparar('2*x', 'x + x'))

    def test_raiz_de_cuatro_y_dos_son_lo_mismo(self):
        self.assertTrue(self.comparar('sqrt(4)', '2'))

    def test_el_punto_flotante_binario_no_estorba(self):
        # La computadora guarda 0.1 y 0.2 en binario y su suma no da
        # exactamente 0.3, pero en decimal son el mismo numero y la pregunta
        # es correcta. Sin margen se rechazaria una pregunta buena.
        self.assertTrue(self.comparar('0.1 + 0.2', '0.3'))

    def test_el_margen_no_confunde_un_redondeo_con_el_valor_exacto(self):
        # El margen es estrecho a proposito: 0.33 sigue siendo distinto de un
        # tercio, o se debilitaria la regla de los distractores equivalentes.
        self.assertFalse(self.comparar('0.33', '1/3'))
        self.assertFalse(self.comparar('3.14', 'pi'))

    def test_valores_distintos_no_son_equivalentes(self):
        self.assertFalse(self.comparar('1/2', '1/3'))
        self.assertFalse(self.comparar('2*x', '3*x'))


class VerificarPreguntaTest(SimpleTestCase):
    """Revisa el dictamen completo de una pregunta."""

    def test_una_pregunta_correcta_pasa(self):
        dictamen = verificar('2 + 2', ['4', '5', '6', '3'], indice_correcta=0)
        self.assertTrue(dictamen.aprobada)
        self.assertTrue(dictamen.aplica)
        self.assertEqual(dictamen.motivo, '')

    def test_detecta_la_respuesta_mal_marcada(self):
        # La expresion da 4 pero se marco el 5 como correcto.
        dictamen = verificar('2 + 2', ['4', '5', '6', '3'], indice_correcta=1)
        self.assertFalse(dictamen.aprobada)
        self.assertIn('no coincide', dictamen.motivo)

    def test_detecta_un_distractor_equivalente_a_la_correcta(self):
        # 0.5 y 1/2 son la misma cosa: habria dos respuestas correctas.
        dictamen = verificar('1/2', ['1/2', '0.5', '1/3', '2'], indice_correcta=0)
        self.assertFalse(dictamen.aprobada)
        self.assertIn('vale lo mismo que la respuesta correcta', dictamen.motivo)

    def test_detecta_dos_distractores_iguales_entre_si(self):
        # 2*x y x+x dejan al alumno con tres opciones reales, no cuatro.
        dictamen = verificar('3*x', ['3*x', '2*x', 'x + x', '5*x'], indice_correcta=0)
        self.assertFalse(dictamen.aprobada)
        self.assertIn('solo hay tres opciones', dictamen.motivo)

    def test_rechaza_si_una_opcion_no_se_interpreta(self):
        dictamen = verificar('2 + 2', ['4', '5', 'seis', '3'], indice_correcta=0)
        self.assertFalse(dictamen.aprobada)
        self.assertIn('opción 3', dictamen.motivo)

    def test_rechaza_si_el_enunciado_no_se_interpreta(self):
        dictamen = verificar('2 +* 2', ['4', '5', '6', '3'], indice_correcta=0)
        self.assertFalse(dictamen.aprobada)
        self.assertIn('enunciado', dictamen.motivo)

    def test_rechaza_si_no_vienen_cuatro_opciones(self):
        dictamen = verificar('2 + 2', ['4', '5', '6'], indice_correcta=0)
        self.assertFalse(dictamen.aprobada)
        self.assertIn('4 opciones', dictamen.motivo)

    def test_rechaza_un_indice_de_correcta_fuera_de_lugar(self):
        dictamen = verificar('2 + 2', ['4', '5', '6', '3'], indice_correcta=9)
        self.assertFalse(dictamen.aprobada)
        self.assertIn('cuál de las opciones', dictamen.motivo)

    def test_sin_expresion_no_aplica_y_pasa_a_revision_humana(self):
        # Comprension o Gramatica no tienen expresion que comprobar.
        dictamen = verificar('', ['sujeto', 'predicado', 'verbo', 'adjetivo'],
                             indice_correcta=0)
        self.assertTrue(dictamen.aprobada)
        self.assertFalse(dictamen.aplica)

    def test_acepta_expresiones_con_incognita(self):
        dictamen = verificar('2*x + x', ['3*x', '2*x', 'x', '4*x'], indice_correcta=0)
        self.assertTrue(dictamen.aprobada)

    def test_rechaza_una_opcion_con_division_entre_cero(self):
        dictamen = verificar('2 + 2', ['4', '1/0', '6', '3'], indice_correcta=0)
        self.assertFalse(dictamen.aprobada)
        self.assertIn('valor definido', dictamen.motivo)

    def test_aprueba_una_suma_de_decimales(self):
        dictamen = verificar('0.1 + 0.2', ['0.3', '0.4', '0.5', '0.6'],
                             indice_correcta=0)
        self.assertTrue(dictamen.aprobada)

    def test_acepta_la_forma_equivalente_de_la_respuesta(self):
        # La opcion dice "0.5" y la expresion da 1/2: son lo mismo y debe pasar.
        dictamen = verificar('1/2', ['0.5', '1/3', '2/3', '1/4'], indice_correcta=0)
        self.assertTrue(dictamen.aprobada)


class LimitesConocidosTest(SimpleTestCase):
    """Deja fijados los huecos del verificador.

    Estas pruebas no describen lo que uno querria que pasara: describen lo que
    hoy pasa y por que se decidio dejarlo asi. Si alguien cambia alguno de
    estos comportamientos, la prueba fallara y tendra que venir a leer el
    motivo antes de darlo por bueno. Los mismos puntos estan explicados en el
    encabezado de verificador.py.
    """

    def test_no_compara_contra_el_enunciado_en_prosa(self):
        # HUECO PRINCIPAL. La funcion ni siquiera recibe el enunciado, asi que
        # una pregunta que diga "cuanto es 7 por 8" con la expresion "2+2" se
        # aprueba: la aritmetica cuadra y la pregunta es inservible. Esto es lo
        # que justifica que la validacion del profesor no sea opcional.
        dictamen = verificar('2 + 2', ['4', '5', '6', '7'], indice_correcta=0)
        self.assertTrue(dictamen.aprobada)

    def test_no_juzga_el_nivel_de_dificultad(self):
        # Una suma de primaria aprobada como si fuera nivel 6. El verificador
        # no tiene forma de opinar sobre eso.
        dictamen = verificar('1 + 1', ['2', '3', '4', '5'], indice_correcta=0)
        self.assertTrue(dictamen.aprobada)

    def test_rechaza_respuestas_con_unidades(self):
        # Falso rechazo conocido. Se corrige indicandole el formato al modelo,
        # no aflojando el verificador.
        dictamen = verificar('2 + 3', ['5 cm', '6 cm', '7 cm', '8 cm'],
                             indice_correcta=0)
        self.assertFalse(dictamen.aprobada)

    def test_rechaza_ecuaciones(self):
        # "x = 3" es la forma natural de media algebra de bachillerato y hoy no
        # se interpreta. Queda pendiente decidir si vale la pena soportarlo.
        dictamen = verificar('x = 3', ['x = 3', 'x = 4', 'x = 5', 'x = 6'],
                             indice_correcta=0)
        self.assertFalse(dictamen.aprobada)

    def test_rechaza_incognitas_de_mas_de_una_letra(self):
        # Solo se aceptan literales sueltas. "theta" o "x1" se rechazan.
        with self.assertRaises(ExpresionInvalida):
            interpretar('theta * 2')
        with self.assertRaises(ExpresionInvalida):
            interpretar('x1 + 1')

    def test_rechaza_la_coma_decimal(self):
        # En Mexico se escribe 0,5 tanto como 0.5, pero la coma es separador de
        # argumentos para el analizador.
        with self.assertRaises(ExpresionInvalida):
            interpretar('0,5 + 0,5')

    def test_rechaza_respuestas_redondeadas_a_proposito(self):
        # Decision deliberada, no un descuido: aceptar 0.33 como un tercio
        # debilitaria la deteccion de distractores equivalentes.
        dictamen = verificar('1/3', ['0.33', '0.5', '0.25', '0.75'],
                             indice_correcta=0)
        self.assertFalse(dictamen.aprobada)

    def test_acepta_numeros_complejos(self):
        # La raiz de menos uno da I, que es un numero valido y no un valor
        # indefinido, aunque quede fuera del temario de nivel medio superior.
        self.assertEqual(str(interpretar('sqrt(-1)')), 'I')
