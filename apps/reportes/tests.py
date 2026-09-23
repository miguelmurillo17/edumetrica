"""
Pruebas del tablero y de la exportacion a CSV.

De aqui salen los numeros que se reportan en el capitulo de resultados, asi que
lo que se comprueba es que los promedios esten bien calculados y que cada quien
vea lo que le toca: el profesor sus evaluaciones y el administrador todas. Un
promedio mal filtrado no se nota a simple vista y contamina el analisis
completo.
"""

import csv
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalogo.models import (
    Categoria, Institucion, Materia, Nivel, OpcionRespuesta, Pregunta,
)
from apps.evaluaciones.models import (
    AsignacionDocente, Evaluacion, Grupo, IntentoEvaluacion, RespuestaAlumno,
)
from apps.usuarios.models import Persona
from apps.reportes.templatetags.reportes_extras import resaltar


class BaseTableroTest(TestCase):
    """Dos grupos, dos materias y dos profesores, para poder cruzar filtros."""

    def setUp(self):
        self.institucion = Institucion.objects.create(nombre='Preparatoria 1')
        self.nivel = Nivel.objects.create(numero=2, nombre='Elemental')

        self.matematicas = Materia.objects.create(
            nombre='Matemáticas', es_cuantitativa=True
        )
        self.literatura = Materia.objects.create(nombre='Literatura')
        self.aritmetica = Categoria.objects.create(
            materia=self.matematicas, nombre='Aritmética'
        )
        self.comprension = Categoria.objects.create(
            materia=self.literatura, nombre='Comprensión'
        )

        self.profesor = Persona.objects.create_user(
            correo='profesor@prueba.mx', nombre='Ana', apellido='Ruiz',
            password='Edumetrica2026', rol=Persona.Rol.PROFESOR,
        )
        self.otro_profesor = Persona.objects.create_user(
            correo='otro@prueba.mx', nombre='Eva', apellido='Pinto',
            password='Edumetrica2026', rol=Persona.Rol.PROFESOR,
        )
        self.administrador = Persona.objects.create_user(
            correo='admin@prueba.mx', nombre='Caro', apellido='Solís',
            password='Edumetrica2026', rol=Persona.Rol.ADMINISTRADOR,
        )

        self.primero = Grupo.objects.create(
            nombre='Primero A', institucion=self.institucion
        )
        self.segundo = Grupo.objects.create(
            nombre='Segundo B', institucion=self.institucion
        )
        # El profesor imparte ambas asignaturas en ambos grupos.
        for grupo in (self.primero, self.segundo):
            for categoria in (self.aritmetica, self.comprension):
                AsignacionDocente.objects.create(
                    grupo=grupo, profesor=self.profesor, categoria=categoria
                )

    def crear_alumno(self, correo, *, sexo='', edad=None, grupo=None,
                      nombre='Beto', apellido='Lara'):
        nacimiento = None
        if edad is not None:
            hoy = date.today()
            # Un dia despues del cumpleanos, para que la edad sea la pedida
            # sin depender de si ya paso o no este ano.
            nacimiento = hoy.replace(year=hoy.year - edad) - timedelta(days=1)
        alumno = Persona.objects.create_user(
            correo=correo, nombre=nombre, apellido=apellido,
            password='Edumetrica2026', rol=Persona.Rol.ALUMNO,
            sexo=sexo, fecha_nacimiento=nacimiento,
        )
        if grupo is not None:
            grupo.alumnos.add(alumno)
        return alumno

    def crear_pregunta(self, categoria, *, nivel=None, enunciado=None):
        pregunta = Pregunta.objects.create(
            materia=categoria.materia, categoria=categoria,
            nivel=nivel or self.nivel,
            enunciado=enunciado or '¿Cuánto es 2 + 3 por 4?',
            creada_por=self.profesor,
            estado=Pregunta.Estado.VALIDADA,
        )
        for posicion, texto in enumerate(['14', '20', '9', '24']):
            OpcionRespuesta.objects.create(
                pregunta=pregunta, texto=texto, es_correcta=(posicion == 0)
            )
        return pregunta

    def crear_evaluacion(self, *, grupo, materia, profesor=None, preguntas=()):
        ahora = timezone.now()
        evaluacion = Evaluacion.objects.create(
            titulo=f'Diagnóstico de {materia.nombre}',
            profesor=profesor or self.profesor,
            grupo=grupo, materia=materia,
            numero_preguntas=len(preguntas),
            fecha_inicio=ahora - timedelta(hours=2),
            fecha_fin=ahora - timedelta(hours=1),
            estado=Evaluacion.Estado.FINALIZADA,
        )
        evaluacion.preguntas.set(preguntas)
        return evaluacion

    def crear_intento(self, evaluacion, alumno, calificacion, *,
                      finalizado=True, aciertos=0):
        intento = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=alumno, calificacion=calificacion,
            estado=(
                IntentoEvaluacion.Estado.FINALIZADO if finalizado
                else IntentoEvaluacion.Estado.EN_CURSO
            ),
            fecha_fin=timezone.now() if finalizado else None,
        )
        for posicion, pregunta in enumerate(evaluacion.preguntas.all()):
            self.responder(intento, pregunta, posicion < aciertos)
        return intento

    def responder(self, intento, pregunta, acerto):
        opcion = pregunta.opciones.filter(es_correcta=acerto).first()
        return RespuestaAlumno.objects.create(
            intento=intento, pregunta=pregunta,
            opcion_seleccionada=opcion, es_correcta=acerto,
        )

    def tablero(self, **filtros):
        return self.client.get(reverse('reportes:dashboard'), filtros)


