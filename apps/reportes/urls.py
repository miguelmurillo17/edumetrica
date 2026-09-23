"""Rutas del tablero de reportes."""

from django.urls import path

from . import views

app_name = 'reportes'

urlpatterns = [
    path('tablero/', views.dashboard, name='dashboard'),
    path('tablero/csv/', views.exportar_csv, name='exportar_csv'),
    path('tablero/intentos/', views.lista_intentos, name='lista_intentos'),
    path('tablero/intentos/<int:intento_id>/', views.detalle_intento, name='detalle_intento'),
]
