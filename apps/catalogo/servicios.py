"""
Puente entre el catalogo del sistema y el modulo de inteligencia artificial.

El modulo apps.ia no conoce los modelos de Django: recibe texto y devuelve
preguntas sueltas. Aqui se traduce en las dos direcciones: se arma la peticion
a partir de la materia, la categoria y el nivel del catalogo, y lo que regresa
se somete al verificador simbolico y se guarda como borrador.

Una pregunta generada NUNCA se guarda como validada. Nace en borrador y espera
a que el profesor la revise, aunque el verificador la haya aprobado.
"""

import logging
import threading
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.ia.errores import ErrorProveedorIA
from apps.ia.proveedores import obtener_proveedor
from apps.ia.servicios import generar_preguntas

from .models import OpcionRespuesta, Pregunta, SolicitudGeneracion
from .verificador import verificar

registro = logging.getLogger(__name__)

# Segundos que se le conceden al hilo por encima del peor caso del proveedor
# antes de dar por perdida una generacion que sigue en proceso.
MARGEN_DE_GRACIA = 30


def hay_llave_configurada():
    """Dice si el proveedor activo tiene llave, sin llamarlo.

    Sirve para no ofrecer la pantalla de generacion cuando no esta configurada.
    Es una comprobacion local: no gasta cuota ni tarda.
    """
    try:
        proveedor = obtener_proveedor(settings.AI_PROVIDER)
    except Exception:
        # Un proveedor mal escrito en el archivo .env vale lo mismo que no
        # tener llave: la pantalla no se ofrece.
        return False
    return bool((settings.AI_LLAVES.get(proveedor.clave) or '').strip())


def solicitudes_de_la_ultima_hora(profesor):
    """Cuantas generaciones lleva pedidas el profesor en la ultima hora.

    Cuentan todas, salgan bien o mal: las dos tocaron al proveedor, y si solo
    contaran las exitosas se podria insistir sin limite contra un proveedor
    caido, que es justo el camino que mas se va a ver.
    """
    desde = timezone.now() - timedelta(hours=1)
    return SolicitudGeneracion.objects.filter(
        profesor=profesor, fecha__gte=desde
    ).count()


def alcanzo_el_tope(profesor):
    """Verdadero si el profesor ya agoto su cupo de la hora."""
    return solicitudes_de_la_ultima_hora(profesor) >= settings.AI_LIMITE_POR_HORA


def _se_quedo_a_medias(solicitud):
    """Verdadero si el hilo de esta solicitud ya no puede seguir vivo.

    El hilo muere con el proceso, asi que un reinicio del servidor a media
    llamada dejaria la solicitud en proceso para siempre y a la pantalla de
    espera contando segundos sin remedio. Se le da el peor caso del proveedor
    -todos los intentos agotando su tiempo de espera- mas un margen, y pasado
    eso se da por perdida.
    """
    intentos = settings.AI_MAX_RETRIES + 1
    limite = timedelta(
        seconds=settings.AI_TIMEOUT * intentos + MARGEN_DE_GRACIA
    )
    return timezone.now() - solicitud.fecha > limite


def _guardar_pregunta(generada, dictamen, solicitud, profesor):
    """Guarda la pregunta con sus cuatro opciones y el fallo del verificador."""
    pregunta = Pregunta.objects.create(
        materia=solicitud.categoria.materia,
        categoria=solicitud.categoria,
        nivel=solicitud.nivel,
        enunciado=generada.enunciado,
        procedimiento=generada.procedimiento,
        creada_por=profesor,
        origen=Pregunta.Origen.IA,
        # Aunque el verificador la apruebe, la revisa una persona antes de que
        # pueda entrar a una evaluacion.
        estado=(
            Pregunta.Estado.BORRADOR if dictamen.aprobada
            else Pregunta.Estado.DESCARTADA
        ),
        # Queda en nulo cuando no habia expresion que comprobar.
        verificada_simbolicamente=dictamen.aprobada if dictamen.aplica else None,
        motivo_rechazo=dictamen.motivo,
        solicitud=solicitud,
    )

    for posicion, texto in enumerate(generada.opciones):
        OpcionRespuesta.objects.create(
            pregunta=pregunta,
            texto=texto,
            es_correcta=(posicion == generada.indice_correcto),
        )

    return pregunta


