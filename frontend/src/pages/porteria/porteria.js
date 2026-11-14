/**
 * Utilidades de las pantallas del guarda: mensajes de error de la API de portería,
 * código de salida de invitados y nombres para mostrar.
 *
 * El backend (accesos/porteria.py) responde los errores de negocio con
 * `{ detail, codigo, ... }`; aquí se elige el título según `codigo` y se usa `detail`
 * como explicación, salvo en los casos donde conviene decirle al guarda qué hacer.
 */
import { leerError } from '../../api/errores';
import { formatearPlaca } from '../conductor/vehiculos';

export const MODOS = { ENTRADA: 'entrada', SALIDA: 'salida' };

/** Medios de pago que recibe el guarda → valor de `metodo_pago` en el backend. */
export const MEDIOS_PAGO = [
  { valor: 'efectivo', texto: 'Efectivo' },
  { valor: 'tarjeta', texto: 'Datáfono' },
];

export const NOMBRE_MEDIO = { efectivo: 'Efectivo', tarjeta: 'Datáfono', pse: 'PSE' };

export const NOMBRE_CONCEPTO = {
  hasta_2h: 'Hasta 2 horas',
  mas_2h: 'Más de 2 horas',
};

// Mismo alfabeto que accesos/porteria.py: sin 0/O ni 1/I.
const PATRON_CODIGO = /^[A-HJ-NP-Z2-9]{8}$/;

/** " k7mp 2qxa " → "K7MP2QXA". */
export function normalizarCodigo(texto = '') {
  return texto.replace(/\s/g, '').toUpperCase();
}

/** ¿El texto es un código de salida de invitado (y no el token de un QR)? */
export function esCodigoSalida(texto) {
  return PATRON_CODIGO.test(normalizarCodigo(texto));
}

/** "K7MP2QXA" → ["K7MP", "2QXA"], para mostrarlo en dos grupos sin meter espacios. */
export function gruposCodigo(codigo = '') {
  return codigo.length === 8 ? [codigo.slice(0, 4), codigo.slice(4)] : [codigo];
}

const ERRORES = {
  qr_vencido: {
    titulo: 'Código QR vencido',
    texto: 'El QR dura 60 segundos. Pide al conductor que muestre el código actualizado en su app y vuelve a escanear.',
  },
  qr_alterado: {
    titulo: 'Código QR inválido',
    texto: 'El código no es válido o fue modificado. Pide al conductor que abra de nuevo su QR en la app.',
  },
  qr_ilegible: {
    titulo: 'Código QR inválido',
    texto: 'No se reconoce como un código de la app del parqueadero.',
  },
  vehiculo_adentro: {
    titulo: 'Vehículo ya adentro',
    texto: (data) =>
      data.placa_adentro
        ? `El conductor ya tiene el vehículo ${formatearPlaca(data.placa_adentro)} dentro del parqueadero. Debe salir antes de ingresar otro.`
        : data.detail,
  },
  sin_ticket_abierto: {
    titulo: 'Sin ingreso abierto',
    texto: (data) => `${data.detail} No hay nada que cobrar; revisa que el modo sea el correcto.`,
  },
  vehiculo_no_existe: { titulo: 'Vehículo no registrado' },
  usuario_inactivo: { titulo: 'Cuenta desactivada' },
  vehiculo_inactivo: { titulo: 'Vehículo desactivado' },
  placa_registrada: { titulo: 'Placa de un conductor registrado' },
  ticket_cerrado: {
    titulo: 'Salida ya registrada',
    texto: 'Este ticket ya fue cerrado; la salida se había registrado antes.',
  },
  ticket_no_existe: { titulo: 'Ticket no encontrado' },
  sin_tarifa_vigente: {
    titulo: 'Sin tarifa vigente',
    texto: (data) => `${data.detail} Avisa al administrador para que configure la tarifa.`,
  },
};

/**
 * Error de la API de portería → `{ titulo, texto, codigo, campos }` para mostrar.
 * `campos` trae los errores de validación de DRF por campo (p. ej. `placa`).
 */
export function errorPorteria(error) {
  const data = error?.response?.data;
  const caso = data && typeof data === 'object' ? ERRORES[data.codigo] : null;
  if (caso) {
    const texto = typeof caso.texto === 'function' ? caso.texto(data) : (caso.texto ?? data.detail);
    return { titulo: caso.titulo, texto, codigo: data.codigo, campos: {} };
  }

  const status = error?.response?.status;
  if (status === 403) {
    return {
      titulo: 'Sin permiso',
      texto: 'Tu usuario no tiene permiso de portería. Cierra sesión e ingresa con una cuenta de guarda.',
      codigo: null,
      campos: {},
    };
  }
  const { general, campos } = leerError(error);
  return { titulo: 'No se pudo completar', texto: general, codigo: null, campos };
}
