/**
 * Cupos libres en vivo.
 *
 * 1. Carga inicial con GET /api/iot/cupos.
 * 2. Se conecta a ws/cupos y aplica cada mensaje que llega.
 * 3. Si el WebSocket se cae, reintenta con espera creciente (1 s, 2 s, 4 s… hasta 15 s)
 *    y, mientras no esté conectado, consulta por HTTP cada 15 segundos.
 *
 * Ambos canales envían el mismo mensaje:
 *   { tipo: 'cupos', libres: { carro: 5, moto: 3 }, actualizado_en: '...' }
 * Se descarta un mensaje más viejo que el último aplicado (la respuesta HTTP inicial
 * puede llegar después del primer mensaje del WebSocket).
 */
import { useEffect, useState } from 'react';

import api, { BASE_URL } from '../api/client';

const WS_URL = `${BASE_URL.replace(/^http/, 'ws')}/ws/cupos`;
const SONDEO_MS = 15000;
const ESPERA_MAXIMA_MS = 15000;

/**
 * Devuelve { libres, enVivo, error }:
 *   libres → { carro, moto } o null mientras no haya llegado ningún dato
 *   enVivo → true si el WebSocket está conectado
 *   error  → true si la última consulta HTTP falló (solo importa si libres es null)
 */
export default function useCupos() {
  const [libres, setLibres] = useState(null);
  const [enVivo, setEnVivo] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cerrado = false;
    let socket = null;
    let temporizadorReconexion = null;
    let temporizadorSondeo = null;
    let intentos = 0;
    let ultimaMarca = 0;

    function aplicar(mensaje) {
      if (cerrado || mensaje?.tipo !== 'cupos' || !mensaje.libres) return;
      const marca = Date.parse(mensaje.actualizado_en) || 0;
      if (marca < ultimaMarca) return;
      ultimaMarca = marca;
      setLibres(mensaje.libres);
      setError(false);
    }

    function consultar() {
      api
        .get('/api/iot/cupos')
        .then(({ data }) => aplicar(data))
        .catch(() => !cerrado && setError(true));
    }

    function iniciarSondeo() {
      if (!temporizadorSondeo) temporizadorSondeo = setInterval(consultar, SONDEO_MS);
    }

    function detenerSondeo() {
      clearInterval(temporizadorSondeo);
      temporizadorSondeo = null;
    }

    function conectar() {
      temporizadorReconexion = null;
      socket = new WebSocket(WS_URL);
      socket.onopen = () => {
        intentos = 0;
        setEnVivo(true);
        detenerSondeo();
      };
      socket.onmessage = (evento) => {
        try {
          aplicar(JSON.parse(evento.data));
        } catch {
          // Mensaje que no es JSON: se ignora.
        }
      };
      socket.onclose = () => {
        if (cerrado) return;
        setEnVivo(false);
        iniciarSondeo();
        const espera = Math.min(ESPERA_MAXIMA_MS, 1000 * 2 ** intentos);
        intentos += 1;
        temporizadorReconexion = setTimeout(conectar, espera);
      };
      // Después de un error siempre llega onclose, que se encarga de reconectar.
    }

    // Al recuperar la red no se espera a que venza la espera de reconexión.
    function alVolverLaRed() {
      if (temporizadorReconexion) {
        clearTimeout(temporizadorReconexion);
        intentos = 0;
        consultar();
        conectar();
      }
    }

    consultar();
    conectar();
    window.addEventListener('online', alVolverLaRed);

    return () => {
      cerrado = true;
      window.removeEventListener('online', alVolverLaRed);
      clearTimeout(temporizadorReconexion);
      detenerSondeo();
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
    };
  }, []);

  return { libres, enVivo, error };
}
