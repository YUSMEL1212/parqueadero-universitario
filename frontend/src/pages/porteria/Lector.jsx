/**
 * Lector QR (/porteria): el guarda elige Entrada o Salida y escanea el QR del conductor
 * con la cámara, o pega el token a mano (en un computador sin cámara es la única forma).
 *
 *   Entrada → POST /api/accesos/entrada y confirmación con placa y hora.
 *   Salida  → POST /api/accesos/salida y pasa a Cobros con la liquidación. En modo
 *             salida el campo manual también acepta el código de 8 caracteres del
 *             ticket de un invitado.
 *
 * Al volver de Cobros con la salida confirmada, muestra el mensaje de éxito que llega
 * en el `state` de la navegación.
 */
import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useOutletContext } from 'react-router-dom';

import api from '../../api/client';
import Campo from '../../components/Campo';
import useEscanerQR from '../../hooks/useEscanerQR';
import { formatoHora, formatoPesos } from '../../utils/formato';
import { NOMBRE_TIPO, formatearPlaca } from '../conductor/vehiculos';
import { MODOS, NOMBRE_MEDIO, errorPorteria, esCodigoSalida, normalizarCodigo } from './porteria';
import { RUTA_COBROS } from './rutas';

const ID_CAMARA = 'lector-qr-camara';

// Un token ya procesado no se vuelve a enviar si sigue frente a la cámara (vence a los 60 s).
const MS_IGNORAR_REPETIDO = 60_000;

const TEXTOS = {
  [MODOS.ENTRADA]: {
    subtitulo: 'Escanea el QR del conductor para registrar su entrada.',
    etiqueta: 'Token del QR',
    ayuda: 'Pega aquí el texto del QR si no hay cámara.',
    boton: 'Registrar entrada',
    enviando: 'Registrando…',
  },
  [MODOS.SALIDA]: {
    subtitulo: 'Escanea el QR del conductor para liquidar su salida.',
    etiqueta: 'Token del QR o código de invitado',
    ayuda: 'Pega el texto del QR, o escribe el código de 8 caracteres del ticket de un invitado.',
    boton: 'Liquidar salida',
    enviando: 'Liquidando…',
  },
};

