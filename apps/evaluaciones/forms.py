"""Formularios para que el profesor programe una evaluacion a un grupo."""

from datetime import timedelta

from django import forms
from django.db.models import Q
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.utils import timezone

from apps.catalogo.models import Materia, Categoria, Pregunta
from apps.usuarios.models import Persona

from .models import Grupo, Evaluacion, CategoriaEvaluacion, AsignacionDocente

# Lo menos que puede durar una evaluacion. El alumno recibe un aviso cuando le
# quedan tres minutos, asi que una ventana mas corta que esta nacerian juntos el
# examen y su cuenta regresiva.
MINUTOS_MINIMOS = 5

# Cuanto se le perdona al profesor que la hora de inicio ya haya pasado. El
# caso comun es programarla para empezar "ahora mismo", y entre que elige la
# hora y acaba de llenar la tabla de asignaturas se le van unos minutos.
MINUTOS_DE_GRACIA = 5


class SelectConDisciplina(forms.Select):
    """Select de asignatura que marca a que disciplina pertenece cada opcion.

    El JavaScript de la plantilla usa el atributo para mostrar solo las
    opciones de la disciplina que se eligio arriba, sin pedirlas al servidor.
    """

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        opcion = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value:
            opcion['attrs']['data-disciplina'] = value.instance.materia_id
        return opcion


class SelectMultipleSinVacios(forms.SelectMultiple):
    """Igual que SelectMultiple, pero ignora los renglones sin elegir.

    La tabla de alumnos manda un <select name="alumnos"> por renglon; el que
    se quedo en "---------" manda cadena vacia, y sin filtrarla aqui esa ''
    llega hasta el pk__in de la validacion (o revienta contra el id numerico
    en alumnos_actuales, que hace su propio filtro).
    """

    def value_from_datadict(self, data, files, name):
        valores = super().value_from_datadict(data, files, name)
        return [valor for valor in valores if valor]


class EntradaFechaHora(forms.DateTimeInput):
    """Campo de fecha y hora que usa el selector nativo del navegador."""
    input_type = 'datetime-local'

    def __init__(self, attrs=None):
        super().__init__(attrs, format='%Y-%m-%dT%H:%M')


