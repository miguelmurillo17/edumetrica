"""Formularios para dar de alta preguntas con sus opciones de respuesta."""

from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet

from .models import Pregunta, OpcionRespuesta, Categoria, Nivel

# Numero de opciones de respuesta que debe tener cada pregunta.
NUMERO_OPCIONES = 4


class PreguntaForm(forms.ModelForm):
    """Formulario del enunciado de la pregunta. La materia se toma de la categoria."""

    class Meta:
        model = Pregunta
        fields = ['categoria', 'nivel', 'enunciado', 'imagen']
        widgets = {
            'enunciado': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo se ofrecen las categorias activas, con su materia a la vista.
        self.fields['categoria'].queryset = (
            Categoria.objects.filter(activa=True).select_related('materia')
        )
        self.fields['nivel'].queryset = Nivel.objects.all()
        self.fields['categoria'].label = 'Categoria'
        self.fields['nivel'].label = 'Nivel'
        self.fields['enunciado'].label = 'Enunciado de la pregunta'
        self.fields['imagen'].label = 'Imagen de la pregunta (opcional)'


class OpcionRespuestaForm(forms.ModelForm):
    """Formulario de una opcion de respuesta. Acepta texto, imagen o ambos."""

    class Meta:
        model = OpcionRespuesta
        fields = ['texto', 'imagen', 'es_correcta']

    def clean(self):
        datos = super().clean()
        texto = datos.get('texto')
        imagen = datos.get('imagen')
        # Una opcion que tiene algun dato debe traer al menos texto o imagen.
        if not texto and not imagen:
            raise forms.ValidationError('La opcion debe tener texto o imagen.')
        return datos


class BaseOpcionesFormSet(BaseInlineFormSet):
    """Valida que se capturen las cuatro opciones y una sola correcta."""

    def clean(self):
        super().clean()
        # Si alguna opcion ya tiene errores no tiene caso seguir revisando.
        if any(self.errors):
            return

        opciones_con_contenido = 0
        correctas = 0
        for formulario in self.forms:
            if not formulario.cleaned_data:
                continue
            texto = formulario.cleaned_data.get('texto')
            imagen = formulario.cleaned_data.get('imagen')
            if texto or imagen:
                opciones_con_contenido += 1
            if formulario.cleaned_data.get('es_correcta'):
                correctas += 1

        if opciones_con_contenido != NUMERO_OPCIONES:
            raise forms.ValidationError(
                'Debes capturar las cuatro opciones de respuesta.'
            )
        if correctas != 1:
            raise forms.ValidationError(
                'Debes marcar exactamente una opcion como la correcta.'
            )


# Conjunto de formularios para editar las cuatro opciones junto con la pregunta.
OpcionRespuestaFormSet = inlineformset_factory(
    Pregunta,
    OpcionRespuesta,
    form=OpcionRespuestaForm,
    formset=BaseOpcionesFormSet,
    extra=NUMERO_OPCIONES,
    max_num=NUMERO_OPCIONES,
    can_delete=False,
)
