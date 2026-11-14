/**
 * Utilidades de las pantallas del administrador: nombres para mostrar, fechas en
 * formato de la API y mensajes de error.
 */
import { leerError } from '../../api/errores';
import { ROLES } from '../../auth/roles';

export const TIPOS_VEHICULO = ['carro', 'moto'];
export const CONCEPTOS_TARIFA = ['hasta_2h', 'mas_2h', 'mensualidad'];

export const NOMBRE_CONCEPTO = {
  hasta_2h: 'Hasta 2 horas',
  mas_2h: 'Más de 2 horas',
  mensualidad: 'Mensualidad',
};

export const OPCIONES_ROL = [
  { valor: ROLES.CONDUCTOR, texto: 'Conductor' },
  { valor: ROLES.GUARDA, texto: 'Guarda' },
  { valor: ROLES.ADMINISTRADOR, texto: 'Administrador' },
];

export const NOMBRE_ESTADO_BAHIA = {
  libre: 'Libre',
  ocupada: 'Ocupada',
  fuera_servicio: 'Fuera de servicio',
};

export const NOMBRE_ESTADO_SENSOR = {
  ok: 'En línea',
  desconectado: 'Desconectado',
  falla: 'Falla',
};

const dos = (n) => String(n).padStart(2, '0');

/** Date → "2026-11-14" con la fecha local (no UTC). */
export function fechaISO(fecha) {
  return `${fecha.getFullYear()}-${dos(fecha.getMonth() + 1)}-${dos(fecha.getDate())}`;
}

/** "2026-11-14" → Date local a medianoche. */
export function fechaDeISO(texto) {
  const [anio, mes, dia] = texto.split('-').map(Number);
  return new Date(anio, mes - 1, dia);
}

/** Fecha `dias` antes (o después, si es negativo) de `fecha`. */
export function sumarDias(fecha, dias) {
  const copia = new Date(fecha);
  copia.setDate(copia.getDate() + dias);
  return copia;
}

/** 12 → "hace 12 s"; 300 → "hace 5 min"; 7200 → "hace 2 h"; 172800 → "hace 2 días". */
export function haceTiempo(segundos) {
  const s = Math.max(0, Math.round(segundos));
  if (s < 60) return `hace ${s} s`;
  const min = Math.floor(s / 60);
  if (min < 60) return `hace ${min} min`;
  const horas = Math.floor(min / 60);
  if (horas < 24) return `hace ${horas} h`;
  const dias = Math.floor(horas / 24);
  return `hace ${dias} ${dias === 1 ? 'día' : 'días'}`;
}

const SIN_PERMISO =
  'Tu usuario no tiene permiso de administrador. Cierra sesión e ingresa con una cuenta de administrador.';

/**
 * Error de axios/DRF → una sola frase para mostrar. Prefiere `detail`; si DRF devolvió
 * errores por campo, toma el primero.
 */
export function mensajeError(error) {
  const { general, campos } = leerError(error, { 403: SIN_PERMISO });
  const primerCampo = Object.values(campos)[0];
  if (general && general !== 'Revisa los campos marcados.') return general;
  return primerCampo ?? general ?? 'No se pudo completar la solicitud.';
}
