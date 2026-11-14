/** Roles del backend (usuarios.models.NombreRol) y la zona de la app de cada uno. */
export const ROLES = {
  CONDUCTOR: 'conductor',
  GUARDA: 'guarda',
  ADMINISTRADOR: 'administrador',
};

const ZONAS = {
  [ROLES.CONDUCTOR]: '/conductor',
  [ROLES.GUARDA]: '/porteria',
  [ROLES.ADMINISTRADOR]: '/admin',
};

export const NOMBRE_ROL = {
  [ROLES.CONDUCTOR]: 'Conductor',
  [ROLES.GUARDA]: 'Portería',
  [ROLES.ADMINISTRADOR]: 'Administrador',
};

/** Ruta de inicio del rol, o null si el rol no tiene zona en la app. */
export function zonaDe(rol) {
  return ZONAS[rol] ?? null;
}
