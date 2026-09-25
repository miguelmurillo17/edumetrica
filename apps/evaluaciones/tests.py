"""
Pruebas del flujo central del sistema: programar una evaluacion, presentarla
y cerrarla.

Es la parte de la que depende la hipotesis de la tesis, asi que lo que se
comprueba aqui no es que las pantallas respondan sino que los numeros salgan
bien: que la calificacion cuente sobre el total de la evaluacion y no sobre lo
que el alumno alcanzo a contestar, que al armar el examen solo entren preguntas
validadas, y que finalizar antes de tiempo cierre a cada alumno con lo que
llevaba.
"""

from datetime import date, timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalogo.models import (
    Categoria, Institucion, Materia, Nivel, OpcionRespuesta, Pregunta,
)
from apps.usuarios.models import Notificacion, Persona

from .avisos import avisar_evaluacion_programada
from .forms import GrupoForm
from .models import (
    AsignacionDocente, CategoriaEvaluacion, Evaluacion, Grupo,
    IntentoEvaluacion, RespuestaAlumno,
)
from .servicios import actualizar_estados, cerrar_evaluacion, entregar_intento


class BaseEvaluacionesTest(TestCase):
    """Un grupo con su profesor, su alumno y un banco de preguntas."""

    def setUp(self):
        self.institucion = Institucion.objects.create(nombre='Preparatoria 1')
        self.materia = Materia.objects.create(
            nombre='Matemáticas', es_cuantitativa=True
        )
        self.categoria = Categoria.objects.create(
            materia=self.materia, nombre='Aritmética'
        )
        self.nivel = Nivel.objects.create(numero=2, nombre='Elemental')

        self.profesor = Persona.objects.create_user(
            correo='profesor@prueba.mx', nombre='Ana', apellido='Ruiz',
            password='Edumetrica2026', rol=Persona.Rol.PROFESOR,
        )
        self.alumno = Persona.objects.create_user(
            correo='alumno@prueba.mx', nombre='Beto', apellido='Lara',
            password='Edumetrica2026', rol=Persona.Rol.ALUMNO,
        )

        self.grupo = Grupo.objects.create(
            nombre='Primero A', institucion=self.institucion
        )
        self.grupo.alumnos.add(self.alumno)
        # El profesor imparte la asignatura en el grupo.
        AsignacionDocente.objects.create(
            grupo=self.grupo, profesor=self.profesor, categoria=self.categoria
        )

    def crear_pregunta(self, **extras):
        datos = {
            'materia': self.materia,
            'categoria': self.categoria,
            'nivel': self.nivel,
            'enunciado': '¿Cuánto es 2 + 3 por 4?',
            'creada_por': self.profesor,
            'estado': Pregunta.Estado.VALIDADA,
        }
        datos.update(extras)
        pregunta = Pregunta.objects.create(**datos)
        for posicion, texto in enumerate(['14', '20', '9', '24']):
            OpcionRespuesta.objects.create(
                pregunta=pregunta, texto=texto, es_correcta=(posicion == 0)
            )
        return pregunta

    def crear_evaluacion(self, *, preguntas=(), inicio=None, fin=None, **extras):
        ahora = timezone.now()
        datos = {
            'titulo': 'Diagnóstico',
            'profesor': self.profesor,
            'grupo': self.grupo,
            'materia': self.materia,
            'fecha_inicio': inicio or ahora - timedelta(hours=1),
            'fecha_fin': fin or ahora + timedelta(hours=1),
            'numero_preguntas': len(preguntas),
        }
        datos.update(extras)
        evaluacion = Evaluacion.objects.create(**datos)
        evaluacion.preguntas.set(preguntas)
        return evaluacion

    def responder(self, intento, pregunta, acerto):
        opcion = pregunta.opciones.filter(es_correcta=acerto).first()
        return RespuestaAlumno.objects.create(
            intento=intento, pregunta=pregunta,
            opcion_seleccionada=opcion, es_correcta=acerto,
        )


class CalificacionTest(BaseEvaluacionesTest):
    """El calculo de la calificacion, que es el numero del que todo depende."""

    def setUp(self):
        super().setUp()
        self.preguntas = [self.crear_pregunta() for _ in range(4)]
        self.evaluacion = self.crear_evaluacion(preguntas=self.preguntas)
        self.intento = IntentoEvaluacion.objects.create(
            evaluacion=self.evaluacion, alumno=self.alumno
        )

    def test_todas_correctas_son_cien(self):
        for pregunta in self.preguntas:
            self.responder(self.intento, pregunta, True)
        self.assertEqual(self.intento.calcular_calificacion(), 100)

    def test_la_mitad_son_cincuenta(self):
        for pregunta in self.preguntas[:2]:
            self.responder(self.intento, pregunta, True)
        for pregunta in self.preguntas[2:]:
            self.responder(self.intento, pregunta, False)
        self.assertEqual(self.intento.calcular_calificacion(), 50)

    def test_sin_responder_nada_es_cero(self):
        self.assertEqual(self.intento.calcular_calificacion(), 0)

    def test_las_no_contestadas_cuentan_como_falladas(self):
        # Es la regla que mas facil se rompe: si el divisor fueran las
        # respuestas guardadas en lugar del total de la evaluacion, un alumno
        # que contesta una sola pregunta y acierta sacaria cien.
        self.responder(self.intento, self.preguntas[0], True)
        self.assertEqual(self.intento.calcular_calificacion(), 25)

    def test_redondea_a_dos_decimales(self):
        # Un tercio de tres aciertos sobre siete preguntas no da un numero
        # redondo, y la calificacion se guarda con dos decimales.
        evaluacion = self.crear_evaluacion(
            preguntas=[self.crear_pregunta() for _ in range(7)]
        )
        intento = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.alumno
        )
        for pregunta in list(evaluacion.preguntas.all())[:3]:
            self.responder(intento, pregunta, True)

        self.assertEqual(intento.calcular_calificacion(), 42.86)

    def test_una_evaluacion_sin_preguntas_no_revienta(self):
        # Dividir entre cero tumbaria la pantalla del alumno al finalizar.
        evaluacion = self.crear_evaluacion(preguntas=[])
        intento = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.alumno
        )
        self.assertEqual(intento.calcular_calificacion(), 0)