class ResumenTest(BaseTableroTest):
    """El promedio y el conteo que encabezan el tablero."""

    def setUp(self):
        super().setUp()
        self.alumno = self.crear_alumno('a1@prueba.mx', grupo=self.primero)
        self.otro = self.crear_alumno('a2@prueba.mx', grupo=self.primero)
        self.preguntas = [self.crear_pregunta(self.aritmetica) for _ in range(4)]
        self.evaluacion = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas,
            preguntas=self.preguntas,
        )
        self.client.force_login(self.profesor)

    def test_promedia_las_calificaciones(self):
        self.crear_intento(self.evaluacion, self.alumno, 80)
        self.crear_intento(self.evaluacion, self.otro, 60)

        resumen = self.tablero().context['resumen']

        self.assertEqual(resumen['total'], 2)
        self.assertEqual(float(resumen['promedio']), 70)

    def test_los_intentos_en_curso_no_cuentan(self):
        # Un alumno que va a la mitad no tiene calificacion final, y meterlo
        # en el promedio lo hunde sin que nadie lo note.
        self.crear_intento(self.evaluacion, self.alumno, 80)
        self.crear_intento(self.evaluacion, self.otro, 0, finalizado=False)

        resumen = self.tablero().context['resumen']

        self.assertEqual(resumen['total'], 1)
        self.assertEqual(float(resumen['promedio']), 80)

    def test_sin_datos_no_revienta(self):
        respuesta = self.tablero()

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['resumen']['total'], 0)
        self.assertIsNone(respuesta.context['resumen']['promedio'])


class QuienVeQueTest(BaseTableroTest):
    """El profesor ve sus evaluaciones; el administrador, todas."""

    def setUp(self):
        super().setUp()
        self.alumno = self.crear_alumno('a1@prueba.mx', grupo=self.primero)
        preguntas = [self.crear_pregunta(self.aritmetica) for _ in range(2)]

        self.mia = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas, preguntas=preguntas
        )
        self.ajena = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas,
            profesor=self.otro_profesor, preguntas=preguntas,
        )
        self.crear_intento(self.mia, self.alumno, 90)
        self.crear_intento(self.ajena, self.alumno, 10)

    def test_el_profesor_solo_ve_las_suyas(self):
        self.client.force_login(self.profesor)

        resumen = self.tablero().context['resumen']

        self.assertEqual(resumen['total'], 1)
        self.assertEqual(float(resumen['promedio']), 90)

    def test_el_administrador_las_ve_todas(self):
        self.client.force_login(self.administrador)

        resumen = self.tablero().context['resumen']

        self.assertEqual(resumen['total'], 2)
        self.assertEqual(float(resumen['promedio']), 50)

    def test_el_alumno_no_entra_al_tablero(self):
        self.client.force_login(self.alumno)

        self.assertEqual(self.tablero().status_code, 403)

    def test_el_profesor_solo_puede_filtrar_por_sus_grupos(self):
        ajeno = Grupo.objects.create(
            nombre='Tercero C', institucion=self.institucion
        )
        self.client.force_login(self.profesor)

        grupos = self.tablero().context['grupos']

        self.assertIn(self.primero, grupos)
        self.assertNotIn(ajeno, grupos)

    def test_el_profesor_no_ve_grupos_repetidos(self):
        # BaseTableroTest.setUp le da al profesor dos asignaturas en cada uno
        # de sus dos grupos: sin distinct() cada grupo saldria duplicado una
        # vez por asignatura, como se vio en el desplegable del tablero.
        self.client.force_login(self.profesor)

        grupos = self.tablero().context['grupos']

        self.assertEqual(grupos.count(), 2)

    def test_el_profesor_solo_se_ve_a_si_mismo_en_el_filtro(self):
        self.client.force_login(self.profesor)

        profesores = self.tablero().context['profesores']

        self.assertEqual(list(profesores), [self.profesor])

    def test_el_administrador_ve_a_todos_en_el_filtro(self):
        self.client.force_login(self.administrador)

        profesores = self.tablero().context['profesores']

        self.assertIn(self.profesor, profesores)
        self.assertIn(self.otro_profesor, profesores)

    def test_el_administrador_filtra_por_profesor(self):
        self.client.force_login(self.administrador)

        resumen = self.tablero(profesor=self.otro_profesor.id).context['resumen']

        self.assertEqual(resumen['total'], 1)
        self.assertEqual(float(resumen['promedio']), 10)


