/**
 * Cámara + lectura de QR con html5-qrcode sobre el elemento con id `idElemento`.
 *
 * Devuelve { fase, error, reintentar }:
 *   fase  → 'iniciando' | 'activo' | 'error'
 *   error → mensaje para el guarda cuando la cámara no se pudo abrir
 *
 * `onLectura(texto)` se llama con cada QR leído (puede repetirse mientras el código
 * siga frente a la cámara; quien lo usa decide qué lecturas ignorar).
 *
 * Arrancar y detener la cámara es asíncrono, y en desarrollo StrictMode monta el efecto
 * dos veces seguidas. Para que dos instancias no peleen por la cámara ni por el mismo
 * elemento, todas las operaciones van en una sola cola.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Html5Qrcode, Html5QrcodeSupportedFormats } from 'html5-qrcode';

let cola = Promise.resolve();

function enCola(tarea) {
  cola = cola.then(tarea).catch(() => {});
  return cola;
}

/** Recuadro guía: un cuadrado del 70 % del lado menor del video. */
function recuadro(ancho, alto) {
  const lado = Math.max(120, Math.floor(Math.min(ancho, alto) * 0.7));
  return { width: lado, height: lado };
}

function mensajeCamara(error) {
  const texto = `${error?.name ?? ''} ${error?.message ?? ''} ${typeof error === 'string' ? error : ''}`;
  if (/NotAllowed|Permission|denied/i.test(texto)) {
    return 'El navegador no dio permiso para usar la cámara. Actívalo en la configuración del sitio o escribe el código en el campo de abajo.';
  }
  if (/NotFound|DevicesNotFound|not found|no camera/i.test(texto)) {
    return 'No se encontró una cámara en este equipo. Pega el token del QR en el campo de abajo.';
  }
  if (/NotReadable|TrackStart|in use/i.test(texto)) {
    return 'La cámara está en uso por otra aplicación. Ciérrala y vuelve a intentar.';
  }
  if (/not supported|insecure|secure context/i.test(texto) || !window.isSecureContext) {
    return 'Este navegador no permite usar la cámara aquí (se necesita HTTPS). Escribe el código en el campo de abajo.';
  }
  return 'No se pudo abrir la cámara. Escribe el código en el campo de abajo o vuelve a intentar.';
}

export default function useEscanerQR(idElemento, onLectura) {
  const [estado, setEstado] = useState({ fase: 'iniciando', error: null });
  const [intento, setIntento] = useState(0);
  const callback = useRef(onLectura);

  useLayoutEffect(() => {
    callback.current = onLectura;
  });

  useEffect(() => {
    let cancelado = false;
    let escaner = null;

    enCola(async () => {
      if (cancelado) return;
      try {
        escaner = new Html5Qrcode(idElemento, {
          verbose: false,
          formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
        });
        await escaner.start(
          { facingMode: 'environment' },
          { fps: 10, qrbox: recuadro },
          (texto) => callback.current?.(texto),
          () => {}, // Cuadro sin QR: no es un error.
        );
        if (!cancelado) setEstado({ fase: 'activo', error: null });
      } catch (error) {
        if (!cancelado) setEstado({ fase: 'error', error: mensajeCamara(error) });
      }
    });

    return () => {
      cancelado = true;
      enCola(async () => {
        if (!escaner) return;
        try {
          if (escaner.isScanning) await escaner.stop();
          escaner.clear();
        } catch {
          // Ya estaba detenido.
        }
      });
    };
  }, [idElemento, intento]);

  const reintentar = useCallback(() => {
    setEstado({ fase: 'iniciando', error: null });
    setIntento((n) => n + 1);
  }, []);

  return { ...estado, reintentar };
}