def crear_solicitud(*, profesor, categoria, nivel):
    """Registra la solicitud antes de llamar al proveedor.

    Se separa del trabajo en si porque la vista necesita el identificador de
    inmediato: redirige a la pantalla de espera, que sondea esta misma fila
    para saber cuando termino la generacion.
    """
    return SolicitudGeneracion.objects.create(
        profesor=profesor,
        materia=categoria.materia,
        categoria=categoria,
        nivel=nivel,
        cantidad_pedida=1,
    )


def generar_pregunta(*, profesor, categoria, nivel, solicitud=None):
    """Genera una pregunta, la verifica y la guarda como borrador.

    Devuelve (pregunta, dictamen). La pregunta queda en borrador si paso el
    verificador y descartada si no, pero en los dos casos se guarda: las
    descartadas son el dato de cuantas rechazo la comprobacion, que es parte
    de lo que se quiere medir.

    Si no se recibe una solicitud se crea aqui, que es como la usa el comando
    de consola. La vista si la crea antes, porque necesita el identificador
    para mandar al profesor a la pantalla de espera.

    Puede levantar ErrorConfiguracionIA, ErrorProveedorIA o ErrorRespuestaIA.
    La solicitud queda registrada tambien cuando falla, con el motivo.

    Ojo con las transacciones: el registro del fallo NO puede ir dentro de una
    transaccion que se revierta al relanzar la excepcion, o se perderia justo
    el dato de cuantos intentos hicieron falta. Por eso el fallo se guarda
    fuera de todo bloque atomico, y el exito dentro del mismo que guarda la
    pregunta.
    """
    materia = categoria.materia

    if solicitud is None:
        solicitud = crear_solicitud(
            profesor=profesor, categoria=categoria, nivel=nivel
        )

    try:
        resultado = generar_preguntas(
            materia=materia.nombre,
            categoria=categoria.nombre,
            nivel=nivel.numero,
            cantidad=1,
            descripcion_nivel=nivel.nombre,
            # Si la materia es cuantitativa, la pregunta tiene que traer la
            # expresion o se estaria saltando el verificador.
            exige_expresion=materia.es_cuantitativa,
        )
    except Exception as error:
        # La solicitud fallida tambien se guarda: sin ella no se sabria cuantos
        # intentos hicieron falta para armar el banco.
        #
        # El mensaje y el detalle van en campos distintos a proposito: el
        # mensaje ya viene redactado para que lo lea el profesor, y el detalle
        # es el texto crudo del proveedor, que solo va a la bitacora.
        solicitud.estado = SolicitudGeneracion.Estado.FALLIDA
        solicitud.mensaje_error = str(error)
        solicitud.tipo_error = getattr(error, 'tipo', '')
        solicitud.detalle_error = getattr(error, 'detalle', '')[:2000] or str(error)[:2000]
        solicitud.save(update_fields=[
            'estado', 'mensaje_error', 'tipo_error', 'detalle_error',
        ])
        raise

    solicitud.modelo = resultado.modelo
    solicitud.tokens_entrada = resultado.tokens_entrada
    solicitud.tokens_salida = resultado.tokens_salida
    solicitud.cantidad_recibida = len(resultado.preguntas)
    solicitud.estado = SolicitudGeneracion.Estado.EXITOSA

    generada = resultado.preguntas[0]
    dictamen = verificar(
        generada.expresion,
        generada.valores_para_verificar,
        generada.indice_correcto,
    )

    solicitud.cantidad_aprobada = 1 if dictamen.aprobada else 0

    # Las tres cosas van juntas y en este orden importa que asi sea. La
    # pregunta y sus cuatro opciones, porque una pregunta a medio guardar
    # seria peor que ninguna. Y la solicitud con ellas, porque la pantalla de
    # espera lee el estado para saber si ya hay algo que revisar: si se
    # marcara exitosa un instante antes de que la pregunta exista, el sondeo
    # que cayera en esa rendija veria un lote terminado y vacio.
    with transaction.atomic():
        solicitud.save()
        pregunta = _guardar_pregunta(generada, dictamen, solicitud, profesor)

    registro.info(
        'Pregunta %s generada para %s / %s: %s',
        pregunta.id, materia.nombre, categoria.nombre,
        'aprobada por el verificador' if dictamen.aprobada
        else f'rechazada ({dictamen.motivo})',
    )
    return pregunta, dictamen