class GraficasTest(BaseTableroTest):
    """Los tres conjuntos de datos que alimentan a Chart.js."""

    def setUp(self):
        super().setUp()
        self.uno = self.crear_alumno('a1@prueba.mx', grupo=self.primero)
        self.dos = self.crear_alumno('a2@prueba.mx', grupo=self.segundo)
        self.de_aritmetica = [
            self.crear_pregunta(self.aritmetica) for _ in range(4)
        ]
        self.de_comprension = [
            self.crear_pregunta(self.comprension) for _ in range(4)
        ]
        self.client.force_login(self.profesor)

    def test_promedio_por_grupo(self):
        primera = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas,
            preguntas=self.de_aritmetica,
        )
        segunda = self.crear_evaluacion(
            grupo=self.segundo, materia=self.matematicas,
            preguntas=self.de_aritmetica,
        )
        self.crear_intento(primera, self.uno, 100)
        self.crear_intento(segunda, self.dos, 50)

        datos = self.tablero().context['datos_grupos']

        self.assertEqual(datos['etiquetas'], ['Primero A', 'Segundo B'])
        self.assertEqual(datos['valores'], [100.0, 50.0])

    def test_promedio_por_materia(self):
        de_mate = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas,
            preguntas=self.de_aritmetica,
        )
        de_letras = self.crear_evaluacion(
            grupo=self.primero, materia=self.literatura,
            preguntas=self.de_comprension,
        )
        self.crear_intento(de_mate, self.uno, 40)
        self.crear_intento(de_letras, self.uno, 90)

        datos = self.tablero().context['datos_materias']

        self.assertEqual(datos['etiquetas'], ['Literatura', 'Matemáticas'])
        self.assertEqual(datos['valores'], [90.0, 40.0])

    def test_porcentaje_de_aciertos_por_categoria(self):
        # Esta grafica no mira la calificacion sino cada respuesta, que es lo
        # que permite decir en que tema se atora el grupo.
        evaluacion = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas,
            preguntas=self.de_aritmetica,
        )
        # Cuatro preguntas: el primero acierta tres, el segundo una.
        self.crear_intento(evaluacion, self.uno, 75, aciertos=3)
        self.crear_intento(evaluacion, self.dos, 25, aciertos=1)

        datos = self.tablero().context['datos_categorias']

        self.assertEqual(datos['etiquetas'], ['Aritmética'])
        # Cuatro aciertos de ocho respuestas.
        self.assertEqual(datos['valores'], [50.0])

    def test_los_valores_van_como_numeros_y_no_como_decimal(self):
        # Chart.js no sabe leer el Decimal que entrega la base de datos, y el
        # sintoma es una grafica en blanco sin ningun error a la vista.
        evaluacion = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas,
            preguntas=self.de_aritmetica,
        )
        self.crear_intento(evaluacion, self.uno, 75)

        datos = self.tablero().context['datos_grupos']

        self.assertIsInstance(datos['valores'][0], float)


