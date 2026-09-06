"""
Configuracion del proyecto Edumetrica.

Los valores sensibles y los que cambian entre entornos se leen desde
variables de entorno mediante python-decouple. Si no existe un archivo .env
se usan los valores por defecto pensados para desarrollo.
"""

from pathlib import Path

from decouple import config, Csv

# Ruta base del proyecto. Sirve para construir rutas relativas mas abajo.
BASE_DIR = Path(__file__).resolve().parent.parent


# Llave secreta de la aplicacion. En produccion debe venir del archivo .env.
SECRET_KEY = config(
    'SECRET_KEY',
    default='django-insecure-clave-solo-para-desarrollo-cambiala-en-produccion',
)

# Modo depuracion. Debe estar apagado en produccion.
DEBUG = config('DEBUG', default=True, cast=bool)

# Dominios desde los que se permite servir la aplicacion.
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())


# Aplicaciones instaladas.
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Libreria para la interfaz de programacion que usa el alumno.
    'rest_framework',

    # Aplicaciones propias del sistema.
    'apps.usuarios',
    'apps.catalogo',
    'apps.evaluaciones',
    'apps.reportes',
    'apps.ia',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Carpeta de plantillas comunes a todo el proyecto.
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Base de datos.
# Por defecto se usa SQLite para poder trabajar sin instalar nada extra.
# Para usar MySQL basta con definir DB_ENGINE=mysql en el archivo .env
# junto con los datos de conexion.
if config('DB_ENGINE', default='sqlite') == 'mysql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': config('DB_NAME', default='edumetrica'),
            'USER': config('DB_USER', default='root'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='127.0.0.1'),
            'PORT': config('DB_PORT', default='3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Validaciones de contrasena.
# Son las mismas revisiones que trae Django, con los mensajes redactados
# de tu, igual que el resto del sistema (ver apps/usuarios/validadores.py).
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'apps.usuarios.validadores.SimilitudConDatosPersonales',
    },
    {
        'NAME': 'apps.usuarios.validadores.LargoMinimo',
    },
    {
        'NAME': 'apps.usuarios.validadores.ContrasenaComun',
    },
    {
        'NAME': 'apps.usuarios.validadores.SoloNumeros',
    },
]


# Modelo de usuario propio. El sistema usa la tabla Persona en lugar de la
# que trae Django por defecto.
AUTH_USER_MODEL = 'usuarios.Persona'

# Rutas de inicio y cierre de sesion.
LOGIN_URL = 'usuarios:inicio_sesion'
LOGIN_REDIRECT_URL = 'usuarios:inicio'
LOGOUT_REDIRECT_URL = 'usuarios:inicio_sesion'


# Envio de correo, usado para restablecer la contrasena.
# En desarrollo el mensaje se imprime en la consola; en produccion se manda
# por SMTP con los datos del archivo .env.
if config('EMAIL_BACKEND', default='consola') == 'smtp':
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = config('EMAIL_HOST', default='')
    EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
    EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
    EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='no-responder@edumetrica.mx')


# Generacion de preguntas con inteligencia artificial.
# El acceso pasa por LiteLLM, que permite cambiar de proveedor sin tocar codigo.
# Las llaves se leen con config() y no con os.environ: python-decouple lee el
# archivo .env por su cuenta y no llena las variables del sistema, asi que
# os.environ.get() las veria vacias.
AI_PROVIDER = config('AI_PROVIDER', default='gemini')

# Vacio significa usar el modelo por omision del proveedor activo.
AI_MODEL = config('AI_MODEL', default='') or None

AI_TEMPERATURE = config('AI_TEMPERATURE', default=0.7, cast=float)
AI_MAX_TOKENS = config('AI_MAX_TOKENS', default=4096, cast=int)
# La generacion corre en un hilo aparte, asi que el corte de treinta segundos
# de un servidor de produccion ya no manda; lo que manda es la paciencia del
# profesor mirando la pantalla de espera. Con un reintento, el peor caso son
# dos intentos de treinta segundos.
AI_TIMEOUT = config('AI_TIMEOUT', default=30, cast=int)
AI_MAX_RETRIES = config('AI_MAX_RETRIES', default=1, cast=int)

# Cuantas generaciones puede pedir un profesor por hora. La cuota es de la
# institucion y no de cada usuario: sin este tope, un profesor la agota para
# todos. Se cuentan todas las solicitudes, salgan bien o mal, porque las dos
# tocaron al proveedor. Es un ajuste y no un numero escrito en el codigo para
# poder subirlo el dia de la demostracion.
AI_LIMITE_POR_HORA = config('AI_LIMITE_POR_HORA', default=20, cast=int)

# Se leen todas, pero solo se exige la del proveedor activo y hasta el momento
# de la llamada, para que el sistema arranque sin ninguna configurada.
AI_LLAVES = {
    'gemini': config('GEMINI_API_KEY', default=''),
    'groq': config('GROQ_API_KEY', default=''),
    'deepseek': config('DEEPSEEK_API_KEY', default=''),
}


# Bitacora. Interesa sobre todo la del modulo de inteligencia artificial:
# deja constancia de cada llamada, el modelo usado y los tokens consumidos,
# que son los datos del capitulo de resultados.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'consola': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'apps.ia': {
            'handlers': ['consola'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}


# Idioma y zona horaria.
LANGUAGE_CODE = 'es-mx'

TIME_ZONE = 'America/Mexico_City'

USE_I18N = True

USE_TZ = True


# Archivos estaticos (hojas de estilo, javascript).
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Archivos multimedia que suben los usuarios (imagenes de preguntas y opciones).
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'


# Tipo de llave primaria por defecto.
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Configuracion de Django REST Framework.
# El alumno consume la interfaz de programacion usando la misma sesion del
# navegador, por eso se autentica por sesion y no con tokens.
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}
