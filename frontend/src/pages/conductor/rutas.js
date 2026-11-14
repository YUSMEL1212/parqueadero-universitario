/** Rutas de la zona del conductor que se enlazan desde varias pantallas. */
export const RUTA_INICIO_CONDUCTOR = '/conductor';
/**
 * Pago de mensualidad. Acepta `?tipo=carro|moto` para preseleccionar el tipo. La pasarela
 * vuelve aquí con `?referencia=…` (y Wompi agrega `&id=…`) para mostrar el resultado.
 */
export const RUTA_PAGAR_MENSUALIDAD = '/conductor/pagos';
export const RUTA_VEHICULOS = '/conductor/vehiculos';
export const RUTA_HISTORIAL = '/conductor/historial';
