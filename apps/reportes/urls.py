"""Rutas del tablero de reportes."""

from django.urls import path

from . import views

app_name = 'reportes'

urlpatterns = [
    path('tablero/', views.dashboard, name='dashboard'),
    path('tablero/csv/', views.exportar_csv, name='exportar_csv'),
]