class FiltrosTest(BaseTableroTest):
    """Los filtros del tablero, que son los mismos que usa el CSV."""

    def setUp(self):
        super().setUp()
        self.preguntas = [self.crear_pregunta(self.aritmetica) for _ in range(2)]
        self.de_letras = [self.crear_pregunta(self.comprension) for _ in range(2)]

        self.chica = self.crear_alumno(
            'chica@prueba.mx', sexo=Persona.Sexo.FEMENINO, edad=16,
            grupo=self.primero,
        )
        self.chico = self.crear_alumno(
            'chico@prueba.mx', sexo=Persona.Sexo.MASCULINO, edad=19,
            grupo=self.segundo,
        )

        self.de_primero = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas,
            preguntas=self.preguntas,
        )
        self.de_segundo = self.crear_evaluacion(
            grupo=self.segundo, materia=self.literatura,
            preguntas=self.de_letras,
        )
        self.crear_intento(self.de_primero, self.chica, 100)
        self.crear_intento(self.de_segundo, self.chico, 50)
        self.client.force_login(self.profesor)

    def test_filtra_por_grupo(self):
        resumen = self.tablero(grupo=self.primero.id).context['resumen']

        self.assertEqual(resumen['total'], 1)
        self.assertEqual(float(resumen['promedio']), 100)

    def test_filtra_por_materia(self):
        resumen = self.tablero(materia=self.literatura.id).context['resumen']

        self.assertEqual(resumen['total'], 1)
        self.assertEqual(float(resumen['promedio']), 50)

    def test_filtra_por_sexo(self):
        resumen = self.tablero(sexo=Persona.Sexo.FEMENINO).context['resumen']

        self.assertEqual(resumen['total'], 1)
        self.assertEqual(float(resumen['promedio']), 100)

    def test_filtra_por_edad_minima(self):
        resumen = self.tablero(edad_min='18').context['resumen']

        self.assertEqual(resumen['total'], 1)
        self.assertEqual(float(resumen['promedio']), 50)

    def test_filtra_por_edad_maxima(self):
        resumen = self.tablero(edad_max='17').context['resumen']

        self.assertEqual(resumen['total'], 1)
        self.assertEqual(float(resumen['promedio']), 100)

    def test_el_rango_de_edad_incluye_sus_extremos(self):
        # Pedir "de 16 a 16" tiene que traer al alumno de 16, no dejarlo fuera
        # por un dia. Es el error clasico de los filtros por fecha.
        resumen = self.tablero(edad_min='16', edad_max='16').context['resumen']

        self.assertEqual(resumen['total'], 1)
        self.assertEqual(float(resumen['promedio']), 100)

    def test_una_edad_que_no_es_numero_se_ignora(self):
        # El filtro llega por la direccion y cualquiera puede escribir ahi.
        resumen = self.tablero(edad_min='dieciseis').context['resumen']

        self.assertEqual(resumen['total'], 2)

    def test_los_filtros_se_acumulan(self):
        resumen = self.tablero(
            grupo=self.primero.id, sexo=Persona.Sexo.MASCULINO
        ).context['resumen']

        self.assertEqual(resumen['total'], 0)

    def test_filtra_por_nombre_o_apellido_del_alumno(self):
        # chica y chico comparten apellido 'Lara' por el valor por omision de
        # crear_alumno; se les da uno propio para poder distinguirlos aqui.
        self.chica.apellido = 'Ramirez'
        self.chica.save(update_fields=['apellido'])

        resumen = self.tablero(alumno='ramirez').context['resumen']

        self.assertEqual(resumen['total'], 1)
        self.assertEqual(float(resumen['promedio']), 100)

    def test_filtra_por_calificacion_minima(self):
        resumen = self.tablero(calificacion_min='60').context['resumen']

        self.assertEqual(resumen['total'], 1)
        self.assertEqual(float(resumen['promedio']), 100)

    def test_filtra_por_calificacion_maxima(self):
        resumen = self.tablero(calificacion_max='60').context['resumen']

        self.assertEqual(resumen['total'], 1)
        self.assertEqual(float(resumen['promedio']), 50)

    def test_el_rango_de_calificacion_incluye_sus_extremos(self):
        resumen = self.tablero(
            calificacion_min='100', calificacion_max='100'
        ).context['resumen']

        self.assertEqual(resumen['total'], 1)
        self.assertEqual(float(resumen['promedio']), 100)

    def test_una_calificacion_que_no_es_numero_se_ignora(self):
        resumen = self.tablero(calificacion_min='muy-bien').context['resumen']

        self.assertEqual(resumen['total'], 2)

    def test_una_calificacion_fuera_de_cero_a_cien_se_ignora(self):
        # 0 a 100 es la escala real de una calificacion; un valor fuera de
        # ahi no puede ser una calificacion valida, se trata como si no se
        # hubiera escrito nada.
        resumen = self.tablero(calificacion_min='-5').context['resumen']
        self.assertEqual(resumen['total'], 2)

        resumen = self.tablero(calificacion_max='150').context['resumen']
        self.assertEqual(resumen['total'], 2)


