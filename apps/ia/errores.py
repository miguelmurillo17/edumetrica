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

    En el plan gratuito la cuota agotada es la falla esperada, no la
    excepcional, por eso se distingue si tiene sentido reintentar.
    """

    def __init__(self, mensaje, *, reintentable=True, proveedor=None):
        super().__init__(mensaje)
        self.reintentable = reintentable
        self.proveedor = proveedor


class ErrorRespuestaIA(ErrorIA):
    """El proveedor respondio, pero lo que mando no cumple el contrato.

    Significa que hay que ajustar el prompt, no la configuracion.
    """
