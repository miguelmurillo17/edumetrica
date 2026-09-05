"""Formulario para que el profesor programe una evaluacion a un grupo."""

from django import forms

from apps.catalogo.models import Materia, Categoria, Pregunta

from .models import Evaluacion


class EntradaFechaHora(forms.DateTimeInput):
    """Campo de fecha y hora que usa el selector nativo del navegador."""
    input_type = 'datetime-local'

    def __init__(self, attrs=None):
        super().__init__(attrs, format='%Y-%m-%dT%H:%M')


class EvaluacionForm(forms.ModelForm):
    """Recoge los datos de la evaluacion. Las preguntas se arman despues."""

    class Meta:
        model = Evaluacion
        fields = [
            'titulo', 'grupo', 'materia', 'categorias',
            'numero_preguntas', 'fecha_inicio', 'fecha_fin',
        ]
        widgets = {
            'categorias': forms.CheckboxSelectMultiple,
            'fecha_inicio': EntradaFechaHora,
            'fecha_fin': EntradaFechaHora,
        }

    def __init__(self, *args, profesor=None, **kwargs):
        super().__init__(*args, **kwargs)

        # El profesor solo puede programar a los grupos que tiene asignados.
        if profesor is not None:
            self.fields['grupo'].queryset = profesor.grupos_asignados.filter(activo=True)

        self.fields['materia'].queryset = Materia.objects.filter(activa=True)
        self.fields['categorias'].queryset = (
            Categoria.objects.filter(activa=True).select_related('materia')
        )

        # Los selectores de fecha entregan el dato en este formato.
        self.fields['fecha_inicio'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['fecha_fin'].input_formats = ['%Y-%m-%dT%H:%M']

        self.fields['titulo'].label = 'Titulo de la evaluacion'
        self.fields['numero_preguntas'].label = 'Numero de preguntas'
        self.fields['fecha_inicio'].label = 'Inicio'
        self.fields['fecha_fin'].label = 'Fin'

    def clean(self):
        datos = super().clean()
        inicio = datos.get('fecha_inicio')
        fin = datos.get('fecha_fin')
        materia = datos.get('materia')
        categorias = datos.get('categorias')
        numero = datos.get('numero_preguntas')

        # La evaluacion no puede terminar antes de empezar.
        if inicio and fin and fin <= inicio:
            self.add_error('fecha_fin', 'La fecha de fin debe ser posterior a la de inicio.')

        # Las categorias elegidas deben ser de la materia seleccionada.
        if materia and categorias:
            ajenas = [c for c in categorias if c.materia_id != materia.id]
            if ajenas:
                self.add_error(
                    'categorias',
                    'Todas las categorias deben pertenecer a la materia elegida.',
                )

        # Debe haber suficientes preguntas para armar la evaluacion.
        if categorias and numero:
            disponibles = Pregunta.objects.filter(
                activa=True, categoria__in=categorias
            ).count()
            if disponibles < numero:
                self.add_error(
                    'numero_preguntas',
                    f'Solo hay {disponibles} preguntas disponibles en las categorias elegidas.',
                )

        return datos