class ExportarCsvTest(BaseTableroTest):
    """El archivo que el profesor se lleva a la hoja de calculo."""

    def setUp(self):
        super().setUp()
        self.alumno = self.crear_alumno('a1@prueba.mx', grupo=self.primero)
        self.otro = self.crear_alumno('a2@prueba.mx', grupo=self.segundo)
        preguntas = [self.crear_pregunta(self.aritmetica) for _ in range(2)]

        self.de_primero = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas, preguntas=preguntas
        )
        self.de_segundo = self.crear_evaluacion(
            grupo=self.segundo, materia=self.matematicas, preguntas=preguntas
        )
        self.crear_intento(self.de_primero, self.alumno, 90)
        self.crear_intento(self.de_segundo, self.otro, 40)
        self.client.force_login(self.profesor)

    def exportar(self, **filtros):
        return self.client.get(reverse('reportes:exportar_csv'), filtros)

    def renglones(self, respuesta):
        texto = respuesta.content.decode('utf-8-sig')
        return list(csv.reader(texto.splitlines()))

    def test_se_descarga_como_archivo(self):
        respuesta = self.exportar()

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('text/csv', respuesta['Content-Type'])
        self.assertIn('resultados.csv', respuesta['Content-Disposition'])

    def test_lleva_la_marca_que_excel_necesita(self):
        # Sin ella Excel abre el archivo sin acentos y el profesor ve nombres
        # rotos, que es la primera impresion del reporte.
        self.assertTrue(self.exportar().content.startswith(b'\xef\xbb\xbf'))

    def test_los_encabezados_van_con_ortografia_completa(self):
        encabezado = self.renglones(self.exportar())[0]

        self.assertEqual(encabezado, [
            'Alumno', 'Grupo', 'Disciplina', 'Evaluación', 'Calificación', 'Fecha',
        ])

    def test_un_renglon_por_intento_finalizado(self):
        renglones = self.renglones(self.exportar())

        self.assertEqual(len(renglones), 3)
        self.assertEqual(renglones[1][0], 'Lara Beto')
        self.assertEqual(renglones[1][1], 'Primero A')
        self.assertEqual(renglones[1][4], '90.00')

    def test_respeta_los_mismos_filtros_que_el_tablero(self):
        # Si el CSV filtrara distinto que la pantalla, el profesor exportaria
        # una cosa despues de haber visto otra.
        renglones = self.renglones(self.exportar(grupo=self.segundo.id))

        self.assertEqual(len(renglones), 2)
        self.assertEqual(renglones[1][1], 'Segundo B')

    def test_el_alumno_no_puede_exportar(self):
        self.client.force_login(self.alumno)

        self.assertEqual(self.exportar().status_code, 403)


class NivelesYTendenciaTest(BaseTableroTest):
    """Aciertos por nivel de dificultad y la tendencia por evaluacion."""

    def setUp(self):
        super().setUp()
        self.avanzado = Nivel.objects.create(numero=3, nombre='Avanzado')
        self.uno = self.crear_alumno('a1@prueba.mx', grupo=self.primero)
        self.client.force_login(self.profesor)

    def test_porcentaje_de_aciertos_por_nivel(self):
        basica = self.crear_pregunta(
            self.aritmetica, nivel=self.nivel, enunciado='Básica'
        )
        avanzada = self.crear_pregunta(
            self.aritmetica, nivel=self.avanzado, enunciado='Avanzada'
        )
        evaluacion = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas,
            preguntas=[basica, avanzada],
        )
        # Se responde a mano, sin pasar por el "aciertos" posicional de
        # crear_intento: Pregunta.Meta.ordering es "-fecha_creacion", asi que
        # el orden de evaluacion.preguntas.all() no es el de creacion.
        intento = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.uno, calificacion=50,
            estado=IntentoEvaluacion.Estado.FINALIZADO, fecha_fin=timezone.now(),
        )
        self.responder(intento, basica, True)
        self.responder(intento, avanzada, False)

        datos = self.tablero().context['datos_niveles']

        self.assertEqual(datos['etiquetas'], ['Elemental', 'Avanzado'])
        self.assertEqual(datos['valores'], [100.0, 0.0])

    def test_tendencia_va_en_orden_cronologico(self):
        preguntas = [self.crear_pregunta(self.aritmetica) for _ in range(2)]
        primera = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas, preguntas=preguntas,
        )
        primera.fecha_inicio = timezone.now() - timedelta(days=5)
        primera.save(update_fields=['fecha_inicio'])
        segunda = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas, preguntas=preguntas,
        )
        segunda.fecha_inicio = timezone.now() - timedelta(days=1)
        segunda.save(update_fields=['fecha_inicio'])

        # Se crean en orden inverso al cronologico para probar que lo que
        # ordena es la fecha y no el orden de creacion.
        self.crear_intento(segunda, self.uno, 40)
        self.crear_intento(primera, self.uno, 90)

        datos = self.tablero().context['datos_tendencia']

        self.assertEqual(datos['valores'], [90.0, 40.0])


