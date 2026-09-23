"""
Reduce el catalogo de niveles de dificultad de seis a tres.

Antes de borrar los niveles 4, 5 y 6 hay que reasignar a las preguntas y
solicitudes de generacion que los usaban, porque su relacion con Nivel esta
protegida (on_delete=PROTECT) y el borrado fallaria con datos colgando.

El mapeo es el mismo que se aplico al banco de preguntas capturado a mano:
1-2 caen en el nuevo nivel 1, 3-4 en el nuevo nivel 2, y 5-6 en el nuevo
nivel 3. De paso se renombran el 2 y el 3 para que el nombre describa su
lugar en la escala de tres, no la de seis.
"""

from django.db import migrations


MAPEO_NUMERO_NUEVO = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3}

NOMBRES_NUEVOS = {
    1: 'Básico',
    2: 'Intermedio',
    3: 'Avanzado',
}


def reducir_a_tres_niveles(apps, schema_editor):
    Nivel = apps.get_model('catalogo', 'Nivel')
    Pregunta = apps.get_model('catalogo', 'Pregunta')
    SolicitudGeneracion = apps.get_model('catalogo', 'SolicitudGeneracion')

    niveles_por_numero = {nivel.numero: nivel for nivel in Nivel.objects.all()}

    for numero_viejo, numero_nuevo in MAPEO_NUMERO_NUEVO.items():
        nivel_viejo = niveles_por_numero.get(numero_viejo)
        nivel_nuevo = niveles_por_numero.get(numero_nuevo)
        if not nivel_viejo or not nivel_nuevo or nivel_viejo == nivel_nuevo:
            continue
        Pregunta.objects.filter(nivel=nivel_viejo).update(nivel=nivel_nuevo)
        SolicitudGeneracion.objects.filter(nivel=nivel_viejo).update(nivel=nivel_nuevo)

    # Ya sin nada que los referencie, se pueden borrar los niveles que sobran.
    Nivel.objects.filter(numero__in=[4, 5, 6]).delete()

    for numero, nombre in NOMBRES_NUEVOS.items():
        Nivel.objects.filter(numero=numero).update(nombre=nombre)


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0011_categorianivel'),
    ]

    operations = [
        migrations.RunPython(reducir_a_tres_niveles, migrations.RunPython.noop),
    ]
