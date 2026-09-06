"""
Errores propios del modulo de inteligencia artificial.

Se traducen aqui los fallos de la biblioteca para que el resto del sistema
nunca vea una excepcion de LiteLLM. La distincion entre los tres no es
decorativa: cada uno se le explica distinto al profesor y se atiende distinto.
"""


class ErrorIA(Exception):
    """Base de todos los errores del modulo."""


class ErrorConfiguracionIA(ErrorIA):
    """Falta configuracion o la llave es invalida.

    Es culpa nuestra, no del proveedor: reintentar no arregla nada.
    """


class ErrorProveedorIA(ErrorIA):
    """El proveedor fallo: se agoto la cuota, no responde, o dio un 5xx.

    Alcanzar el limite de solicitudes es una situacion normal de operacion y no
    una excepcion, por eso se distingue si tiene sentido reintentar. Los planes
    de pago tienen limites mas altos, pero tambien los tienen: el mensaje no
    debe dar por hecho que el plan es gratuito.

    El tipo sirve para que la pantalla del profesor diga algo util en lugar de
    un "ocurrio un error" generico. Importa que quede claro cuando el problema
    es del proveedor y no del sistema: si no, el profesor concluye que
    Edumetrica no sirve y deja de usarlo.
    """

    SATURACION = 'saturacion'
    CUOTA = 'cuota'
    CONEXION = 'conexion'
    MODELO = 'modelo'
    DESCONOCIDO = 'desconocido'

    def __init__(self, mensaje, *, reintentable=True, proveedor=None,
                 tipo=DESCONOCIDO, detalle=''):
        super().__init__(mensaje)
        self.reintentable = reintentable
        self.proveedor = proveedor
        self.tipo = tipo
        # El texto crudo del proveedor. Va a la bitacora, nunca a la pantalla:
        # un volcado de JSON hace pensar que el sistema se rompio.
        self.detalle = detalle


class ErrorRespuestaIA(ErrorIA):
    """El proveedor respondio, pero lo que mando no cumple el contrato.

    Significa que hay que ajustar el prompt, no la configuracion.
    """
