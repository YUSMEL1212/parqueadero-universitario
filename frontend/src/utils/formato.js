/** Formatos de dinero, fecha, hora y duración compartidos por las pantallas. */

export const formatoPesos = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

export const formatoFecha = new Intl.DateTimeFormat('es-CO', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});

export const formatoHora = new Intl.DateTimeFormat('es-CO', { hour: 'numeric', minute: '2-digit' });

export const formatoDiaCorto = new Intl.DateTimeFormat('es-CO', { day: 'numeric', month: 'short' });

/** 45 → "45 min"; 90 → "1 h 30 min"; 120 → "2 h". */
export function formatearDuracion(minutos) {
  const total = Math.max(0, Number(minutos) || 0);
  const horas = Math.floor(total / 60);
  const resto = total % 60;
  if (!horas) return `${resto} min`;
  return resto ? `${horas} h ${resto} min` : `${horas} h`;
}

export function mismoDia(a, b) {
  return a.toDateString() === b.toDateString();
}

/** Hora de `fecha`; si no es el mismo día que `referencia`, antepone el día ("13 nov, 5:00 p. m."). */
export function horaConDia(fecha, referencia) {
  return mismoDia(fecha, referencia)
    ? formatoHora.format(fecha)
    : `${formatoDiaCorto.format(fecha)}, ${formatoHora.format(fecha)}`;
}