class DisponibilidadTest(BaseEvaluacionesTest):
    """Cuando se puede presentar una evaluacion y cuando no."""

    def test_dentro_del_horario_esta_disponible(self):
        self.assertTrue(self.crear_evaluacion().esta_disponible())

    def test_antes_de_la_hora_de_inicio_no(self):
        ahora = timezone.now()
        evaluacion = self.crear_evaluacion(
            inicio=ahora + timedelta(hours=1), fin=ahora + timedelta(hours=2)
        )
        self.assertFalse(evaluacion.esta_disponible())

    def test_despues_de_la_hora_de_fin_tampoco(self):
        ahora = timezone.now()
        evaluacion = self.crear_evaluacion(
            inicio=ahora - timedelta(hours=2), fin=ahora - timedelta(hours=1)
        )
        self.assertFalse(evaluacion.esta_disponible())

    def test_finalizada_no_esta_disponible_aunque_falte_tiempo(self):
        # El profesor la cerro antes: el horario ya no manda.
        evaluacion = self.crear_evaluacion(
            estado=Evaluacion.Estado.FINALIZADA
        )
        self.assertFalse(evaluacion.esta_disponible())


class ProgramarEvaluacionTest(BaseEvaluacionesTest):
    """La pantalla con la que el profesor arma el examen."""

    def setUp(self):
        super().setUp()
        self.otra_categoria = Categoria.objects.create(
            materia=self.materia, nombre='Álgebra'
        )
        # El profesor tambien imparte la segunda asignatura en el grupo.
        AsignacionDocente.objects.create(
            grupo=self.grupo, profesor=self.profesor, categoria=self.otra_categoria
        )
        # Banco suficiente para pedir hasta cinco de cada categoria.
        for _ in range(5):
            self.crear_pregunta()
            self.crear_pregunta(categoria=self.otra_categoria)
        self.client.force_login(self.profesor)

    def cuando(self, momento):
        """Formatea un momento como lo manda el selector del navegador.

        Hay que pasar por la hora local: timezone.now() viene en UTC, y
        formatearlo tal cual correria las fechas las horas que lleve de
        diferencia la zona del proyecto.
        """
        return timezone.localtime(momento).strftime('%Y-%m-%dT%H:%M')

    def datos(self, renglones, **extras):
        """Arma el envio del formulario con su tabla de categorias."""
        ahora = timezone.now()
        envio = {
            'titulo': 'Diagnóstico',
            'grupo': self.grupo.id,
            'materia': self.materia.id,
            # Arranca al momento: programarla en el pasado la dejaria cerrada
            # de nacimiento, y el formulario ya no lo permite.
            'fecha_inicio': self.cuando(ahora),
            'fecha_fin': self.cuando(ahora + timedelta(hours=1)),
            'categorias_elegidas-TOTAL_FORMS': str(len(renglones)),
            'categorias_elegidas-INITIAL_FORMS': '0',
            'categorias_elegidas-MIN_NUM_FORMS': '0',
            'categorias_elegidas-MAX_NUM_FORMS': '1000',
        }
        for posicion, (categoria, numero) in enumerate(renglones):
            envio[f'categorias_elegidas-{posicion}-categoria'] = categoria.id
            envio[f'categorias_elegidas-{posicion}-numero_preguntas'] = numero
        envio.update(extras)
        return envio

    def programar(self, renglones, **extras):
        return self.client.post(
            reverse('evaluaciones:crear_evaluacion'),
            self.datos(renglones, **extras),
        )

    def test_arma_el_examen_con_lo_que_pide_cada_renglon(self):
        respuesta = self.programar([(self.categoria, 2), (self.otra_categoria, 3)])

        self.assertRedirects(
            respuesta, reverse('evaluaciones:lista_evaluaciones')
        )
        evaluacion = Evaluacion.objects.get()
        self.assertEqual(evaluacion.preguntas.count(), 5)
        self.assertEqual(
            evaluacion.preguntas.filter(categoria=self.categoria).count(), 2
        )
        self.assertEqual(
            evaluacion.preguntas.filter(categoria=self.otra_categoria).count(), 3
        )

    def test_el_total_es_la_suma_de_los_renglones(self):
        # numero_preguntas es el divisor de la calificacion: si se desfasa de
        # las preguntas que de verdad tiene la evaluacion, todas las
        # calificaciones del grupo salen mal.
        self.programar([(self.categoria, 2), (self.otra_categoria, 3)])

        evaluacion = Evaluacion.objects.get()
        self.assertEqual(evaluacion.numero_preguntas, 5)
        self.assertEqual(evaluacion.numero_preguntas, evaluacion.preguntas.count())

    def test_guarda_los_renglones_de_la_tabla(self):
        self.programar([(self.categoria, 2), (self.otra_categoria, 3)])

        renglones = CategoriaEvaluacion.objects.order_by('id')
        self.assertEqual(renglones.count(), 2)
        self.assertEqual(renglones[0].categoria, self.categoria)
        self.assertEqual(renglones[0].numero_preguntas, 2)

    def test_solo_entran_preguntas_validadas(self):
        # Es la compuerta que sostiene la propuesta: una pregunta generada que
        # nadie ha revisado no puede colarse a un examen real.
        Pregunta.objects.update(estado=Pregunta.Estado.BORRADOR)
        buenas = [self.crear_pregunta() for _ in range(2)]

        self.programar([(self.categoria, 2)])

        evaluacion = Evaluacion.objects.get()
        self.assertEqual(
            set(evaluacion.preguntas.values_list('id', flat=True)),
            {pregunta.id for pregunta in buenas},
        )

    def test_una_pregunta_dada_de_baja_no_entra(self):
        # "Inactiva" es dar de baja una pregunta vieja, distinto de "todavia
        # no la revisan", y las dos tienen que dejarla fuera.
        Pregunta.objects.update(activa=False)
        buenas = [self.crear_pregunta() for _ in range(2)]

        self.programar([(self.categoria, 2)])

        evaluacion = Evaluacion.objects.get()
        self.assertEqual(
            set(evaluacion.preguntas.values_list('id', flat=True)),
            {pregunta.id for pregunta in buenas},
        )

    def test_rechaza_si_el_banco_no_alcanza(self):
        # El conteo del formulario y la seleccion de la vista tienen que mirar
        # el mismo banco: si el formulario dijera que hay veinte y la vista
        # armara con ocho, la evaluacion saldria mas corta sin avisar.
        respuesta = self.programar([(self.categoria, 50)])

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'solo tiene 5 preguntas disponibles')
        self.assertFalse(Evaluacion.objects.exists())

    def test_rechaza_la_tabla_vacia(self):
        respuesta = self.programar([])

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'al menos una asignatura')
        self.assertFalse(Evaluacion.objects.exists())

    def test_rechaza_categorias_repetidas(self):
        # La tabla se rechaza, pero conviene saber quien la rechaza: quien
        # avisa es la restriccion de unicidad del modelo, que el formulario de
        # Django comprueba antes de llegar a la validacion propia. El mensaje
        # escrito a mano en BaseCategoriasFormSet no alcanza a mostrarse.
        respuesta = self.programar([(self.categoria, 1), (self.categoria, 2)])

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Evaluacion.objects.exists())
        self.assertTrue(respuesta.context['filas'].non_form_errors())

    def test_rechaza_una_asignatura_de_otra_disciplina(self):
        otra_materia = Materia.objects.create(nombre='Literatura')
        ajena = Categoria.objects.create(
            materia=otra_materia, nombre='Comprensión'
        )
        self.crear_pregunta(materia=otra_materia, categoria=ajena)
        # Se le asigna al profesor para que el formulario acepte la asignatura;
        # asi la validacion que se prueba es la de disciplina, no la de choices.
        AsignacionDocente.objects.create(
            grupo=self.grupo, profesor=self.profesor, categoria=ajena
        )

        respuesta = self.programar([(ajena, 1)])

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'no pertenece a la disciplina elegida')
        self.assertFalse(Evaluacion.objects.exists())

    def test_rechaza_una_asignatura_que_no_imparte_en_el_grupo(self):
        # El profesor no puede evaluar una asignatura de la disciplina elegida
        # si no la imparte en ese grupo.
        no_asignada = Categoria.objects.create(
            materia=self.materia, nombre='Geometría'
        )
        for _ in range(3):
            self.crear_pregunta(categoria=no_asignada)

        respuesta = self.programar([(no_asignada, 1)])

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Evaluacion.objects.exists())

    def test_rechaza_que_termine_antes_de_empezar(self):
        ahora = timezone.now()
        respuesta = self.programar(
            [(self.categoria, 1)],
            fecha_inicio=self.cuando(ahora + timedelta(hours=2)),
            fecha_fin=self.cuando(ahora + timedelta(hours=1)),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'posterior a la de inicio')
        self.assertFalse(Evaluacion.objects.exists())

    def test_rechaza_programarla_en_el_pasado(self):
        # Una evaluacion con la ventana ya vencida nace cerrada: ningun alumno
        # del grupo podria presentarla.
        ahora = timezone.now()
        respuesta = self.programar(
            [(self.categoria, 1)],
            fecha_inicio=self.cuando(ahora - timedelta(hours=2)),
            fecha_fin=self.cuando(ahora - timedelta(hours=1)),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'no puede estar en el pasado')
        self.assertFalse(Evaluacion.objects.exists())

    def test_rechaza_una_ventana_demasiado_corta(self):
        # Con dos minutos de plazo, el aviso de que quedan tres minutos saldria
        # antes de que el alumno abriera la primera pregunta.
        ahora = timezone.now()
        respuesta = self.programar(
            [(self.categoria, 1)],
            fecha_inicio=self.cuando(ahora + timedelta(hours=1)),
            fecha_fin=self.cuando(ahora + timedelta(hours=1, minutes=2)),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'al menos 5 minutos')
        self.assertFalse(Evaluacion.objects.exists())

    def test_el_profesor_solo_ve_sus_grupos(self):
        ajeno = Grupo.objects.create(
            nombre='Segundo B', institucion=self.institucion
        )

        respuesta = self.client.get(reverse('evaluaciones:crear_evaluacion'))

        grupos = respuesta.context['formulario'].fields['grupo'].queryset
        self.assertIn(self.grupo, grupos)
        self.assertNotIn(ajeno, grupos)

    def test_el_administrador_no_programa(self):
        # Programar es del profesor: el administrador da de alta el catalogo
        # pero no imparte clase.
        administrador = Persona.objects.create_user(
            correo='admin@prueba.mx', nombre='Caro', apellido='Solis',
            password='Edumetrica2026', rol=Persona.Rol.ADMINISTRADOR,
        )
        self.client.force_login(administrador)

        respuesta = self.client.get(reverse('evaluaciones:crear_evaluacion'))

        self.assertEqual(respuesta.status_code, 403)


