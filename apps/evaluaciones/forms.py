"""Formularios para que el profesor programe una evaluacion a un grupo."""

from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet

from apps.catalogo.models import Materia, Categoria, Pregunta

from .models import Grupo, Evaluacion, CategoriaEvaluacion


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

        # El profesor solo puede programar a los grupos que tiene asignados.
        # El superusuario, que no tiene grupos, puede hacerlo a cualquiera.
        grupos = Grupo.objects.filter(activo=True)
        if usuario is not None and usuario.es_profesor:
            grupos = grupos.filter(profesores=usuario)
        self.fields['grupo'].queryset = grupos

        self.fields['materia'].queryset = Materia.objects.filter(activa=True)

        # Los selectores de fecha entregan el dato en este formato.
        self.fields['fecha_inicio'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['fecha_fin'].input_formats = ['%Y-%m-%dT%H:%M']

        self.fields['titulo'].label = 'Título de la evaluación'
        self.fields['fecha_inicio'].label = 'Inicio'
        self.fields['fecha_fin'].label = 'Fin'

    def clean(self):
        datos = super().clean()
        inicio = datos.get('fecha_inicio')
        fin = datos.get('fecha_fin')

        # La evaluacion no puede terminar antes de empezar.
        if inicio and fin and fin <= inicio:
            self.add_error('fecha_fin', 'La fecha de fin debe ser posterior a la de inicio.')

        return datos


class CategoriaEvaluacionForm(forms.ModelForm):
    """Un renglon de la tabla: una categoria y cuantas preguntas se toman."""

    class Meta:
        model = CategoriaEvaluacion
        fields = ['categoria', 'numero_preguntas']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].queryset = (
            Categoria.objects.filter(activa=True).select_related('materia')
        )
        self.fields['numero_preguntas'].widget.attrs['min'] = 1


class BaseCategoriasFormSet(BaseInlineFormSet):
    """Valida los renglones de categorias de la evaluacion.

    La materia se asigna desde la vista antes de validar, porque vive en el
    otro formulario y hace falta para revisar que las categorias le toquen.
    """

    materia = None

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
                'Debes agregar al menos una categoría con su número de preguntas.'
            )

        # Una misma categoria no se puede capturar dos veces.
        elegidas = [datos['categoria'] for datos in renglones]
        if len(elegidas) != len(set(elegidas)):
            raise forms.ValidationError('Hay categorías repetidas en la tabla.')

        for datos in renglones:
            categoria = datos['categoria']
            numero = datos.get('numero_preguntas')

            # Todas las categorias deben ser de la materia elegida.
            if self.materia is not None and categoria.materia_id != self.materia.id:
                raise forms.ValidationError(
                    f'La categoría {categoria.nombre} no pertenece a la materia elegida.'
                )

            if not numero or numero < 1:
                raise forms.ValidationError(
                    f'La categoría {categoria.nombre} debe pedir al menos una pregunta.'
                )

            # Debe haber preguntas suficientes en el banco.
            disponibles = Pregunta.objects.filter(activa=True, categoria=categoria).count()
            if disponibles < numero:
                raise forms.ValidationError(
                    f'La categoría {categoria.nombre} solo tiene {disponibles} '
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
