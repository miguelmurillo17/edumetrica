"""Orden alfabetico para los combobox, sin distinguir mayusculas ni acentos.

SQLite compara los textos por sus bytes UTF-8, asi que una palabra que
empieza con vocal acentuada (por ejemplo "Algebra") termina despues de toda
la Z en vez de junto a las demas A. PostgreSQL tampoco lo resuelve solo: lo
que haga depende del locale con que se creo el cluster, y con el locale C
ordena por bytes igual que SQLite.

Asi que los dos motores usan aqui la misma collation propia, "es_sin_acentos",
y por eso el orden es identico en desarrollo y en produccion. La diferencia
esta en quien la crea: en SQLite se registra en Python al abrir la conexion
(las de SQLite viven en el proceso, no en el archivo) y en PostgreSQL la crea
la migracion usuarios/0006 con el proveedor ICU, porque ahi la collation vive
en la base de datos.
"""

import unicodedata

from django.conf import settings
from django.db.backends.signals import connection_created
from django.db.models import F
from django.db.models.functions import Collate

NOMBRE_COLLATION = 'es_sin_acentos'

# Locale de ICU que usa la migracion: espanol comparando solo el primer nivel,
# el de la letra base, con lo que la mayuscula y el acento dejan de contar.
LOCALE_ICU = 'es-u-ks-level1'

_MOTOR = settings.DATABASES['default']['ENGINE']
TIENE_COLLATION = 'sqlite3' in _MOTOR or 'postgresql' in _MOTOR


def _sin_acentos(texto):
    if texto is None:
        return ''
    normalizado = unicodedata.normalize('NFKD', texto)
    return normalizado.encode('ascii', 'ignore').decode('ascii').lower()


def _comparar(a, b):
    a, b = _sin_acentos(a), _sin_acentos(b)
    return -1 if a < b else (1 if a > b else 0)


def _registrar_collation(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        connection.connection.create_collation(NOMBRE_COLLATION, _comparar)


connection_created.connect(_registrar_collation)


def alfabetico(*campos):
    """Expresiones de orden para Meta.ordering que ignoran acentos y mayusculas.

    En SQLite y en PostgreSQL ordena con la collation "es_sin_acentos". En
    cualquier otro motor devuelve el nombre del campo tal cual, que ordena
    como sepa: preferimos un orden imperfecto a una consulta que truene.
    """
    if TIENE_COLLATION:
        return [Collate(F(campo), NOMBRE_COLLATION) for campo in campos]
    return list(campos)