class FinalizarEvaluacionTest(BaseEvaluacionesTest):
    """El profesor cierra la evaluacion antes de tiempo."""

    def setUp(self):
        super().setUp()
        self.otro_alumno = Persona.objects.create_user(
            correo='otro@prueba.mx', nombre='Dani', apellido='Mora',
            password='Edumetrica2026', rol=Persona.Rol.ALUMNO,
        )
        self.grupo.alumnos.add(self.otro_alumno)
        self.preguntas = [self.crear_pregunta() for _ in range(4)]
        self.evaluacion = self.crear_evaluacion(preguntas=self.preguntas)
        self.client.force_login(self.profesor)

    def finalizar(self):
        return self.client.post(reverse(
            'evaluaciones:finalizar_evaluacion', args=[self.evaluacion.id]
        ))

    def test_cierra_los_intentos_en_curso_con_su_parcial(self):
        # El alumno que iba a la mitad se queda con lo que llevaba, no con cero.
        intento = IntentoEvaluacion.objects.create(
            evaluacion=self.evaluacion, alumno=self.alumno
        )
        self.responder(intento, self.preguntas[0], True)
        self.responder(intento, self.preguntas[1], True)

        self.finalizar()

        intento.refresh_from_db()
        self.assertEqual(intento.estado, IntentoEvaluacion.Estado.FINALIZADO)
        self.assertEqual(float(intento.calificacion), 50)
        self.assertIsNotNone(intento.fecha_fin)

    def test_marca_la_evaluacion_como_finalizada(self):
        self.finalizar()

        self.evaluacion.refresh_from_db()
        self.assertEqual(self.evaluacion.estado, Evaluacion.Estado.FINALIZADA)

    def test_antes_de_la_hora_de_fin_queda_como_anticipada(self):
        # Es el dato que distingue "se acabo el tiempo" de "el profesor
        # decidio cerrarla", y se reporta en el capitulo de resultados.
        self.finalizar()

        self.evaluacion.refresh_from_db()
        self.assertTrue(self.evaluacion.finalizada_anticipadamente)

    def test_despues_de_la_hora_de_fin_no_es_anticipada(self):
        ahora = timezone.now()
        self.evaluacion.fecha_inicio = ahora - timedelta(hours=3)
        self.evaluacion.fecha_fin = ahora - timedelta(hours=1)
        self.evaluacion.save()

        self.finalizar()

        self.evaluacion.refresh_from_db()
        self.assertFalse(self.evaluacion.finalizada_anticipadamente)

    def test_no_toca_los_intentos_que_ya_estaban_cerrados(self):
        cerrado = IntentoEvaluacion.objects.create(
            evaluacion=self.evaluacion, alumno=self.alumno,
            estado=IntentoEvaluacion.Estado.FINALIZADO, calificacion=75,
        )

        self.finalizar()

        cerrado.refresh_from_db()
        self.assertEqual(float(cerrado.calificacion), 75)

    def test_el_alumno_que_no_empezo_no_gana_un_intento(self):
        self.finalizar()
        self.assertFalse(
            IntentoEvaluacion.objects.filter(alumno=self.otro_alumno).exists()
        )

    def test_otro_profesor_no_puede_finalizarla(self):
        ajeno = Persona.objects.create_user(
            correo='ajeno@prueba.mx', nombre='Eva', apellido='Pinto',
            password='Edumetrica2026', rol=Persona.Rol.PROFESOR,
        )
        self.client.force_login(ajeno)

        respuesta = self.finalizar()

        self.assertEqual(respuesta.status_code, 404)
        self.evaluacion.refresh_from_db()
        self.assertNotEqual(self.evaluacion.estado, Evaluacion.Estado.FINALIZADA)

    def test_una_visita_sin_confirmar_no_la_finaliza(self):
        # Se confirma con un envio; entrar a la direccion no debe cerrarla.
        self.client.get(reverse(
            'evaluaciones:finalizar_evaluacion', args=[self.evaluacion.id]
        ))

        self.evaluacion.refresh_from_db()
        self.assertNotEqual(self.evaluacion.estado, Evaluacion.Estado.FINALIZADA)


