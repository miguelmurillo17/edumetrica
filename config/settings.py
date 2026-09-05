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
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Modelo de usuario propio. El sistema usa la tabla Persona en lugar de la
# que trae Django por defecto.
AUTH_USER_MODEL = 'usuarios.Persona'

# Rutas de inicio y cierre de sesion.
LOGIN_URL = 'usuarios:inicio_sesion'
LOGIN_REDIRECT_URL = 'usuarios:inicio'
LOGOUT_REDIRECT_URL = 'usuarios:inicio_sesion'


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
