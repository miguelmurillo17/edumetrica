/*
 * Buscador con resaltado para los listados del sistema. Trabaja en el
 * navegador porque busca en todo el renglon a la vez y pinta las
 * coincidencias, algo que no tiene sentido resolver con una recarga.
 *
 * Se activa solo si la pantalla trae un input.buscador-tabla (lo agrega
 * templates/incluye/buscador_tabla.html); si no hay ninguno no hace nada.
 * Cada buscador filtra el contenedor que apunta su data-tabla, sobre los
 * elementos que calcen con su data-renglon (por omision, filas de tabla).
 */
(function () {
    // Quita acentos y pasa a minusculas, para que "algebra" encuentre
    // "Álgebra" y no dependa de mayusculas.
    function normalizar(texto) {
        return texto
            .normalize('NFD')
            .replace(/[̀-ͯ]/g, '')
            .toLowerCase();
    }

    // Cada letra del termino se vuelve un grupo que acepta sus variantes con
    // acento, para poder resaltar aunque el texto del renglon si los lleve.
    const equivalentes = {
        a: '[aáàäâã]', e: '[eéèëê]', i: '[iíìïî]',
        o: '[oóòöô]', u: '[uúùüû]', n: '[nñ]', c: '[cç]',
    };

    function aExpresion(termino) {
        const escapado = termino.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        let patron = '';
        for (const letra of escapado) {
            patron += equivalentes[letra] || letra;
        }
        return new RegExp(patron, 'gi');
    }

    function resaltarRenglon(renglon, expresiones) {
        const paseador = document.createTreeWalker(renglon, NodeFilter.SHOW_TEXT);
        const nodos = [];
        while (paseador.nextNode()) {
            nodos.push(paseador.currentNode);
        }
        nodos.forEach(function (nodo) {
            let coincide = false;
            for (const expresion of expresiones) {
                expresion.lastIndex = 0;
                if (expresion.test(nodo.nodeValue)) {
                    coincide = true;
                    break;
                }
            }
            if (!coincide) {
                return;
            }
            let html = nodo.nodeValue.replace(/[&<>]/g, function (caracter) {
                return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[caracter];
            });
            for (const expresion of expresiones) {
                html = html.replace(expresion, '<mark class="resaltado">$&</mark>');
            }
            const envoltura = document.createElement('span');
            envoltura.innerHTML = html;
            nodo.replaceWith(envoltura);
        });
    }

    function activar(buscador) {
        const id = buscador.dataset.tabla;
        const contenedor = document.getElementById(id);
        if (!contenedor) {
            return;
        }
        const selectorRenglon = buscador.dataset.renglon || 'tbody tr';
        const renglones = Array.from(contenedor.querySelectorAll(selectorRenglon));
        const aviso = document.querySelector('.aviso-sin-resultados[data-tabla="' + id + '"]');
        const conteo = document.querySelector('.conteo-tabla[data-tabla="' + id + '"]');
        const total = renglones.length;

        renglones.forEach(function (renglon) {
            renglon.dataset.original = renglon.innerHTML;
            renglon.dataset.texto = normalizar(renglon.textContent);
        });

        function filtrar() {
            const consulta = buscador.value.trim();
            const terminos = normalizar(consulta).split(/\s+/).filter(Boolean);
            let visibles = 0;

            renglones.forEach(function (renglon) {
                // Se parte del contenido original: limpia el resaltado anterior.
                renglon.innerHTML = renglon.dataset.original;

                const pasa = terminos.every(function (termino) {
                    return renglon.dataset.texto.indexOf(termino) !== -1;
                });
                renglon.hidden = !pasa;
                if (pasa) {
                    visibles += 1;
                }
            });

            if (terminos.length) {
                const expresiones = terminos.map(aExpresion);
                renglones.forEach(function (renglon) {
                    if (!renglon.hidden) {
                        resaltarRenglon(renglon, expresiones);
                    }
                });
                if (conteo) {
                    conteo.textContent = visibles + ' de ' + total;
                }
            } else if (conteo) {
                conteo.textContent = '';
            }

            if (aviso) {
                aviso.hidden = visibles !== 0 || total === 0;
            }
        }

        buscador.addEventListener('input', filtrar);
    }

    document.querySelectorAll('input.buscador-tabla').forEach(activar);
})();