class MisGruposTest(BaseEvaluacionesTest):
    """La pantalla de grupos muestra que asignatura imparte cada profesor."""

    def test_lista_al_profesor_con_su_asignatura(self):
        self.client.force_login(self.profesor)

        respuesta = self.client.get(reverse('evaluaciones:lista_grupos'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Ruiz Ana')
        # La asignatura asignada en el grupo aparece junto al profesor.
        self.assertContains(respuesta, 'Aritmética')

    def test_una_segunda_asignatura_tambien_aparece(self):
        otra = Categoria.objects.create(materia=self.materia, nombre='Álgebra')
        AsignacionDocente.objects.create(
            grupo=self.grupo, profesor=self.profesor, categoria=otra
        )
        self.client.force_login(self.profesor)

        respuesta = self.client.get(reverse('evaluaciones:lista_grupos'))

        self.assertContains(respuesta, 'Aritmética')
        self.assertContains(respuesta, 'Álgebra')


class GrupoFormTest(BaseEvaluacionesTest):
    """Un alumno solo puede pertenecer a un grupo a la vez."""

    def test_un_alumno_en_otro_grupo_no_aparece_disponible(self):
        # self.alumno ya esta en self.grupo desde el setUp.
        otro_grupo = Grupo.objects.create(nombre='Segundo B')

        formulario = GrupoForm(instance=otro_grupo)

        self.assertNotIn(self.alumno, formulario.fields['alumnos'].queryset)

    def test_un_alumno_sin_grupo_si_aparece_disponible(self):
        libre = Persona.objects.create_user(
            correo='libre@prueba.mx', nombre='Cruz', apellido='Nava',
            password='Edumetrica2026', rol=Persona.Rol.ALUMNO,
        )

        formulario = GrupoForm()

        self.assertIn(libre, formulario.fields['alumnos'].queryset)

    def test_al_editar_su_propio_grupo_el_alumno_si_aparece_disponible(self):
        formulario = GrupoForm(instance=self.grupo)

        self.assertIn(self.alumno, formulario.fields['alumnos'].queryset)

    def test_un_renglon_sin_elegir_no_truena_ni_invalida_el_formulario(self):
        # La tabla siempre puede traer un renglon extra en "---------": no
        # cuenta como un alumno invalido, simplemente no aporta nada.
        formulario = GrupoForm(
            instance=self.grupo,
            data={
                'nombre': self.grupo.nombre,
                'institucion': '',
                'alumnos': ['', str(self.alumno.pk)],
                'activo': 'on',
            },
        )

        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertQuerySetEqual(
            formulario.alumnos_actuales, [self.alumno], transform=lambda p: p
        )

    def test_no_deja_elegir_al_mismo_alumno_dos_veces(self):
        formulario = GrupoForm(
            instance=self.grupo,
            data={
                'nombre': self.grupo.nombre,
                'institucion': '',
                'alumnos': [str(self.alumno.pk), str(self.alumno.pk)],
                'activo': 'on',
            },
        )

        self.assertFalse(formulario.is_valid())
        errores = formulario.non_field_errors()
        self.assertIn('No puedes agregar al mismo alumno más de una vez.', errores)
        # El alumno repetido ya es de este grupo: no debe salir tambien el
        # error de "ya pertenece a otro grupo" (regresion de combinar
        # Q(grupos__isnull=False) con ~Q(grupos=pk) en un solo filter()).
        self.assertFalse(any('Ya pertenecen a otro grupo' in e for e in errores))

    def test_no_deja_guardar_a_un_alumno_que_se_asigno_a_otro_grupo_mientras_tanto(self):
        # El queryset del campo es perezoso: aunque se arma al abrir el
        # formulario, se vuelve a consultar hasta que algo lo evalua. Si
        # alguien mas asigna al alumno a otro grupo antes de que este se
        # guarde, no debe dejarlo pasar.
        libre = Persona.objects.create_user(
            correo='libre3@prueba.mx', nombre='Elia', apellido='Nunez',
            password='Edumetrica2026', rol=Persona.Rol.ALUMNO,
        )
        formulario = GrupoForm(
            instance=self.grupo,
            data={
                'nombre': self.grupo.nombre,
                'institucion': '',
                'alumnos': [str(libre.pk)],
                'activo': 'on',
            },
        )
        otro_grupo = Grupo.objects.create(nombre='Cuarto D')
        otro_grupo.alumnos.add(libre)

        self.assertFalse(formulario.is_valid())
        self.assertNotIn(libre, self.grupo.alumnos.all())


class CrearGrupoTest(BaseEvaluacionesTest):
    """El administrador da de alta grupos desde /grupos/nuevo/."""

    def setUp(self):
        super().setUp()
        self.administrador = Persona.objects.create_user(
            correo='admin@prueba.mx', nombre='Cara', apellido='Diaz',
            password='Edumetrica2026', rol=Persona.Rol.ADMINISTRADOR,
        )
        self.client.force_login(self.administrador)

    def datos_formset_vacio(self):
        return {
            'asignaciones-TOTAL_FORMS': '1',
            'asignaciones-INITIAL_FORMS': '0',
            'asignaciones-MIN_NUM_FORMS': '0',
            'asignaciones-MAX_NUM_FORMS': '1000',
            'asignaciones-0-profesor': '',
            'asignaciones-0-categoria': '',
        }

    def test_no_deja_asignar_a_un_alumno_que_ya_esta_en_otro_grupo(self):
        # self.alumno ya esta en self.grupo desde el setUp.
        datos = {
            'nombre': 'Tercero C',
            'institucion': '',
            'alumnos': [self.alumno.pk],
            'activo': 'on',
        }
        datos.update(self.datos_formset_vacio())

        respuesta = self.client.post(reverse('evaluaciones:crear_grupo'), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Grupo.objects.filter(nombre='Tercero C').exists())

    def test_un_renglon_vacio_no_truena_al_reintentar_con_otro_error(self):
        # Reproduce el bug: un renglon en "---------" junto con un error en
        # otro campo (aqui, el alumno que ya esta en otro grupo) no debe
        # tronar al repintar la tabla de alumnos.
        datos = {
            'nombre': 'Tercero C',
            'institucion': '',
            'alumnos': ['', str(self.alumno.pk)],
            'activo': 'on',
        }
        datos.update(self.datos_formset_vacio())

        respuesta = self.client.post(reverse('evaluaciones:crear_grupo'), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Grupo.objects.filter(nombre='Tercero C').exists())

    def test_deja_asignar_a_un_alumno_libre(self):
        libre = Persona.objects.create_user(
            correo='libre2@prueba.mx', nombre='Dana', apellido='Soto',
            password='Edumetrica2026', rol=Persona.Rol.ALUMNO,
        )
        datos = {
            'nombre': 'Tercero C',
            'institucion': '',
            'alumnos': [libre.pk],
            'activo': 'on',
        }
        datos.update(self.datos_formset_vacio())

        respuesta = self.client.post(reverse('evaluaciones:crear_grupo'), datos)

        self.assertEqual(respuesta.status_code, 302)
        nuevo = Grupo.objects.get(nombre='Tercero C')
        self.assertIn(libre, nuevo.alumnos.all())


class VencimientoTest(BaseEvaluacionesTest):
    """Que ocurre cuando se acaba el plazo y nadie cerro la evaluacion.

    Es el hueco que mas caro sale: sin este cierre una evaluacion vencida sigue
    diciendo "Programada" y el intento de quien cerro el navegador se queda en
    curso para siempre. Como el tablero solo cuenta intentos finalizados, ese
    alumno desaparece del promedio de su grupo.
    """

    def setUp(self):
        super().setUp()
        self.preguntas = [self.crear_pregunta() for _ in range(4)]

    def evaluacion_vencida(self):
        ahora = timezone.now()
        return self.crear_evaluacion(
            preguntas=self.preguntas,
            inicio=ahora - timedelta(hours=2),
            fin=ahora - timedelta(minutes=1),
        )

    def test_la_vencida_queda_finalizada(self):
        evaluacion = self.evaluacion_vencida()

        actualizar_estados()

        evaluacion.refresh_from_db()
        self.assertEqual(evaluacion.estado, Evaluacion.Estado.FINALIZADA)

    def test_el_vencimiento_no_es_una_finalizacion_anticipada(self):
        # La bandera distingue la decision del profesor de que se acabara el
        # plazo, y el capitulo de resultados se apoya en esa diferencia.
        evaluacion = self.evaluacion_vencida()

        actualizar_estados()

        evaluacion.refresh_from_db()
        self.assertFalse(evaluacion.finalizada_anticipadamente)

    def test_cierra_el_intento_abandonado_con_su_parcial(self):
        evaluacion = self.evaluacion_vencida()
        intento = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.alumno
        )
        self.responder(intento, self.preguntas[0], True)

        actualizar_estados()

        intento.refresh_from_db()
        self.assertEqual(intento.estado, IntentoEvaluacion.Estado.FINALIZADO)
        self.assertEqual(float(intento.calificacion), 25)
        self.assertIsNotNone(intento.fecha_fin)

    def test_el_alumno_que_no_empezo_no_gana_un_intento(self):
        # Vale lo mismo que al finalizar anticipadamente: no se inventan
        # intentos, quien no entro sigue como no iniciado.
        self.evaluacion_vencida()

        actualizar_estados()

        self.assertFalse(IntentoEvaluacion.objects.exists())

    def test_la_ventana_abierta_la_marca_en_curso(self):
        # El estado en curso estaba declarado en el modelo y no se usaba nunca.
        evaluacion = self.crear_evaluacion(preguntas=self.preguntas)

        actualizar_estados()

        evaluacion.refresh_from_db()
        self.assertEqual(evaluacion.estado, Evaluacion.Estado.EN_CURSO)

    def test_la_que_no_ha_empezado_sigue_programada(self):
        ahora = timezone.now()
        evaluacion = self.crear_evaluacion(
            preguntas=self.preguntas,
            inicio=ahora + timedelta(hours=1),
            fin=ahora + timedelta(hours=2),
        )

        actualizar_estados()

        evaluacion.refresh_from_db()
        self.assertEqual(evaluacion.estado, Evaluacion.Estado.PROGRAMADA)

    def test_no_toca_lo_que_el_profesor_ya_habia_cerrado(self):
        evaluacion = self.crear_evaluacion(
            preguntas=self.preguntas,
            estado=Evaluacion.Estado.FINALIZADA,
            finalizada_anticipadamente=True,
        )
        cerrado = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.alumno,
            estado=IntentoEvaluacion.Estado.FINALIZADO, calificacion=75,
        )

        actualizar_estados()

        evaluacion.refresh_from_db()
        cerrado.refresh_from_db()
        self.assertTrue(evaluacion.finalizada_anticipadamente)
        self.assertEqual(float(cerrado.calificacion), 75)

    def test_el_panel_del_alumno_la_muestra_cerrada(self):
        # El cierre es perezoso: entrar al panel es lo que lo dispara.
        self.evaluacion_vencida()
        self.client.force_login(self.alumno)

        respuesta = self.client.get(reverse('evaluaciones:panel_alumno'))

        situaciones = [
            fila['situacion'] for fila in respuesta.context['evaluaciones']
        ]
        self.assertEqual(situaciones, ['cerrada'])

    def test_el_comando_cierra_las_vencidas(self):
        # El comando existe para cron: cierra aunque nadie tenga el navegador
        # abierto, que es lo que necesita un aviso de "ya puedes ver resultados".
        evaluacion = self.evaluacion_vencida()

        call_command('cerrar_evaluaciones', stdout=StringIO())

        evaluacion.refresh_from_db()
        self.assertEqual(evaluacion.estado, Evaluacion.Estado.FINALIZADA)


