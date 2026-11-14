/**
 * Token del QR dinámico del conductor (GET /api/accesos/qr?vehiculo=<id>).
 *
 * El token vence a los 60 segundos. Cuando se agota `segundos_restantes` se pide uno
 * nuevo solo, sin recargar la página. El vencimiento se calcula con el reloj del
 * teléfono a partir de `segundos_restantes` (no de `vence_en`), para que un reloj
 * desajustado no adelante ni atrase la renovación.
 *
 * Si la pestaña estuvo en segundo plano (el navegador frena los temporizadores), al
 * volver se revisa el vencimiento y se renueva de inmediato si hace falta.
 */
import axios from 'axios';
import { useCallback, useEffect, useState } from 'react';

import api from '../api/client';

/**
 * Devuelve { qr, cargando, error, reintentar }:
 *   qr       → { token, vehiculo, total, venceLocal } o null. `venceLocal` es un
 *              timestamp (ms) del reloj local; `total` son los segundos de vigencia.
 *   cargando → true mientras se pide un token (el primero o una renovación)
 *   error    → el error de axios de la última petición, o null
 */
export default function useQR(vehiculoId) {
  const [qr, setQr] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    if (!vehiculoId) return undefined;

    let vigente = true;
    let temporizador = null;
    let venceLocal = 0;
    let controlador = null;

    async function pedir() {
      clearTimeout(temporizador);
      controlador?.abort();
      controlador = new AbortController();
      setCargando(true);
      try {
        const { data } = await api.get('/api/accesos/qr', {
          params: { vehiculo: vehiculoId },
          signal: controlador.signal,
        });
        if (!vigente) return;
        const segundos = Math.max(1, Number(data.segundos_restantes) || 0);
        venceLocal = Date.now() + segundos * 1000;
        setQr({ token: data.token, vehiculo: data.vehiculo, total: segundos, venceLocal });
        setError(null);
        setCargando(false);
        temporizador = setTimeout(pedir, segundos * 1000);
      } catch (e) {
        if (!vigente || axios.isCancel(e)) return;
        // Un token vencido no sirve para entrar: no se sigue mostrando.
        setQr(null);
        setError(e);
        setCargando(false);
      }
    }

    function alVolverAVer() {
      if (document.visibilityState === 'visible' && venceLocal && Date.now() >= venceLocal) {
        pedir();
      }
    }

    pedir();
    document.addEventListener('visibilitychange', alVolverAVer);

    return () => {
      vigente = false;
      clearTimeout(temporizador);
      controlador?.abort();
      document.removeEventListener('visibilitychange', alVolverAVer);
    };
  }, [vehiculoId, intento]);

  const reintentar = useCallback(() => {
    setError(null);
    setIntento((n) => n + 1);
  }, []);

  return { qr, cargando, error, reintentar };
}
