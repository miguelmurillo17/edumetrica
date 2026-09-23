"""Orden alfabetico para los combobox, sin distinguir mayusculas ni acentos.

SQLite compara los textos por sus bytes UTF-8, asi que una palabra que
empieza con vocal acentuada (por ejemplo "Algebra") termina despues de toda
la Z en vez de junto a las demas A. MySQL en produccion ya lo resuelve con
su collation por omision, pero en desarrollo hay que registrar una collation
propia para que los select salgan en el orden que espera quien los lee.
"""

import unicodedata

from django.conf import settings
from django.db.backends.signals import connection_created
from django.db.models import F
from django.db.models.functions import Collate

NOMBRE_COLLATION = 'es_sin_acentos'

USA_SQLITE = 'sqlite3' in settings.DATABASES['default']['ENGINE']


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

    En SQLite usa la collation registrada arriba; en MySQL el collation por
    omision de utf8mb4 ya intercala los acentos junto a su letra, asi que
    basta con el nombre del campo.
    """
    if USA_SQLITE:
        return [Collate(F(campo), NOMBRE_COLLATION) for campo in campos]
    return list(campos)