class ResponderFueraDePlazoTest(BaseEvaluacionesTest):
    """El plazo lo vigila el servidor, no el navegador del alumno."""

    def setUp(self):
        super().setUp()
        self.preguntas = [self.crear_pregunta() for _ in range(2)]
        self.evaluacion = self.crear_evaluacion(preguntas=self.preguntas)
        self.intento = IntentoEvaluacion.objects.create(
            evaluacion=self.evaluacion, alumno=self.alumno
        )
        self.client.force_login(self.alumno)

    def vencer_el_plazo(self):
        """Mueve la ventana al pasado sin pasar por el formulario."""
        ahora = timezone.now()
        Evaluacion.objects.filter(id=self.evaluacion.id).update(
            fecha_inicio=ahora - timedelta(hours=2),
            fecha_fin=ahora - timedelta(minutes=1),
        )

    def responder_por_la_api(self, pregunta):
        opcion = pregunta.opciones.filter(es_correcta=True).first()
        return self.client.post(
            reverse('evaluaciones:api_responder', args=[self.intento.id]),
            {'pregunta': pregunta.id, 'opcion': opcion.id},
            content_type='application/json',
        )

    def consultar_estado(self):
        return self.client.get(
            reverse('evaluaciones:api_estado', args=[self.intento.id])
        )

    def test_dentro_del_plazo_la_respuesta_se_guarda(self):
        respuesta = self.responder_por_la_api(self.preguntas[0])

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(RespuestaAlumno.objects.filter(intento=self.intento).exists())

    def test_despues_del_plazo_la_respuesta_no_se_guarda(self):
        # Con la pestana abierta, un alumno podria seguir contestando horas
        # despues de que la evaluacion cerro y mejorar su calificacion.
        self.vencer_el_plazo()

        respuesta = self.responder_por_la_api(self.preguntas[0])

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()['finalizada'])
        self.assertFalse(RespuestaAlumno.objects.filter(intento=self.intento).exists())

    def test_despues_del_plazo_el_intento_queda_cerrado(self):
        self.vencer_el_plazo()

        self.responder_por_la_api(self.preguntas[0])

        self.intento.refresh_from_db()
        self.assertEqual(self.intento.estado, IntentoEvaluacion.Estado.FINALIZADO)

    def test_el_sondeo_avisa_que_se_acabo_el_tiempo(self):
        # El motivo cambia el mensaje que lee el alumno en su resultado.
        self.vencer_el_plazo()

        respuesta = self.consultar_estado()

        self.assertTrue(respuesta.json()['finalizada'])
        self.assertEqual(respuesta.json()['motivo'], 'tiempo')

    def test_el_sondeo_avisa_que_la_cerro_el_profesor(self):
        cerrar_evaluacion(self.evaluacion, anticipada=True)

        respuesta = self.consultar_estado()

        self.assertTrue(respuesta.json()['finalizada'])
        self.assertEqual(respuesta.json()['motivo'], 'profesor')

    def test_el_sondeo_dice_cuanto_plazo_queda(self):
        # Con esto la pantalla del alumno vuelve a poner su cuenta regresiva
        # en hora: corre sola entre sondeo y sondeo, pero manda el servidor.
        segundos = self.consultar_estado().json()['segundos_restantes']

        self.assertGreater(segundos, 3500)
        self.assertLessEqual(segundos, 3600)

    def test_el_sondeo_no_da_plazo_de_una_cerrada(self):
        cerrar_evaluacion(self.evaluacion, anticipada=True)

        self.assertEqual(
            self.consultar_estado().json()['segundos_restantes'], 0
        )

    def test_el_sondeo_no_cierra_nada_dentro_del_plazo(self):
        respuesta = self.consultar_estado()

        self.assertFalse(respuesta.json()['finalizada'])
        self.intento.refresh_from_db()
        self.assertEqual(self.intento.estado, IntentoEvaluacion.Estado.EN_CURSO)


