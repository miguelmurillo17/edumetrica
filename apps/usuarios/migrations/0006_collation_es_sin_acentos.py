"""Crea en PostgreSQL la collation con que se ordenan los combobox.

Vive en usuarios y no en catalogo porque usuarios es la primera aplicacion
que migra (es la del AUTH_USER_MODEL) y la collation la usan las tres:
Persona, Grupo, Materia y Categoria la piden en su Meta.ordering a traves de
config.orden_alfabetico.

En SQLite no hay nada que crear: su collation se registra en Python cada vez
que se abre una conexion, asi que aqui la migracion no hace nada.
"""

from django.db import migrations

from config.orden_alfabetico import LOCALE_ICU, NOMBRE_COLLATION

# Se deja deterministic en su valor por omision (verdadero) a proposito. Con
# eso PostgreSQL ordena con la clave de ICU, que es lo que queremos, pero
# desempata byte por byte y el "=" sigue comparando exacto; una collation no
# determinista haria que dos nombres que solo difieren en el acento se
# consideraran iguales, y ademas rompe los LIKE.
CREAR = (
    f'CREATE COLLATION IF NOT EXISTS "{NOMBRE_COLLATION}" '
    f"(provider = icu, locale = '{LOCALE_ICU}');"
)
BORRAR = f'DROP COLLATION IF EXISTS "{NOMBRE_COLLATION}";'


def crear_collation(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(CREAR)


def borrar_collation(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(BORRAR)


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0005_notificacion'),
    ]

    operations = [
        migrations.RunPython(crear_collation, borrar_collation),
    ]