class PreguntasDificilesTest(BaseTableroTest):
    """El ranking de preguntas con mas error del tablero."""

    def setUp(self):
        super().setUp()
        self.uno = self.crear_alumno('a1@prueba.mx', grupo=self.primero)
        self.dos = self.crear_alumno('a2@prueba.mx', grupo=self.primero)
        self.client.force_login(self.profesor)

    def test_ordena_de_mayor_a_menor_error(self):
        facil = self.crear_pregunta(self.aritmetica, enunciado='Fácil')
        dificil = self.crear_pregunta(self.aritmetica, enunciado='Difícil')
        evaluacion = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas,
            preguntas=[facil, dificil],
        )
        # Se responde a mano: los dos alumnos aciertan la facil y fallan la
        # dificil, sin depender del orden posicional de crear_intento.
        for alumno in (self.uno, self.dos):
            intento = IntentoEvaluacion.objects.create(
                evaluacion=evaluacion, alumno=alumno, calificacion=50,
                estado=IntentoEvaluacion.Estado.FINALIZADO, fecha_fin=timezone.now(),
            )
            self.responder(intento, facil, True)
            self.responder(intento, dificil, False)

        ranking = self.tablero().context['preguntas_dificiles']

        self.assertEqual(ranking[0]['enunciado'], 'Difícil')
        self.assertEqual(ranking[0]['porcentaje_error'], 100.0)
        self.assertEqual(ranking[1]['enunciado'], 'Fácil')
        self.assertEqual(ranking[1]['porcentaje_error'], 0.0)

    def test_dos_preguntas_con_el_mismo_enunciado_no_se_mezclan(self):
        # Nada obliga a que el enunciado sea unico; si el agrupado fuera por
        # texto en vez de por id, estas dos preguntas se fusionarian en una
        # sola fila y el porcentaje de error saldria mal.
        una = self.crear_pregunta(self.aritmetica, enunciado='Repetida')
        otra = self.crear_pregunta(self.aritmetica, enunciado='Repetida')
        evaluacion = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas,
            preguntas=[una, otra],
        )
        self.crear_intento(evaluacion, self.uno, 50, aciertos=1)

        ranking = self.tablero().context['preguntas_dificiles']

        self.assertEqual(len(ranking), 2)
        errores = sorted(fila['porcentaje_error'] for fila in ranking)
        self.assertEqual(errores, [0.0, 100.0])


class ParticipacionTest(BaseTableroTest):
    """Cuantos alumnos distintos ya presentaron, contra cuantos hay en alcance."""

    def setUp(self):
        super().setUp()
        self.uno = self.crear_alumno('a1@prueba.mx', grupo=self.primero)
        self.dos = self.crear_alumno('a2@prueba.mx', grupo=self.primero)
        self.tres = self.crear_alumno('a3@prueba.mx', grupo=self.primero)
        self.preguntas = [self.crear_pregunta(self.aritmetica) for _ in range(2)]
        self.client.force_login(self.profesor)

    def test_cuenta_alumnos_distintos_no_intentos(self):
        evaluacion = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas, preguntas=self.preguntas,
        )
        otra = self.crear_evaluacion(
            grupo=self.primero, materia=self.literatura, preguntas=[],
        )
        # El mismo alumno presenta dos evaluaciones: cuenta una sola vez.
        self.crear_intento(evaluacion, self.uno, 80)
        self.crear_intento(otra, self.uno, 60)

        respuesta = self.tablero()

        self.assertEqual(respuesta.context['alumnos_evaluados'], 1)
        self.assertEqual(respuesta.context['total_alumnos'], 3)

    def test_el_total_se_ajusta_al_grupo_filtrado(self):
        self.crear_alumno('a4@prueba.mx', grupo=self.segundo)

        respuesta = self.tablero(grupo=self.primero.id)

        self.assertEqual(respuesta.context['total_alumnos'], 3)