class PresentarEvaluacionTest(BaseEvaluacionesTest):
    """Quien puede abrir la pantalla con la que se presenta la evaluacion.

    La revision vive en la vista y no solo en la API: sin ella, cualquiera con
    la direccion veia la pantalla completa y se topaba con el error hasta la
    primera peticion.
    """

    def setUp(self):
        super().setUp()
        self.preguntas = [self.crear_pregunta() for _ in range(2)]
        self.evaluacion = self.crear_evaluacion(preguntas=self.preguntas)

    def presentar(self):
        return self.client.get(reverse(
            'evaluaciones:presentar_evaluacion', args=[self.evaluacion.id]
        ))

    def mover_ventana(self, inicio, fin):
        Evaluacion.objects.filter(id=self.evaluacion.id).update(
            fecha_inicio=inicio, fecha_fin=fin
        )

    def test_el_alumno_del_grupo_entra(self):
        self.client.force_login(self.alumno)

        self.assertEqual(self.presentar().status_code, 200)

    def test_un_alumno_de_otro_grupo_no_entra(self):
        ajeno = Persona.objects.create_user(
            correo='ajeno@prueba.mx', nombre='Ivan', apellido='Cruz',
            password='Edumetrica2026', rol=Persona.Rol.ALUMNO,
        )
        self.client.force_login(ajeno)

        respuesta = self.presentar()

        self.assertRedirects(
            respuesta, reverse('usuarios:inicio'), target_status_code=302
        )

    def test_no_se_entra_a_una_evaluacion_vencida(self):
        ahora = timezone.now()
        self.mover_ventana(ahora - timedelta(hours=2), ahora - timedelta(minutes=1))
        self.client.force_login(self.alumno)

        respuesta = self.presentar()

        self.assertRedirects(respuesta, reverse('evaluaciones:panel_alumno'))

    def test_no_se_entra_antes_de_que_empiece(self):
        ahora = timezone.now()
        self.mover_ventana(ahora + timedelta(hours=1), ahora + timedelta(hours=2))
        self.client.force_login(self.alumno)

        respuesta = self.presentar()

        self.assertRedirects(respuesta, reverse('evaluaciones:panel_alumno'))

    def test_quien_ya_la_presento_puede_volver_a_su_resultado(self):
        # Es donde lee la retroalimentacion y el procedimiento de las falladas,
        # asi que la puerta no se le cierra cuando la evaluacion ya termino.
        IntentoEvaluacion.objects.create(
            evaluacion=self.evaluacion, alumno=self.alumno,
            estado=IntentoEvaluacion.Estado.FINALIZADO, calificacion=80,
        )
        ahora = timezone.now()
        self.mover_ventana(ahora - timedelta(hours=2), ahora - timedelta(minutes=1))
        self.client.force_login(self.alumno)

        self.assertEqual(self.presentar().status_code, 200)


