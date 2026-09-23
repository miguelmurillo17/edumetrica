"""Formularios para dar de alta preguntas con sus opciones de respuesta."""

from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet

from .models import (
    Pregunta, OpcionRespuesta, Categoria, CategoriaNivel, Materia, Nivel, Institucion,
)

# Numero de opciones de respuesta que debe tener cada pregunta.
NUMERO_OPCIONES = 4


class PreguntaForm(forms.ModelForm):
    """Formulario del enunciado de la pregunta. La materia se toma de la categoria."""

    class Meta:
        model = Pregunta
        # El procedimiento no va aqui: se captura paso a paso en la plantilla y
        # la vista lo arma antes de guardar. Ver apps.catalogo.procedimientos.
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
        self.fields['categoria'].label = 'Asignatura'
        self.fields['nivel'].label = 'Nivel'
        self.fields['enunciado'].label = 'Enunciado de la pregunta'
        self.fields['imagen'].label = 'Imagen de la pregunta (opcional)'


class GenerarPreguntaForm(forms.Form):
    """Pide la categoria y el nivel de la pregunta que se va a generar.

    No es un ModelForm: lo que se captura aqui no se guarda tal cual, sino que
    viaja al proveedor y regresa convertido en una pregunta.
    """

    categoria = forms.ModelChoiceField(
        queryset=Categoria.objects.none(),
        label='Asignatura',
        help_text='La disciplina se toma de la asignatura que elijas.',
    )
    nivel = forms.ModelChoiceField(
        queryset=Nivel.objects.none(),
        label='Nivel de dificultad',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].queryset = (
            Categoria.objects.filter(activa=True).select_related('materia')
        )
        self.fields['nivel'].queryset = Nivel.objects.all()


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
            # En el panel de administracion se pueden borrar opciones; las
            # marcadas para eliminar no cuentan.
            if formulario.cleaned_data.get('DELETE'):
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


class InstitucionForm(forms.ModelForm):
    """Datos de la escuela donde se usa el sistema."""

    class Meta:
        model = Institucion
        fields = ['nombre', 'direccion', 'telefono']


class MateriaForm(forms.ModelForm):
    """Alta y edicion de una disciplina."""

    class Meta:
        model = Materia
        fields = ['nombre', 'descripcion', 'activa', 'es_cuantitativa']


class CategoriaForm(forms.ModelForm):
    """Alta y edicion de una asignatura dentro de una disciplina."""

    class Meta:
        model = Categoria
        fields = ['materia', 'nombre', 'activa']


class NivelForm(forms.ModelForm):
    """Alta y edicion de un nivel de dificultad."""

    class Meta:
        model = Nivel
        fields = ['numero', 'nombre', 'descripcion']


class DescripcionesNivelForm(forms.Form):
    """Un campo de texto por cada nivel del catalogo, con el tipo de preguntas
    que le corresponde a la asignatura en ese nivel.

    No es un ModelForm ni un formset inline: esos necesitan que la asignatura
    ya tenga id para poder asociarle filas, y por eso el alta se quedaba sin
    este campo. Los niveles ya existen de antemano (los da de alta el
    administrador aparte), asi que aqui basta un campo de texto por nivel,
    sirve igual para dar de alta una asignatura que para editarla.
    """

    def __init__(self, *args, categoria=None, **kwargs):
        self.categoria = categoria
        super().__init__(*args, **kwargs)
        for nivel in Nivel.objects.all():
            inicial = ''
            if categoria is not None:
                fila = categoria.descripciones_nivel.filter(nivel=nivel).first()
                inicial = fila.descripcion if fila else ''
            self.fields[f'nivel_{nivel.id}'] = forms.CharField(
                required=False,
                initial=inicial,
                label=f'Tipo de preguntas — nivel {nivel.nombre}',
                widget=forms.Textarea(attrs={'rows': 2}),
            )

    def guardar(self, categoria):
        """Crea o actualiza la fila de cada nivel con lo que se capturo."""
        for nivel in Nivel.objects.all():
            CategoriaNivel.objects.update_or_create(
                categoria=categoria,
                nivel=nivel,
                defaults={'descripcion': self.cleaned_data.get(f'nivel_{nivel.id}', '')},
            )
