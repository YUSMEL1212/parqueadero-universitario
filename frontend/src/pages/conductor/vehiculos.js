/**
 * Utilidades de vehículos y placas compartidas por las pantallas del conductor y de
 * portería (registro de invitados).
 *
 * Mismas reglas que el backend (vehiculos/models.py): carro ABC123, moto ABC12D, sin
 * guion ni espacios y en mayúsculas. El backend vuelve a validar; esto solo evita
 * enviar algo que de seguro se va a rechazar.
 */

export const NOMBRE_TIPO = { carro: 'Carro', moto: 'Moto' };

const PATRON_PLACA = {
  carro: /^[A-Z]{3}[0-9]{3}$/,
  moto: /^[A-Z]{3}[0-9]{2}[A-Z]$/,
};

const EJEMPLO_PLACA = { carro: 'ABC-123', moto: 'ABC-12D' };

/** "abc-123" / " xyz 45k " → "ABC123" / "XYZ45K". */
export function normalizarPlaca(placa = '') {
  return placa.replace(/[\s-]/g, '').toUpperCase();
}

/** ABC123 → "ABC 123"; ABC12D → "ABC 12D". */
export function formatearPlaca(placa = '') {
  return placa.length === 6 ? `${placa.slice(0, 3)} ${placa.slice(3)}` : placa;
}

export function ejemploPlaca(tipo) {
  return EJEMPLO_PLACA[tipo] ?? 'ABC-123';
}

/** Mensaje de error para mostrar bajo el campo, o null si la placa es válida para el tipo. */
export function errorDePlaca(placa, tipo) {
  const normalizada = normalizarPlaca(placa);
  if (!normalizada) return 'Escribe la placa del vehículo.';
  if (PATRON_PLACA[tipo]?.test(normalizada)) return null;

  const otro = tipo === 'carro' ? 'moto' : 'carro';
  if (PATRON_PLACA[otro].test(normalizada)) {
    return `Esa parece una placa de ${otro}. Cambia el tipo de vehículo o revisa la placa.`;
  }
  return tipo === 'moto'
    ? 'La placa de una moto tiene 3 letras, 2 números y 1 letra, por ejemplo ABC-12D.'
    : 'La placa de un carro tiene 3 letras y 3 números, por ejemplo ABC-123.';
}