@override_settings(CORREO_EN_HILO=False)
class AvisosTest(BaseEvaluacionesTest):
    """Los cuatro momentos en los que el sistema interrumpe a alguien.

    El correo se manda en un hilo, asi que aqui se apaga esa opcion: lo que se
    comprueba es que el mensaje se arme y salga, no cuando termina el hilo.
    """

    def setUp(self):
        super().setUp()
        self.otro_alumno = Persona.objects.create_user(
            correo='otro@prueba.mx', nombre='Dani', apellido='Mora',
            password='Edumetrica2026', rol=Persona.Rol.ALUMNO,
        )
        self.grupo.alumnos.add(self.otro_alumno)
        self.preguntas = [self.crear_pregunta() for _ in range(4)]

    def avisos_de(self, persona):
        return Notificacion.objects.filter(persona=persona)

    def evaluacion_vencida(self):
        ahora = timezone.now()
        return self.crear_evaluacion(
            preguntas=self.preguntas,
            inicio=ahora - timedelta(hours=2),
            fin=ahora - timedelta(minutes=1),
        )

    def test_programar_avisa_a_los_alumnos_del_grupo(self):
        evaluacion = self.crear_evaluacion(preguntas=self.preguntas)

        avisar_evaluacion_programada(evaluacion)

        for alumno in (self.alumno, self.otro_alumno):
            aviso = self.avisos_de(alumno).get()
            self.assertEqual(aviso.titulo, 'Nueva evaluación programada')
            self.assertEqual(aviso.url, reverse('evaluaciones:panel_alumno'))

    def test_al_profesor_no_le_llega_el_aviso_de_su_propia_evaluacion(self):
        evaluacion = self.crear_evaluacion(preguntas=self.preguntas)

        avisar_evaluacion_programada(evaluacion)

        self.assertFalse(self.avisos_de(self.profesor).exists())

    def test_programar_manda_un_correo_por_alumno(self):
        evaluacion = self.crear_evaluacion(preguntas=self.preguntas)

        avisar_evaluacion_programada(evaluacion)

        self.assertEqual(len(mail.outbox), 2)
        destinatarios = sorted(sum((m.to for m in mail.outbox), []))
        self.assertEqual(
            destinatarios, ['alumno@prueba.mx', 'otro@prueba.mx']
        )

    def test_el_correo_no_revela_las_direcciones_de_los_companeros(self):
        # Un solo mensaje con todo el grupo en copia repartiria los correos de
        # los alumnos entre sus companeros.
        evaluacion = self.crear_evaluacion(preguntas=self.preguntas)

        avisar_evaluacion_programada(evaluacion)

        for mensaje in mail.outbox:
            self.assertEqual(len(mensaje.to), 1)
            self.assertFalse(mensaje.cc)
            self.assertFalse(mensaje.bcc)

    @override_settings(SITIO_URL='https://edumetrica.mx')
    def test_el_correo_lleva_un_enlace_con_el_dominio_configurado(self):
        # Una ruta relativa no sirve fuera del navegador, y en produccion el
        # enlace no puede apuntar a la direccion de desarrollo.
        evaluacion = self.crear_evaluacion(preguntas=self.preguntas)

        avisar_evaluacion_programada(evaluacion)

        self.assertIn('https://edumetrica.mx/alumno/', mail.outbox[0].body)

    def test_el_asunto_va_en_una_sola_linea(self):
        # Un salto de linea colado en la plantilla partiria la cabecera.
        evaluacion = self.crear_evaluacion(preguntas=self.preguntas)

        avisar_evaluacion_programada(evaluacion)

        self.assertNotIn('\n', mail.outbox[0].subject)

    def test_programar_desde_la_pantalla_avisa_y_manda_correo(self):
        # El camino completo: lo que de verdad hace el profesor.
        self.client.force_login(self.profesor)
        ahora = timezone.now()
        envio = {
            'titulo': 'Diagnóstico',
            'grupo': self.grupo.id,
            'materia': self.materia.id,
            'fecha_inicio': timezone.localtime(ahora).strftime('%Y-%m-%dT%H:%M'),
            'fecha_fin': timezone.localtime(
                ahora + timedelta(hours=1)
            ).strftime('%Y-%m-%dT%H:%M'),
            'categorias_elegidas-TOTAL_FORMS': '1',
            'categorias_elegidas-INITIAL_FORMS': '0',
            'categorias_elegidas-MIN_NUM_FORMS': '0',
            'categorias_elegidas-MAX_NUM_FORMS': '1000',
            'categorias_elegidas-0-categoria': self.categoria.id,
            'categorias_elegidas-0-numero_preguntas': '2',
        }

        respuesta = self.client.post(
            reverse('evaluaciones:crear_evaluacion'), envio
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Notificacion.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 2)

    def test_el_vencimiento_avisa_al_profesor(self):
        evaluacion = self.evaluacion_vencida()

        actualizar_estados()

        aviso = self.avisos_de(self.profesor).get()
        self.assertEqual(aviso.titulo, 'Una evaluación llegó a su fin')
        self.assertEqual(
            aviso.url,
            reverse('evaluaciones:detalle_evaluacion', args=[evaluacion.id]),
        )

    def test_finalizar_anticipadamente_no_avisa_al_profesor(self):
        # La cerro el: avisarle de su propia decision seria ruido.
        evaluacion = self.crear_evaluacion(preguntas=self.preguntas)

        cerrar_evaluacion(evaluacion, anticipada=True)

        self.assertFalse(self.avisos_de(self.profesor).exists())

    def test_al_alumno_que_se_quedo_a_medias_se_le_avisa(self):
        evaluacion = self.evaluacion_vencida()
        intento = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.alumno
        )
        self.responder(intento, self.preguntas[0], True)

        actualizar_estados()

        aviso = self.avisos_de(self.alumno).get()
        self.assertEqual(aviso.titulo, 'Ya puedes ver tu resultado')

    def test_al_que_ya_habia_entregado_no_se_le_avisa(self):
        # Ese vio su resultado en pantalla al terminar.
        evaluacion = self.evaluacion_vencida()
        IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.alumno,
            estado=IntentoEvaluacion.Estado.FINALIZADO, calificacion=50,
        )

        actualizar_estados()

        self.assertFalse(self.avisos_de(self.alumno).exists())

    def test_al_que_nunca_entro_no_se_le_avisa(self):
        self.evaluacion_vencida()

        actualizar_estados()

        self.assertFalse(self.avisos_de(self.otro_alumno).exists())

    def test_cuando_el_ultimo_alumno_entrega_se_avisa_al_profesor(self):
        evaluacion = self.crear_evaluacion(preguntas=self.preguntas)
        primero = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.alumno
        )
        segundo = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.otro_alumno
        )

        entregar_intento(primero)
        self.assertFalse(self.avisos_de(self.profesor).exists())

        entregar_intento(segundo)

        aviso = self.avisos_de(self.profesor).get()
        self.assertEqual(aviso.titulo, 'Tu grupo terminó la evaluación')

    def test_no_se_avisa_del_grupo_si_falta_alguien_por_entrar(self):
        evaluacion = self.crear_evaluacion(preguntas=self.preguntas)
        intento = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.alumno
        )

        entregar_intento(intento)

        self.assertFalse(self.avisos_de(self.profesor).exists())

    def test_entregar_el_ultimo_de_una_cerrada_no_avisa(self):
        # Si la evaluacion ya esta finalizada, el profesor no puede hacer nada
        # con la noticia: el aviso de cierre ya se le mando.
        evaluacion = self.crear_evaluacion(
            preguntas=self.preguntas, estado=Evaluacion.Estado.FINALIZADA
        )
        intento = IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.alumno
        )
        IntentoEvaluacion.objects.create(
            evaluacion=evaluacion, alumno=self.otro_alumno,
            estado=IntentoEvaluacion.Estado.FINALIZADO, calificacion=50,
        )

        entregar_intento(intento)

        self.assertFalse(self.avisos_de(self.profesor).exists())


