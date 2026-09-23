/*
 * Mensajes en español para la validacion nativa de los campos numericos.
 *
 * El navegador ya sabe impedir que se envie un formulario con un numero
 * fuera de rango (min/max) o que no sea numero, pero el mensaje que muestra
 * sale en el idioma de la interfaz del navegador, no en el de la pagina: el
 * atributo lang="es" del documento no lo cambia. Por eso se le pone el
 * mensaje a mano con setCustomValidity() en cuanto se detecta el motivo.
 */
(function () {
    function mensajeDeValidez(campo) {
        const validez = campo.validity;
        if (validez.valueMissing) {
            return 'Este campo es obligatorio.';
        }
        if (validez.badInput) {
            return 'Escribe un número.';
        }
        if (validez.rangeUnderflow) {
            return 'El valor debe ser mayor o igual a ' + campo.min + '.';
        }
        if (validez.rangeOverflow) {
            return 'El valor debe ser menor o igual a ' + campo.max + '.';
        }
        if (validez.stepMismatch) {
            return 'Ese valor no es válido.';
        }
        return '';
    }

    function revisar(campo) {
        campo.setCustomValidity(mensajeDeValidez(campo));
    }

    document.querySelectorAll('input[type="number"]').forEach(function (campo) {
        revisar(campo);
        campo.addEventListener('input', function () {
            revisar(campo);
        });
    });
})();