def _trabajar_en_hilo(solicitud_id):
    """Cuerpo del hilo: genera la pregunta de una solicitud ya registrada.

    Nada de lo que ocurre aqui llega al profesor por excepcion, porque nadie
    esta esperando la respuesta: el fallo se guarda en la solicitud y la
    pantalla de espera lo lee en su siguiente sondeo.
    """
    try:
        solicitud = SolicitudGeneracion.objects.select_related(
            'profesor', 'categoria__materia', 'nivel'
        ).get(id=solicitud_id)
        try:
            generar_pregunta(
                profesor=solicitud.profesor,
                categoria=solicitud.categoria,
                nivel=solicitud.nivel,
                solicitud=solicitud,
            )
        except Exception:
            # generar_pregunta ya dejo la solicitud marcada como fallida con su
            # mensaje; aqui solo queda el rastro para la bitacora.
            registro.warning('La solicitud %s no pudo completarse', solicitud_id)
    except Exception:
        registro.exception('Fallo no previsto en la solicitud %s', solicitud_id)
    finally:
        # Cada hilo abre su propia conexion a la base de datos y hay que
        # cerrarla, o se van acumulando conexiones abiertas.
        connection.close()


def lanzar_generacion(*, profesor, categoria, nivel):
    """Registra la solicitud y arranca la generacion en segundo plano.

    Devuelve la solicitud de inmediato, sin esperar al proveedor. Una
    generacion tarda unos veinte segundos cuando sale bien, y con el reintento
    puede llegar al minuto: sostener la peticion todo ese tiempo no funciona,
    porque un servidor de produccion suele cortar a los treinta segundos.

    Se usa un hilo y no una cola de tareas a proposito. Una cola exigiria otro
    servicio corriendo, y el proyecto ya resolvio antes un problema parecido
    -avisarle al alumno que el profesor cerro la evaluacion- con sondeo en
    lugar de infraestructura nueva. Este es el mismo trato.
    """
    if alcanzo_el_tope(profesor):
        # La vista tambien lo comprueba, que es donde el profesor recibe la
        # explicacion; esta es la red. El tope cuida la cuota de toda la
        # institucion y no puede depender de que la pantalla se acuerde, igual
        # que la cantidad de preguntas se valida en el formulario y otra vez
        # en el servicio que la usa.
        raise ValueError(
            f'El profesor ya pidió {settings.AI_LIMITE_POR_HORA} generaciones '
            f'en la última hora.'
        )

    solicitud = crear_solicitud(
        profesor=profesor, categoria=categoria, nivel=nivel
    )
    hilo = threading.Thread(
        target=_trabajar_en_hilo,
        args=(solicitud.id,),
        daemon=True,
    )
    hilo.start()
    return solicitud


def mensaje_de_espera(solicitud):
    """Lo que la pantalla de espera debe contestarle al sondeo.

    El texto crudo del proveedor no aparece por ningun lado: se manda el
    mensaje ya redactado, que es el que explica de quien es el problema.
    """
    if solicitud.estado == SolicitudGeneracion.Estado.EN_PROCESO:
        if not _se_quedo_a_medias(solicitud):
            return {'estado': 'en_proceso'}
        # Se anota en la solicitud y no solo en la respuesta: de esta tabla
        # salen los numeros del capitulo de resultados, y una solicitud que se
        # quedo en proceso para siempre los ensucia. Si el hilo siguiera vivo
        # despues de todo, al terminar sobrescribe esto y el siguiente sondeo
        # ve la pregunta.
        solicitud.estado = SolicitudGeneracion.Estado.FALLIDA
        solicitud.mensaje_error = (
            'La generación se interrumpió antes de terminar. Suele pasar '
            'cuando el servidor se reinicia a media petición. Puedes '
            'intentarlo de nuevo.'
        )
        solicitud.save(update_fields=['estado', 'mensaje_error'])

    if solicitud.estado == SolicitudGeneracion.Estado.FALLIDA:
        return {
            'estado': 'fallida',
            'mensaje': solicitud.mensaje_error,
            'tipo': solicitud.tipo_error,
            # Un identificador de modelo caducado es configuracion, no una
            # falla pasajera: ahi no tiene caso ofrecer que reintente.
            'reintentable': solicitud.tipo_error != ErrorProveedorIA.MODELO,
        }

    pregunta = solicitud.preguntas.first()
    if pregunta is None:
        # No deberia ocurrir, pero mas vale contestar algo util que dejar a la
        # pantalla sondeando para siempre.
        return {
            'estado': 'fallida',
            'mensaje': 'La generación terminó sin producir una pregunta.',
            'tipo': '',
            'reintentable': True,
        }
    return {'estado': 'lista', 'pregunta_id': pregunta.id}