class EvaluacionForm(forms.ModelForm):
    """Recoge los datos generales. Las categorias van en su propia tabla."""

    class Meta:
        model = Evaluacion
        fields = ['titulo', 'grupo', 'materia', 'fecha_inicio', 'fecha_fin']
        widgets = {
            'fecha_inicio': EntradaFechaHora,
            'fecha_fin': EntradaFechaHora,
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)

        # El profesor solo puede programar a los grupos que tiene asignados y
        # solo las disciplinas que imparte en ellos. El superusuario, que no
        # tiene asignaciones, puede hacerlo con cualquiera.
        grupos = Grupo.objects.filter(activo=True)
        materias = Materia.objects.filter(activa=True)
        if usuario is not None and usuario.es_profesor:
            grupos = grupos.filter(profesores=usuario).distinct()
            materias = materias.filter(
                categorias__asignaciones__profesor=usuario
            ).distinct()
        self.fields['grupo'].queryset = grupos
        self.fields['materia'].queryset = materias

        # Los selectores de fecha entregan el dato en este formato.
        self.fields['fecha_inicio'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['fecha_fin'].input_formats = ['%Y-%m-%dT%H:%M']

        self.fields['titulo'].label = 'Título de la evaluación'
        self.fields['materia'].label = 'Disciplina'
        self.fields['fecha_inicio'].label = 'Inicio'
        self.fields['fecha_fin'].label = 'Fin'

    def clean(self):
        datos = super().clean()
        inicio = datos.get('fecha_inicio')
        fin = datos.get('fecha_fin')

        # La evaluacion no puede terminar antes de empezar.
        if inicio and fin:
            if fin <= inicio:
                self.add_error('fecha_fin', 'La fecha de fin debe ser posterior a la de inicio.')
            elif fin - inicio < timedelta(minutes=MINUTOS_MINIMOS):
                self.add_error(
                    'fecha_fin',
                    f'La evaluación debe durar al menos {MINUTOS_MINIMOS} minutos.',
                )

        # Programar una evaluacion que ya paso dejaria a los alumnos sin
        # oportunidad de presentarla: nace cerrada. Solo se revisa al
        # programarla, porque una evaluacion vieja se debe poder editar.
        if inicio and self.instance.pk is None:
            limite = timezone.now() - timedelta(minutes=MINUTOS_DE_GRACIA)
            if inicio < limite:
                self.add_error(
                    'fecha_inicio', 'La fecha de inicio no puede estar en el pasado.'
                )

        return datos


class CategoriaEvaluacionForm(forms.ModelForm):
    """Un renglon de la tabla: una categoria y cuantas preguntas se toman."""

    class Meta:
        model = CategoriaEvaluacion
        fields = ['categoria', 'numero_preguntas']
        widgets = {
            'categoria': SelectConDisciplina,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].queryset = (
            Categoria.objects.filter(activa=True).select_related('materia')
        )
        self.fields['numero_preguntas'].widget.attrs['min'] = 1


class BaseCategoriasFormSet(BaseInlineFormSet):
    """Valida los renglones de asignaturas de la evaluacion.

    La materia, el grupo y el usuario se asignan desde la vista antes de
    validar, porque viven en el otro formulario y hacen falta para revisar que
    las asignaturas le toquen al profesor en ese grupo.
    """

    materia = None
    grupo = None
    usuario = None

    def add_fields(self, form, index):
        super().add_fields(form, index)
        # El profesor solo puede elegir asignaturas que imparte en alguno de sus
        # grupos; en clean() se afina que sea justo la del grupo elegido.
        if self.usuario is not None and self.usuario.es_profesor:
            if 'categoria' in form.fields:
                form.fields['categoria'].queryset = (
                    Categoria.objects
                    .filter(activa=True, asignaciones__profesor=self.usuario)
                    .distinct()
                    .select_related('materia')
                )

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        renglones = []
        for formulario in self.forms:
            datos = formulario.cleaned_data
            # Los renglones vacios o marcados para borrar no cuentan.
            if not datos or datos.get('DELETE'):
                continue
            if datos.get('categoria') is None:
                continue
            renglones.append(datos)

        if not renglones:
            raise forms.ValidationError(
                'Debes agregar al menos una asignatura con su número de preguntas.'
            )

        # Una misma asignatura no se puede capturar dos veces.
        elegidas = [datos['categoria'] for datos in renglones]
        if len(elegidas) != len(set(elegidas)):
            raise forms.ValidationError('Hay asignaturas repetidas en la tabla.')

        # Asignaturas que el profesor imparte en el grupo elegido. El
        # superusuario no tiene asignaciones, asi que no se le restringe.
        asignadas = None
        if self.usuario is not None and self.usuario.es_profesor and self.grupo is not None:
            asignadas = set(
                AsignacionDocente.objects
                .filter(grupo=self.grupo, profesor=self.usuario)
                .values_list('categoria_id', flat=True)
            )

        for datos in renglones:
            categoria = datos['categoria']
            numero = datos.get('numero_preguntas')

            # Todas las asignaturas deben ser de la disciplina elegida.
            if self.materia is not None and categoria.materia_id != self.materia.id:
                raise forms.ValidationError(
                    f'La asignatura {categoria.nombre} no pertenece a la disciplina elegida.'
                )

            # Y el profesor debe impartirla en ese grupo.
            if asignadas is not None and categoria.id not in asignadas:
                raise forms.ValidationError(
                    f'No impartes la asignatura {categoria.nombre} en el grupo elegido.'
                )

            if not numero or numero < 1:
                raise forms.ValidationError(
                    f'La asignatura {categoria.nombre} debe pedir al menos una pregunta.'
                )

            # Debe haber preguntas suficientes en el banco. Solo cuentan las
            # utilizables, es decir las que ya paso alguien por validacion.
            disponibles = Pregunta.objects.utilizables().filter(categoria=categoria).count()
            if disponibles < numero:
                raise forms.ValidationError(
                    f'La asignatura {categoria.nombre} solo tiene {disponibles} '
                    f'preguntas disponibles.'
                )


# Tabla de categorias que se captura junto con la evaluacion.
CategoriaEvaluacionFormSet = inlineformset_factory(
    Evaluacion,
    CategoriaEvaluacion,
    form=CategoriaEvaluacionForm,
    formset=BaseCategoriasFormSet,
    extra=1,
    can_delete=True,
)


class GrupoForm(forms.ModelForm):
    """Alta y edicion de un grupo: sus alumnos los asigna el administrador.

    Un alumno solo pertenece a un grupo a la vez, asi que el campo "alumnos"
    se captura como una tabla (un renglon por alumno, igual que la plantilla
    docente) en vez del selector multiple de toda la vida.
    """

    class Meta:
        model = Grupo
        fields = ['nombre', 'institucion', 'alumnos', 'activo']
        widgets = {
            'alumnos': SelectMultipleSinVacios,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo se pueden elegir alumnos sin grupo, mas los que ya son de
        # este (para no perderlos al editar).
        sin_grupo = Q(grupos__isnull=True)
        if self.instance.pk:
            sin_grupo |= Q(grupos=self.instance.pk)
        self.fields['alumnos'].queryset = (
            Persona.objects.filter(rol=Persona.Rol.ALUMNO).filter(sin_grupo).distinct()
        )
        self.fields['alumnos'].help_text = (
            'Solo aparecen los alumnos que no pertenecen a otro grupo.'
        )

    @property
    def alumnos_actuales(self):
        """Alumnos que debe traer marcados la tabla al pintar la pantalla.

        Si el formulario viene de un POST invalido se repite lo que la
        persona ya habia elegido, para no perder su trabajo; si no, son los
        alumnos que el grupo ya tiene guardados (ninguno si es nuevo).
        """
        if self.is_bound:
            # Se reutiliza el widget para leer los valores: ya sabe ignorar
            # el renglon que se quedo en "---------" (manda cadena vacia, y
            # sin filtrarla revienta el pk__in contra el id numerico).
            campo = self.fields['alumnos']
            valores = campo.widget.value_from_datadict(
                self.data, self.files, self.add_prefix('alumnos')
            )
            return campo.queryset.filter(pk__in=valores)
        if self.instance.pk:
            return self.instance.alumnos.all()
        return Persona.objects.none()

    def clean(self):
        datos = super().clean()
        alumnos = datos.get('alumnos')
        if alumnos is None:
            return datos

        # La tabla no impide elegir al mismo alumno en dos renglones: el
        # campo llega deduplicado (es un ModelMultipleChoiceField), asi que
        # se compara contra lo que mando cada renglon.
        campo = self.fields['alumnos']
        valores = campo.widget.value_from_datadict(
            self.data, self.files, self.add_prefix('alumnos')
        )
        if len(valores) != len(set(valores)):
            self.add_error(None, 'No puedes agregar al mismo alumno más de una vez.')

        # El queryset del campo ya descarta a quien estaba en otro grupo
        # cuando se abrio el formulario, pero se revisa otra vez contra la
        # base de datos por si alguien mas lo asigno mientras tanto. Se
        # revisa persona por persona -y no con un solo filter()- porque
        # combinar "tiene grupo" con "no es este grupo" sobre la misma
        # relacion de muchos a muchos en un filter() no hace lo que parece:
        # Django no reutiliza el join con la negacion y el resultado sale
        # mal (documentado en "Spanning multi-valued relationships").
        frescos = Persona.objects.filter(pk__in=[persona.pk for persona in alumnos])
        en_otro_grupo = []
        for persona in frescos:
            otros_grupos = persona.grupos.all()
            if self.instance.pk:
                otros_grupos = otros_grupos.exclude(pk=self.instance.pk)
            if otros_grupos.exists():
                en_otro_grupo.append(persona)
        if en_otro_grupo:
            nombres = ', '.join(persona.nombre_completo for persona in en_otro_grupo)
            self.add_error(None, f'Ya pertenecen a otro grupo: {nombres}.')

        return datos


class AsignacionDocenteForm(forms.ModelForm):
    """Un renglon de la tabla: que asignatura imparte un profesor en el grupo."""

    class Meta:
        model = AsignacionDocente
        fields = ['profesor', 'categoria']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['profesor'].queryset = Persona.objects.filter(rol=Persona.Rol.PROFESOR)
        self.fields['categoria'].queryset = (
            Categoria.objects.filter(activa=True).select_related('materia')
        )


# Tabla de asignaciones docentes (profesor + asignatura) que se captura junto
# con el grupo. El related_name "asignaciones" del modelo AsignacionDocente
# ya arma el prefijo de los campos, igual que categorias_elegidas arriba.
AsignacionDocenteFormSet = inlineformset_factory(
    Grupo,
    AsignacionDocente,
    form=AsignacionDocenteForm,
    extra=1,
    can_delete=True,
)