class ListaIntentosTest(BaseTableroTest):
    """El listado de intentos que alimenta la exploracion de resultados."""

    def setUp(self):
        super().setUp()
        self.alumno = self.crear_alumno('a1@prueba.mx', grupo=self.primero)
        preguntas = [self.crear_pregunta(self.aritmetica) for _ in range(2)]
        self.mia = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas, preguntas=preguntas,
        )
        self.ajena = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas,
            profesor=self.otro_profesor, preguntas=preguntas,
        )
        self.propio = self.crear_intento(self.mia, self.alumno, 80)
        self.crear_intento(self.ajena, self.alumno, 20)

    def listado(self, **filtros):
        return self.client.get(reverse('reportes:lista_intentos'), filtros)

    def test_el_profesor_solo_ve_sus_intentos(self):
        self.client.force_login(self.profesor)

        intentos = list(self.listado().context['intentos'])

        self.assertEqual(intentos, [self.propio])

    def test_el_administrador_los_ve_todos(self):
        self.client.force_login(self.administrador)

        intentos = self.listado().context['intentos']

        self.assertEqual(intentos.count(), 2)

    def test_el_alumno_no_entra(self):
        self.client.force_login(self.alumno)

        self.assertEqual(self.listado().status_code, 403)

    def test_se_puede_ordenar_por_calificacion(self):
        self.client.force_login(self.administrador)

        intentos = list(
            self.listado(orden='calificacion', dir='asc').context['intentos']
        )

        self.assertEqual([intento.calificacion for intento in intentos], [20, 80])


class DetalleIntentoTest(BaseTableroTest):
    """El detalle pregunta por pregunta de un intento finalizado."""

    def setUp(self):
        super().setUp()
        self.alumno = self.crear_alumno('a1@prueba.mx', grupo=self.primero)
        self.preguntas = [self.crear_pregunta(self.aritmetica) for _ in range(2)]
        self.evaluacion = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas, preguntas=self.preguntas,
        )
        self.ajena = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas,
            profesor=self.otro_profesor, preguntas=self.preguntas,
        )

    def detalle(self, intento_id, **filtros):
        return self.client.get(
            reverse('reportes:detalle_intento', args=[intento_id]), filtros
        )

    def test_muestra_lo_que_contesto_el_alumno(self):
        intento = self.crear_intento(self.evaluacion, self.alumno, 50, aciertos=1)
        self.client.force_login(self.profesor)

        resultado = self.detalle(intento.id).context['resultado']

        self.assertEqual(resultado['aciertos'], 1)
        self.assertEqual(resultado['total'], 2)
        self.assertTrue(resultado['detalle'][0]['acerto'])
        self.assertFalse(resultado['detalle'][1]['acerto'])

    def test_el_profesor_no_puede_ver_intentos_ajenos(self):
        ajeno = self.crear_intento(self.ajena, self.alumno, 50)
        self.client.force_login(self.profesor)

        self.assertEqual(self.detalle(ajeno.id).status_code, 404)

    def test_un_intento_en_curso_no_esta_disponible(self):
        en_curso = self.crear_intento(
            self.evaluacion, self.alumno, 0, finalizado=False
        )
        self.client.force_login(self.profesor)

        self.assertEqual(self.detalle(en_curso.id).status_code, 404)

    def test_se_puede_ordenar_por_nivel(self):
        avanzado = Nivel.objects.create(numero=3, nombre='Avanzado')
        basica = self.crear_pregunta(
            self.aritmetica, nivel=self.nivel, enunciado='Básica'
        )
        avanzada = self.crear_pregunta(
            self.aritmetica, nivel=avanzado, enunciado='Avanzada'
        )
        evaluacion = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas,
            preguntas=[basica, avanzada],
        )
        intento = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.alumno, calificacion=50,
            estado=IntentoEvaluacion.Estado.FINALIZADO, fecha_fin=timezone.now(),
        )
        self.responder(intento, basica, True)
        self.responder(intento, avanzada, False)
        self.client.force_login(self.profesor)

        detalle = self.detalle(intento.id, orden='nivel', dir='desc').context[
            'resultado'
        ]['detalle']

        self.assertEqual(
            [fila['nivel_numero'] for fila in detalle], [avanzado.numero, self.nivel.numero]
        )

    def test_se_puede_ordenar_por_resultado(self):
        intento = self.crear_intento(self.evaluacion, self.alumno, 50, aciertos=1)
        self.client.force_login(self.profesor)

        detalle = self.detalle(intento.id, orden='resultado', dir='asc').context[
            'resultado'
        ]['detalle']

        # Las incorrectas (False) van antes que las correctas (True).
        self.assertEqual([fila['acerto'] for fila in detalle], [False, True])


