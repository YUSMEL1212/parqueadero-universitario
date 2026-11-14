/**
 * GET sencillo con estado de carga y error.
 *
 * Devuelve { datos, error, cargando, recargar, setDatos }:
 *   recargar → vuelve a pedir `url`
 *   setDatos → ajusta los datos en memoria (por ejemplo, tras crear o eliminar algo)
 *              sin volver a consultar al servidor
 */
import { useCallback, useEffect, useState } from 'react';

import api from '../api/client';

export default function useConsulta(url) {
  const [estado, setEstado] = useState({ datos: null, error: null, cargando: true });
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    let vigente = true;
    api
      .get(url)
      .then(({ data }) => vigente && setEstado({ datos: data, error: null, cargando: false }))
      .catch((error) => vigente && setEstado({ datos: null, error, cargando: false }));
    return () => {
      vigente = false;
    };
  }, [url, intento]);

  const recargar = useCallback(() => {
    setEstado((e) => ({ ...e, error: null, cargando: true }));
    setIntento((n) => n + 1);
  }, []);

  const setDatos = useCallback((actualizar) => {
    setEstado((e) => ({
      ...e,
      datos: typeof actualizar === 'function' ? actualizar(e.datos) : actualizar,
    }));
  }, []);

  return { ...estado, recargar, setDatos };
}
