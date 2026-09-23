"""Rutas de los paneles, las evaluaciones y la interfaz de programacion del alumno."""

from django.urls import path

from . import views
from . import api

app_name = 'evaluaciones'

urlpatterns = [
    # Paneles
    path('profesor/', views.panel_profesor, name='panel_profesor'),
    path('alumno/', views.panel_alumno, name='panel_alumno'),

    # Grupos: el profesor solo consulta, el administrador tambien da de alta y edita.
    path('grupos/', views.lista_grupos, name='lista_grupos'),
    path('grupos/nuevo/', views.crear_grupo, name='crear_grupo'),
    path('grupos/<int:grupo_id>/editar/', views.editar_grupo, name='editar_grupo'),

    # Evaluaciones del profesor
    path('evaluaciones/', views.lista_evaluaciones, name='lista_evaluaciones'),
    path('evaluaciones/nueva/', views.crear_evaluacion, name='crear_evaluacion'),
    path('evaluaciones/<int:evaluacion_id>/', views.detalle_evaluacion, name='detalle_evaluacion'),
    path('evaluaciones/<int:evaluacion_id>/finalizar/', views.finalizar_evaluacion, name='finalizar_evaluacion'),

    # Presentacion de la evaluacion por el alumno
    path('alumno/evaluacion/<int:evaluacion_id>/', views.presentar_evaluacion, name='presentar_evaluacion'),

    # Endpoints JSON que consume la aplicacion de Vue del alumno
    path('api/alumno/evaluaciones/<int:evaluacion_id>/iniciar/', api.iniciar_evaluacion, name='api_iniciar'),
    path('api/alumno/intentos/<int:intento_id>/responder/', api.responder_pregunta, name='api_responder'),
    path('api/alumno/intentos/<int:intento_id>/finalizar/', api.finalizar_intento, name='api_finalizar'),
    path('api/alumno/intentos/<int:intento_id>/resultado/', api.resultado_intento, name='api_resultado'),
    path('api/alumno/intentos/<int:intento_id>/estado/', api.estado_intento, name='api_estado'),
]
