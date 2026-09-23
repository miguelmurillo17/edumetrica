"""
Ordenamiento por columnas para los listados del sistema, con el mismo
mecanismo que ya usaba a mano la lista de preguntas: todo viaja en la URL
(funciona sin JavaScript y se puede compartir), asi que aqui solo se separa
esa logica para no repetirla en cada listado nuevo.
"""

from urllib.parse import urlencode


def resolver_orden(request, columnas, filtros_activos=None):
    """Lee el orden pedido en la URL y arma los enlaces de cada cabecera.

    columnas: diccionario {clave_en_la_url: campo_real_del_modelo}. El campo
    real puede ser un solo nombre ("correo") o una tupla de varios cuando
    hace falta un criterio de desempate (por ejemplo ('apellido', 'nombre')
    para la columna "Nombre" de una Persona).
    filtros_activos: filtros vigentes, para conservarlos en los enlaces de
    ordenamiento.

    Devuelve (campo_orm, orden, direccion, columnas_orden). campo_orm es
    None cuando no se pidio ningun orden explicito (queda el que ya trae el
    queryset, normalmente el Meta.ordering del modelo); si no es None, es una
    tupla lista para queryset.order_by(*campo_orm, 'id').
    """
    filtros_activos = filtros_activos or {}

    orden = request.GET.get('orden', '')
    direccion = request.GET.get('dir', 'asc')
    if direccion not in ('asc', 'desc'):
        direccion = 'asc'

    campo_orm = None
    if orden in columnas:
        campos = columnas[orden]
        if isinstance(campos, str):
            campos = (campos,)
        if direccion == 'desc':
            campo_orm = tuple('-' + campo for campo in campos)
        else:
            campo_orm = tuple(campos)
    else:
        orden = ''
        direccion = 'asc'

    # Para cada columna ordenable se arma su enlace (conservando los filtros)
    # y se marca si es la que ordena ahora, para pintarle la flecha.
    columnas_orden = {}
    for clave in columnas:
        parametros = dict(filtros_activos)
        parametros['orden'] = clave
        if orden == clave and direccion == 'asc':
            parametros['dir'] = 'desc'
            indicador = 'asc'
        elif orden == clave and direccion == 'desc':
            parametros['dir'] = 'asc'
            indicador = 'desc'
        else:
            parametros['dir'] = 'asc'
            indicador = ''
        columnas_orden[clave] = {
            'url': '?' + urlencode(parametros),
            'indicador': indicador,
        }

    return campo_orm, orden, direccion, columnas_orden