class ResumenFiltrosTest(BaseTableroTest):
    """El dialogo 'Ver filtros aplicados' del tablero y de intentos."""

    def setUp(self):
        super().setUp()
        self.preguntas = [self.crear_pregunta(self.aritmetica) for _ in range(2)]
        self.flor_perez = self.crear_alumno(
            'flor.perez@prueba.mx', nombre='Flor', apellido='Pérez', grupo=self.primero,
        )
        self.flor_gomez = self.crear_alumno(
            'flor.gomez@prueba.mx', nombre='Flor', apellido='Gómez', grupo=self.primero,
        )
        self.evaluacion = self.crear_evaluacion(
            grupo=self.primero, materia=self.matematicas, preguntas=self.preguntas,
        )
        self.crear_intento(self.evaluacion, self.flor_perez, 80)
        self.crear_intento(self.evaluacion, self.flor_gomez, 60)
        self.client.force_login(self.profesor)

    def test_sin_filtros_no_hay_nada_que_resumir(self):
        respuesta = self.tablero()

        self.assertEqual(respuesta.context['resumen_filtros'], [])
        self.assertEqual(respuesta.context['alumnos_coincidentes'], [])

    def test_resuelve_ids_a_nombres_legibles(self):
        # Un id de grupo o de disciplina no dice nada por si solo; el
        # dialogo tiene que mostrar el nombre, no el numero de la URL.
        respuesta = self.tablero(grupo=self.primero.id, materia=self.matematicas.id)

        resumen = respuesta.context['resumen_filtros']
        self.assertIn(('Grupo', self.primero.nombre), resumen)
        self.assertIn(('Disciplina', self.matematicas.nombre), resumen)

    def test_lista_los_alumnos_que_coinciden_con_el_texto(self):
        respuesta = self.tablero(alumno='flor')

        nombres = [a.nombre_completo for a in respuesta.context['alumnos_coincidentes']]
        self.assertIn(self.flor_perez.nombre_completo, nombres)
        self.assertIn(self.flor_gomez.nombre_completo, nombres)

    def test_solo_lista_a_quienes_quedan_en_el_conjunto_ya_filtrado(self):
        # Combinado con calificacion_min=70 deja fuera a Gomez (60), aunque
        # su nombre tambien coincida con 'flor': la lista tiene que reflejar
        # lo que de verdad se esta mostrando, no solo el texto suelto.
        respuesta = self.tablero(alumno='flor', calificacion_min='70')

        nombres = [a.nombre_completo for a in respuesta.context['alumnos_coincidentes']]
        self.assertEqual(nombres, [self.flor_perez.nombre_completo])


class ResaltarFiltroTest(TestCase):
    """El filtro de plantilla que subraya la coincidencia en el dialogo."""

    def test_envuelve_la_coincidencia_en_mark(self):
        self.assertEqual(
            resaltar('Flores Valeria', 'Flor'),
            '<mark class="resaltado">Flor</mark>es Valeria',
        )

    def test_no_distingue_mayusculas_de_minusculas(self):
        self.assertIn('<mark class="resaltado">flor</mark>', resaltar('flores valeria', 'FLOR'))

    def test_sin_texto_buscado_regresa_el_texto_igual(self):
        self.assertEqual(resaltar('Flores Valeria', ''), 'Flores Valeria')

    def test_escapa_html_del_texto_original(self):
        # El texto que se resalta puede venir de un nombre capturado por
        # cualquiera; sin escapar, ese nombre podria inyectar HTML.
        resultado = resaltar('<script>Flor</script>', 'Flor')

        self.assertNotIn('<script>', resultado)
        self.assertIn('&lt;script&gt;', resultado)
