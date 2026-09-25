"""
Comando que cierra las evaluaciones cuyo plazo ya vencio, junto con los
intentos que quedaron abiertos.

El sistema no tiene nada corriendo en segundo plano: el cierre normal es
perezoso y ocurre cuando alguien mira la evaluacion (el panel del alumno, el
listado del profesor, el tablero o cualquier peticion de la aplicacion del
alumno). Este comando hace lo mismo sin que nadie tenga el navegador abierto,
para poder dejarlo en cron.

Se ejecuta con: python manage.py cerrar_evaluaciones
"""

from django.core.management.base import BaseCommand

from apps.evaluaciones.models import Evaluacion
from apps.evaluaciones.servicios import actualizar_estados


class Command(BaseCommand):
    help = 'Cierra las evaluaciones vencidas y los intentos que dejaron abiertos.'

    def handle(self, *args, **opciones):
        # Se anotan antes para poder decir cuales se cerraron en esta corrida.
        abiertas = list(
            Evaluacion.objects
            .exclude(estado=Evaluacion.Estado.FINALIZADA)
            .values_list('id', flat=True)
        )

        actualizar_estados()

        cerradas = (
            Evaluacion.objects
            .filter(id__in=abiertas, estado=Evaluacion.Estado.FINALIZADA)
            .select_related('grupo')
        )
        total = cerradas.count()

        if total == 0:
            self.stdout.write('No habia evaluaciones por cerrar.')
            return

        for evaluacion in cerradas:
            self.stdout.write(
                f'Cerrada: {evaluacion.titulo} ({evaluacion.grupo.nombre})'
            )

        cuenta = '1 evaluacion cerrada.' if total == 1 else f'{total} evaluaciones cerradas.'
        self.stdout.write(self.style.SUCCESS(cuenta))
