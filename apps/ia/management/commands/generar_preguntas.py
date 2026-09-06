"""
Prueba de humo desde la consola.

Genera un lote y le pasa cada pregunta por el verificador simbolico, para ver
el flujo completo sin necesidad de tener listas las pantallas. No guarda nada
en la base de datos.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.catalogo.verificador import verificar
from apps.ia.errores import ErrorIA
from apps.ia.servicios import generar_preguntas


class Command(BaseCommand):
    help = 'Genera preguntas con el proveedor activo y las verifica. No guarda nada.'

    def add_arguments(self, parser):
        parser.add_argument('--materia', required=True)
        parser.add_argument('--categoria', required=True)
        parser.add_argument('--nivel', type=int, default=3)
        parser.add_argument('--cantidad', type=int, default=1)
        parser.add_argument(
            '--json', action='store_true', help='Muestra la respuesta cruda.'
        )

    def handle(self, *args, **opciones):
        try:
            resultado = generar_preguntas(
                materia=opciones['materia'],
                categoria=opciones['categoria'],
                nivel=opciones['nivel'],
                cantidad=opciones['cantidad'],
            )
        except ErrorIA as error:
            raise CommandError(str(error)) from error

        if opciones['json']:
            crudas = [
                {
                    'enunciado': pregunta.enunciado,
                    'expresion': pregunta.expresion,
                    'opciones': pregunta.opciones,
                    'valores': pregunta.valores,
                    'indice_correcto': pregunta.indice_correcto,
                    'procedimiento': pregunta.procedimiento,
                }
                for pregunta in resultado.preguntas
            ]
            self.stdout.write(json.dumps(crudas, ensure_ascii=False, indent=2))
            return

        self.stdout.write(self.style.SUCCESS(
            f'{len(resultado.preguntas)} preguntas de {resultado.proveedor} '
            f'({resultado.modelo}) · {resultado.tokens_entrada} tokens de '
            f'entrada y {resultado.tokens_salida} de salida'
        ))

        aprobadas = 0
        for numero, pregunta in enumerate(resultado.preguntas, start=1):
            dictamen = verificar(
                pregunta.expresion,
                pregunta.valores_para_verificar,
                pregunta.indice_correcto,
            )
            if dictamen.aprobada:
                aprobadas += 1

            self.stdout.write(f'\n{numero}. {pregunta.enunciado}')
            if pregunta.expresion:
                self.stdout.write(f'   expresión: {pregunta.expresion}')
            for posicion, opcion in enumerate(pregunta.opciones):
                marca = '*' if posicion == pregunta.indice_correcto else ' '
                valor = ''
                if pregunta.valores:
                    valor = f'   [{pregunta.valores[posicion]}]'
                self.stdout.write(
                    f'   {marca} {chr(97 + posicion)}) {opcion}{valor}'
                )
            if pregunta.procedimiento:
                self.stdout.write(f'   procedimiento: {pregunta.procedimiento}')

            if not dictamen.aplica:
                self.stdout.write(self.style.WARNING(
                    '   verificador: no aplica, pasa directo a revisión humana'
                ))
            elif dictamen.aprobada:
                self.stdout.write(self.style.SUCCESS('   verificador: aprobada'))
            else:
                self.stdout.write(self.style.ERROR(
                    f'   verificador: rechazada — {dictamen.motivo}'
                ))

        self.stdout.write(
            f'\nAprobadas por el verificador: {aprobadas} de '
            f'{len(resultado.preguntas)}'
        )
