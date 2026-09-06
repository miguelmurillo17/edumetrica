"""Rutas para la administracion del catalogo de preguntas."""

from django.urls import path

from . import views

app_name = 'catalogo'

urlpatterns = [
    path('preguntas/', views.lista_preguntas, name='lista_preguntas'),
    path('preguntas/nueva/', views.crear_pregunta, name='crear_pregunta'),
    path('preguntas/<int:pregunta_id>/editar/', views.editar_pregunta, name='editar_pregunta'),
    path('preguntas/generar/', views.generar_pregunta, name='generar_pregunta'),
    path(
        'preguntas/generando/<int:solicitud_id>/',
        views.esperar_generacion,
        name='esperar_generacion',
    ),
    # Sondeo de la pantalla de espera: contesta si la generacion ya termino.
    path(
        'preguntas/generando/<int:solicitud_id>/estado/',
        views.estado_generacion,
        name='estado_generacion',
    ),
    path(
        'preguntas/<int:pregunta_id>/revisar/',
        views.revisar_pregunta,
        name='revisar_pregunta',
    ),
    path(
        'preguntas/<int:pregunta_id>/resolver/',
        views.resolver_pregunta,
        name='resolver_pregunta',
    ),
]
