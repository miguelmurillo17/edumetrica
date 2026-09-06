# Edumétrica

Sistema de apoyo para el fortalecimiento de habilidades de nivel medio superior.
Permite a los profesores programar evaluaciones de opcion multiple a sus grupos,
y a los alumnos presentarlas y recibir retroalimentacion inmediata.

Este software forma parte de la tesis para obtener el titulo de Licenciado en
Ingenieria de Software.

## Tecnologias

- Python 3.12 y Django 6
- Django REST Framework para los pocos endpoints JSON que consume el alumno
- Autenticacion por sesion de Django (mismo origen, sin CORS ni tokens)
- Base de datos SQLite en desarrollo, MySQL en produccion
- Vue 3 por CDN dentro de una plantilla de Django para la experiencia del alumno,
  y Chart.js por CDN para las graficas del tablero (no hay paso de compilacion)

## Roles del sistema

- **Administrador:** registra la institucion, profesores, alumnos, grupos,
  materias, categorias, niveles y preguntas. Puede ver el tablero y reportes,
  pero no programa evaluaciones.
- **Profesor:** da de alta preguntas, programa evaluaciones a sus grupos y
  monitorea el avance de sus alumnos.
- **Alumno:** presenta las evaluaciones y recibe retroalimentacion inmediata.

El superusuario no se limita a un rol: entra a cualquier pantalla del sistema y al
iniciar sesion se le ofrecen los tres paneles para que elija desde cual trabajar.

## Aplicaciones del proyecto

Las cuatro aplicaciones propias viven agrupadas dentro del paquete `apps/`, para
separarlas de la configuracion del proyecto (`config/`) y de las carpetas
compartidas `templates/` y `static/`.

- `apps/usuarios`: modelo Persona y autenticacion.
- `apps/catalogo`: instituciones, materias, categorias, niveles, preguntas y opciones.
- `apps/evaluaciones`: grupos, evaluaciones, intentos y respuestas.
- `apps/reportes`: tablero, estadisticas y exportacion de resultados.

En el codigo se importan con la ruta completa, por ejemplo
`from apps.catalogo.models import Pregunta`. La etiqueta interna de cada aplicacion
sigue siendo la corta (`usuarios`, `catalogo`, `evaluaciones`, `reportes`), asi que
comandos como `python manage.py migrate catalogo` no cambian. En cambio
`manage.py test` recibe la ruta del modulo: `python manage.py test apps.evaluaciones`.

## Instalacion

```bash
# Crear y activar el entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Copiar el archivo de variables de entorno y ajustarlo
cp .env.example .env

# Aplicar las migraciones
python manage.py migrate

# Crear el usuario administrador
python manage.py createsuperuser

# Cargar los datos iniciales: los 6 niveles, una institucion y una materia
# de ejemplo, y un usuario de cada rol
python manage.py datos_iniciales

# Arrancar el servidor de desarrollo
python manage.py runserver
```

El panel de administracion queda disponible en http://127.0.0.1:8000/admin/

## Cambiar a MySQL

1. Instalar el conector: `pip install mysqlclient`
2. Crear la base de datos: `CREATE DATABASE edumetrica CHARACTER SET utf8mb4;`
3. En el archivo `.env` poner `DB_ENGINE=mysql` y los datos de conexion.
4. Volver a correr `python manage.py migrate`.

## Generacion de preguntas con IA

El acceso al proveedor pasa por LiteLLM, asi que cambiar de proveedor es editar
el archivo `.env` y no el codigo. El proveedor por omision es Google AI Studio
(Gemini), que hoy se usa en su plan gratuito; tambien estan configurados Groq y
DeepSeek. El plan gratuito es comodo para desarrollar, pero sus solicitudes se
atienden con menor prioridad y el proveedor responde 503 con cierta frecuencia;
pasar a un plan de pago no requiere cambios de codigo, solo del `.env`.

Copia las variables desde `.env.example` y pon la llave del proveedor que vayas
a usar. Para probar desde la consola, sin guardar nada en la base de datos:

```bash
python manage.py generar_preguntas --materia "Matematicas" --categoria "Aritmetica" --nivel 2
```

Se genera una pregunta a la vez. La pregunta generada pasa por el verificador
simbolico antes de mostrarse, y el comando indica si la aprobo o con que motivo
la rechazo.

Los identificadores de modelo caducan: si el proveedor responde que el modelo no
existe, ajusta `AI_MODEL` en el `.env` con el vigente en su consola.

## Comandos utiles

```bash
# Generar migraciones tras cambiar los modelos
python manage.py makemigrations

# Correr las pruebas
python manage.py test

# Correr las pruebas de una sola aplicacion (ruta de modulo, no etiqueta)
python manage.py test apps.evaluaciones

# Cargar datos de demostracion para el tablero: alumnos con edad y sexo,
# dos grupos, dos materias, evaluaciones finalizadas con sus intentos y
# una evaluacion disponible para probar el flujo del alumno
python manage.py datos_demo
```

## Estructura del proyecto

```
config/        configuracion de Django (settings, urls, wsgi, asgi)
apps/          las cuatro aplicaciones propias
templates/     plantillas HTML compartidas
static/        hojas de estilo y demas archivos estaticos
manage.py
```
