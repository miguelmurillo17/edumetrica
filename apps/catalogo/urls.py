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

    # CRUD del administrador para los catalogos.
    path('instituciones/', views.lista_instituciones, name='lista_instituciones'),
    path('instituciones/nueva/', views.crear_institucion, name='crear_institucion'),
    path(
        'instituciones/<int:institucion_id>/editar/',
        views.editar_institucion,
        name='editar_institucion',
    ),

    path('materias/', views.lista_materias, name='lista_materias'),
    path('materias/nueva/', views.crear_materia, name='crear_materia'),
    path('materias/<int:materia_id>/editar/', views.editar_materia, name='editar_materia'),

    path('categorias/', views.lista_categorias, name='lista_categorias'),
    path('categorias/nueva/', views.crear_categoria, name='crear_categoria'),
    path(
        'categorias/<int:categoria_id>/editar/',
        views.editar_categoria,
        name='editar_categoria',
    ),

    path('niveles/', views.lista_niveles, name='lista_niveles'),
    path('niveles/nuevo/', views.crear_nivel, name='crear_nivel'),
    path('niveles/<int:nivel_id>/editar/', views.editar_nivel, name='editar_nivel'),
]