class ReanudarEvaluacionTest(BaseEvaluacionesTest):
    """Lo que entrega el servidor cuando el alumno abre la evaluacion.

    Son las dos cosas que necesita su pantalla para no hacerle perder el hilo:
    en que pregunta retomar si vuelve tras un corte, y cuanto plazo le queda.
    """

    def setUp(self):
        super().setUp()
        self.preguntas = [self.crear_pregunta() for _ in range(4)]
        self.evaluacion = self.crear_evaluacion(preguntas=self.preguntas)
        self.client.force_login(self.alumno)

    def iniciar(self):
        respuesta = self.client.post(
            reverse('evaluaciones:api_iniciar', args=[self.evaluacion.id])
        )
        return respuesta.json()

    def responder_las_primeras(self, cuantas):
        """Contesta las primeras preguntas en el orden en que las entrega."""
        datos = self.iniciar()
        intento = IntentoEvaluacion.objects.get(id=datos['intento_id'])
        for ficha in datos['preguntas'][:cuantas]:
            self.responder(
                intento, Pregunta.objects.get(id=ficha['id']), True
            )
        return intento

    def test_sin_respuestas_previas_abre_en_la_primera(self):
        self.assertEqual(self.iniciar()['indice_inicial'], 0)

    def test_reanuda_en_la_primera_sin_responder(self):
        # El alumno que vuelve tras un corte no tiene que pasar otra vez por
        # todas las que ya contesto.
        self.responder_las_primeras(2)

        self.assertEqual(self.iniciar()['indice_inicial'], 2)

    def test_con_todas_respondidas_abre_en_la_primera(self):
        # No queda ninguna pendiente, asi que se abre al principio para que
        # pueda repasar antes de entregar.
        self.responder_las_primeras(4)

        self.assertEqual(self.iniciar()['indice_inicial'], 0)

    def test_entrega_los_segundos_que_le_quedan_de_plazo(self):
        # La evaluacion de la prueba termina dentro de una hora.
        segundos = self.iniciar()['segundos_restantes']

        self.assertGreater(segundos, 3500)
        self.assertLessEqual(segundos, 3600)

    def test_quien_ya_presento_recibe_su_resultado(self):
        intento = IntentoEvaluacion.objects.create(
            evaluacion=self.evaluacion, alumno=self.alumno,
            estado=IntentoEvaluacion.Estado.FINALIZADO, calificacion=25,
        )
        self.responder(intento, self.preguntas[0], True)

        datos = self.iniciar()

        self.assertTrue(datos['finalizado'])
        self.assertEqual(datos['resultado']['total'], 4)
        self.assertEqual(datos['resultado']['aciertos'], 1)
        # No se le vuelve a montar el examen.
        self.assertNotIn('preguntas', datos)

    def test_puede_volver_por_su_resultado_con_la_evaluacion_cerrada(self):
        # Es el caso normal: se vuelve a leer la retroalimentacion cuando la
        # evaluacion ya termino, que es justo cuando el plazo diria que no.
        IntentoEvaluacion.objects.create(
            evaluacion=self.evaluacion, alumno=self.alumno,
            estado=IntentoEvaluacion.Estado.FINALIZADO, calificacion=50,
        )
        cerrar_evaluacion(self.evaluacion, anticipada=True)

        datos = self.iniciar()

        self.assertTrue(datos['finalizado'])

    def test_al_volver_no_se_le_dice_que_se_acabo_el_tiempo(self):
        # El aviso explica una interrupcion, y a quien entra por su cuenta a
        # leer su resultado no lo interrumpio nadie.
        IntentoEvaluacion.objects.create(
            evaluacion=self.evaluacion, alumno=self.alumno,
            estado=IntentoEvaluacion.Estado.FINALIZADO, calificacion=50,
        )
        cerrar_evaluacion(self.evaluacion, anticipada=True)

        self.assertNotIn('motivo', self.iniciar())

    def test_el_procedimiento_sigue_sin_viajar_durante_el_examen(self):
        # Se repite aqui la regla de siempre porque esta pantalla ahora
        # entrega resultados: el camino del examen no puede contagiarse.
        self.preguntas[0].procedimiento = 'Primero multiplicas y luego sumas.'
        self.preguntas[0].save(update_fields=['procedimiento'])

        respuesta = self.client.post(
            reverse('evaluaciones:api_iniciar', args=[self.evaluacion.id])
        )

        self.assertNotIn('Primero multiplicas', respuesta.content.decode())