function SelectorModo({ valor, onCambiar, disabled }) {
  return (
    <fieldset className="segmentos segmentos--grande" disabled={disabled}>
      <legend className="sr-only">Qué registrar</legend>
      <div className="segmentos__opciones">
        {[
          { modo: MODOS.ENTRADA, texto: 'Entrada' },
          { modo: MODOS.SALIDA, texto: 'Salida' },
        ].map(({ modo, texto }) => (
          <label key={modo} className="segmentos__opcion">
            <input
              type="radio"
              name="modo"
              value={modo}
              checked={valor === modo}
              onChange={() => onCambiar(modo)}
            />
            <span>{texto}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function Escaner({ procesando, onLectura }) {
  const { fase, error, reintentar } = useEscanerQR(ID_CAMARA, onLectura);

  return (
    <section className="escaner" aria-label="Cámara">
      <div className="escaner__marco">
        <div id={ID_CAMARA} className="escaner__camara" />
        {fase === 'iniciando' && (
          <div className="escaner__capa" role="status">
            <span className="spinner" aria-hidden="true" />
            <span>Abriendo la cámara…</span>
          </div>
        )}
        {fase === 'error' && (
          <div className="escaner__capa">
            <p className="escaner__mensaje">{error}</p>
            <button type="button" className="boton boton--secundario" onClick={reintentar}>
              Reintentar cámara
            </button>
          </div>
        )}
        {fase === 'activo' && procesando && (
          <div className="escaner__capa escaner__capa--velo" role="status">
            <span className="spinner" aria-hidden="true" />
            <span>Validando…</span>
          </div>
        )}
      </div>
      {fase === 'activo' && <p className="escaner__ayuda texto-suave">Ubica el QR dentro del recuadro.</p>}
    </section>
  );
}

function Resultado({ resultado }) {
  if (!resultado) return null;

  if (resultado.tipo === 'error') {
    return (
      <div className="resultado resultado--error" role="alert">
        <p className="resultado__titulo">{resultado.titulo}</p>
        {resultado.texto && <p>{resultado.texto}</p>}
      </div>
    );
  }

  if (resultado.tipo === 'entrada') {
    const { ticket } = resultado;
    return (
      <div className="resultado resultado--exito" role="status">
        <p className="resultado__titulo">Entrada registrada</p>
        <div className="resultado__vehiculo">
          <span className="placa">{formatearPlaca(ticket.placa)}</span>
          <span>
            {NOMBRE_TIPO[ticket.tipo_vehiculo] ?? ticket.tipo_vehiculo}
            {ticket.conductor && ` · ${ticket.conductor}`}
          </span>
        </div>
        <p>
          Hora de entrada:{' '}
          <strong>
            <time dateTime={ticket.hora_entrada}>{formatoHora.format(new Date(ticket.hora_entrada))}</time>
          </strong>
        </p>
      </div>
    );
  }

  // Salida confirmada en Cobros.
  const { recibo, valorMostrado } = resultado;
  const cobrado = recibo.valor_cobrado ?? 0;
  return (
    <div className="resultado resultado--exito" role="status">
      <p className="resultado__titulo">Salida registrada</p>
      <div className="resultado__vehiculo">
        <span className="placa">{formatearPlaca(recibo.placa)}</span>
        <span>{NOMBRE_TIPO[recibo.tipo_vehiculo] ?? recibo.tipo_vehiculo}</span>
      </div>
      <p>
        {cobrado > 0 ? (
          <>
            Pago de <strong>{formatoPesos.format(cobrado)}</strong> en{' '}
            {(NOMBRE_MEDIO[recibo.metodo_pago] ?? recibo.metodo_pago ?? 'efectivo').toLowerCase()}.
          </>
        ) : (
          'Sin cobro: mensualidad activa.'
        )}{' '}
        Puede abrir la talanquera.
      </p>
      {valorMostrado != null && valorMostrado !== cobrado && (
        <p className="resultado__nota">
          El valor cambió de {formatoPesos.format(valorMostrado)} a {formatoPesos.format(cobrado)} porque
          se recalculó al confirmar.
        </p>
      )}
    </div>
  );
}

export default function Lector() {
  const { modo, setModo, setLiquidacion } = useOutletContext();
  const navigate = useNavigate();
  const location = useLocation();

  const [resultado, setResultado] = useState(() =>
    location.state?.salida
      ? { tipo: 'salida', recibo: location.state.salida, valorMostrado: location.state.valorMostrado }
      : null,
  );
  const [manual, setManual] = useState('');
  const [procesando, setProcesando] = useState(false);
  const ocupado = useRef(false);
  const ultimaLectura = useRef({ texto: null, en: 0 });

  // El mensaje de la salida se muestra una vez: se limpia el state para que no
  // reaparezca al recargar.
  useEffect(() => {
    if (location.state) navigate(location.pathname, { replace: true, state: null });
  }, [location, navigate]);

  function cambiarModo(nuevo) {
    setModo(nuevo);
    setResultado(null);
  }

  async function procesar(texto) {
    const valor = texto.trim();
    if (!valor || ocupado.current) return false;
    ocupado.current = true;
    setProcesando(true);
    setResultado(null);

    try {
      if (modo === MODOS.ENTRADA) {
        const { data } = await api.post('/api/accesos/entrada', { token: valor });
        setResultado({ tipo: 'entrada', ticket: data });
        return true;
      }
      const cuerpo = esCodigoSalida(valor) ? { codigo_salida: normalizarCodigo(valor) } : { token: valor };
      const { data } = await api.post('/api/accesos/salida', cuerpo);
      setLiquidacion(data);
      navigate(RUTA_COBROS);
      return true;
    } catch (e) {
      const { titulo, texto: detalle, campos } = errorPorteria(e);
      setResultado({
        tipo: 'error',
        titulo,
        texto: campos.token ?? campos.codigo_salida ?? detalle,
      });
      return false;
    } finally {
      ocupado.current = false;
      setProcesando(false);
    }
  }

  function alLeerQR(texto) {
    const ahora = Date.now();
    const { texto: anterior, en } = ultimaLectura.current;
    if (texto === anterior && ahora - en < MS_IGNORAR_REPETIDO) return;
    if (ocupado.current) return;
    ultimaLectura.current = { texto, en: ahora };
    navigator.vibrate?.(80);
    procesar(texto);
  }

  async function enviarManual(evento) {
    evento.preventDefault();
    if (!manual.trim()) {
      setResultado({ tipo: 'error', titulo: 'Falta el código', texto: 'Pega el token del QR antes de enviar.' });
      return;
    }
    if (await procesar(manual)) setManual('');
  }

  const textos = TEXTOS[modo];

  return (
    <div className="porteria">
      <header className="saludo">
        <h1 className="saludo__titulo">Lector QR</h1>
        <p className="texto-suave">{textos.subtitulo}</p>
      </header>

      <SelectorModo valor={modo} onCambiar={cambiarModo} disabled={procesando} />

      <Escaner procesando={procesando} onLectura={alLeerQR} />

      <Resultado resultado={resultado} />

      <form className="tarjeta" onSubmit={enviarManual} noValidate aria-labelledby="titulo-manual">
        <h2 id="titulo-manual" className="bloque__titulo">
          Ingreso manual
        </h2>
        <Campo
          etiqueta={textos.etiqueta}
          name="token"
          value={manual}
          onChange={(e) => setManual(e.target.value)}
          ayuda={textos.ayuda}
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          readOnly={procesando}
        />
        <button type="submit" className="boton boton--primario boton--bloque" disabled={procesando}>
          {procesando ? textos.enviando : textos.boton}
        </button>
      </form>
    </div>
  );
}
