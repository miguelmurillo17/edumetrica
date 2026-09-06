"""
Catalogo de proveedores de inteligencia artificial.

Cada uno declara su modelo por omision, el nombre de su variable de entorno y
donde se consigue la llave. Cambiar de proveedor es cambiar AI_PROVIDER en el
archivo .env; este catalogo es lo unico que hay que tocar para agregar otro.
"""

from dataclasses import dataclass

from .errores import ErrorConfiguracionIA


@dataclass(frozen=True)
class Proveedor:
    clave: str
    etiqueta: str
    # El identificador incluye el prefijo que LiteLLM necesita para saber a
    # quien llamar. El prefijo no cambia aunque el modelo si.
    modelo_por_omision: str
    variable_llave: str
    acepta_modo_json: bool
    consola: str


PROVEEDORES = {
    'gemini': Proveedor(
        clave='gemini',
        etiqueta='Google AI Studio (Gemini)',
        modelo_por_omision='gemini/gemini-3.6-flash',
        variable_llave='GEMINI_API_KEY',
        acepta_modo_json=True,
        consola='https://aistudio.google.com/app/apikey',
    ),
    'groq': Proveedor(
        clave='groq',
        etiqueta='Groq',
        modelo_por_omision='groq/openai/gpt-oss-120b',
        variable_llave='GROQ_API_KEY',
        acepta_modo_json=True,
        consola='https://console.groq.com/keys',
    ),
    'deepseek': Proveedor(
        clave='deepseek',
        etiqueta='DeepSeek',
        modelo_por_omision='deepseek/deepseek-chat',
        variable_llave='DEEPSEEK_API_KEY',
        acepta_modo_json=True,
        consola='https://platform.deepseek.com',
    ),
}


def obtener_proveedor(clave):
    """Regresa la configuracion del proveedor, o explica cuales son validos."""
    try:
        return PROVEEDORES[clave]
    except KeyError:
        validos = ', '.join(sorted(PROVEEDORES))
        raise ErrorConfiguracionIA(
            f"AI_PROVIDER='{clave}' no es un proveedor válido. "
            f'Las opciones son: {validos}.'
        ) from None
