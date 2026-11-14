/**
 * Convierte un error de axios/DRF en mensajes para mostrar al usuario.
 *
 * Devuelve { general, campos }:
 *   general → texto para el aviso de la parte superior del formulario (o null)
 *   campos  → { nombreCampo: 'mensaje' } con los errores de validación de DRF
 */
export function leerError(error, mensajes = {}) {
  if (!error?.response) {
    if (error?.code === 'ECONNABORTED') {
      return { general: 'El servidor tardó demasiado en responder. Intenta de nuevo.', campos: {} };
    }
    return {
      general: 'No se pudo conectar con el servidor. Revisa tu conexión e intenta de nuevo.',
      campos: {},
    };
  }

  const { status, data } = error.response;
  if (mensajes[status]) return { general: mensajes[status], campos: {} };

  if (status >= 500) {
    return { general: 'Ocurrió un error en el servidor. Intenta de nuevo en unos minutos.', campos: {} };
  }

  if (data && typeof data === 'object' && !Array.isArray(data)) {
    const campos = {};
    let general = null;
    for (const [clave, valor] of Object.entries(data)) {
      const texto = Array.isArray(valor) ? valor.join(' ') : String(valor);
      if (clave === 'detail' || clave === 'non_field_errors') general = texto;
      else campos[clave] = texto;
    }
    if (!general && Object.keys(campos).length) general = 'Revisa los campos marcados.';
    return { general, campos };
  }

  return { general: 'No se pudo completar la solicitud.', campos: {} };
}
