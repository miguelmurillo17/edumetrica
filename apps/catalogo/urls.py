"""Rutas para la administracion del catalogo de preguntas."""

from django.urls import path

from . import views

app_name = 'catalogo'

urlpatterns = [
    path('preguntas/', views.lista_preguntas, name='lista_preguntas'),
    path('preguntas/nueva/', views.crear_pregunta, name='crear_pregunta'),
]
