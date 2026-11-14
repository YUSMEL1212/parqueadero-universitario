/**
 * Cobros (/porteria/cobros): liquidación de la salida en curso y registro del pago.
 *
 * La liquidación llega del Lector (POST /api/accesos/salida) por el contexto de
 * LayoutPorteria. Sin liquidación pendiente, la pantalla permite buscar la salida de
 * un invitado con el código de su ticket.
 *
 * "Registrar pago y abrir talanquera" llama a POST /api/accesos/salida/confirmar. El
 * backend recalcula el cobro en ese momento, así que el recibo puede diferir de lo
 * mostrado si entre tanto se cruzaron los 120 minutos; el Lector avisa si pasa.
 */
import { useState } from 'react';
import { Link, useNavigate, useOutletContext } from 'react-router-dom';

import api from '../../api/client';
import Campo from '../../components/Campo';
import { formatearDuracion, formatoPesos, horaConDia } from '../../utils/formato';
import { NOMBRE_TIPO, formatearPlaca } from '../conductor/vehiculos';
import {
  MEDIOS_PAGO,
  NOMBRE_CONCEPTO,
  errorPorteria,
  esCodigoSalida,
  normalizarCodigo,
} from './porteria';
import { RUTA_LECTOR } from './rutas';

function ErrorCaja({ error }) {
  if (!error) return null;
  return (
    <div className="resultado resultado--error" role="alert">
      <p className="resultado__titulo">{error.titulo}</p>
      {error.texto && <p>{error.texto}</p>}
    </div>
  );
}

// ---- Sin salida pendiente ----------------------------------------------------------

function BuscarInvitado({ onLiquidado }) {
  const [codigo, setCodigo] = useState('');
  const [errorCampo, setErrorCampo] = useState(null);
  const [error, setError] = useState(null);
  const [buscando, setBuscando] = useState(false);

  async function buscar(evento) {
    evento.preventDefault();
    setError(null);
    if (!esCodigoSalida(codigo)) {
      setErrorCampo('El código tiene 8 letras y números, como aparece en el ticket del invitado.');
      return;
    }
    setErrorCampo(null);
    setBuscando(true);
    try {
      const { data } = await api.post('/api/accesos/salida', { codigo_salida: normalizarCodigo(codigo) });
      onLiquidado(data);
    } catch (e) {
      const info = errorPorteria(e);
      setError({ ...info, texto: info.campos.codigo_salida ?? info.texto });
    } finally {
      setBuscando(false);
    }
  }

  return (
    <form className="tarjeta" onSubmit={buscar} noValidate aria-labelledby="titulo-buscar">
      <h2 id="titulo-buscar" className="bloque__titulo">
        Salida de un invitado
      </h2>
      <ErrorCaja error={error} />
      <Campo
        etiqueta="Código de salida"
        name="codigo_salida"
        value={codigo}
        onChange={(e) => {
          setCodigo(e.target.value.toUpperCase());
          if (errorCampo) setErrorCampo(null);
        }}
        error={errorCampo}
        ayuda="El código de 8 caracteres impreso en el ticket del invitado."
        placeholder="K7MP2QXA"
        maxLength={12}
        autoComplete="off"
        autoCapitalize="characters"
        spellCheck={false}
        readOnly={buscando}
      />
      <button type="submit" className="boton boton--primario boton--bloque" disabled={buscando}>
        {buscando ? 'Liquidando…' : 'Liquidar salida'}
      </button>
    </form>
  );
}

function SinCobro({ onLiquidado }) {
  return (
    <>
      <div className="vacio">
        <p className="vacio__titulo">No hay una salida pendiente de cobro</p>
        <p className="texto-suave">
          Para un conductor registrado, escanea su QR en el Lector con el modo Salida.
        </p>
        <Link to={RUTA_LECTOR} className="boton boton--secundario">
          Ir al lector
        </Link>
      </div>
      <BuscarInvitado onLiquidado={onLiquidado} />
    </>
  );
}

// ---- Liquidación -------------------------------------------------------------------

function SelectorMedio({ valor, onCambiar, disabled }) {
  return (
    <fieldset className="segmentos" disabled={disabled}>
      <legend className="campo__etiqueta">Medio recibido</legend>
      <div className="segmentos__opciones">
        {MEDIOS_PAGO.map((m) => (
          <label key={m.valor} className="segmentos__opcion">
            <input
              type="radio"
              name="medio"
              value={m.valor}
              checked={valor === m.valor}
              onChange={() => onCambiar(m.valor)}
            />
            <span>{m.texto}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function textoTarifa(liquidacion) {
  const { tarifa, motivo } = liquidacion;
  if (!tarifa) return motivo === 'mensualidad_activa' ? 'Mensualidad activa' : '—';
  return `${NOMBRE_CONCEPTO[tarifa.concepto] ?? tarifa.concepto} · ${formatoPesos.format(tarifa.valor)}`;
}

function Liquidacion({ liquidacion, onCancelar, onConfirmado }) {
  const [medio, setMedio] = useState(MEDIOS_PAGO[0].valor);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);

  const entrada = new Date(liquidacion.hora_entrada);
  const salida = new Date(liquidacion.hora_salida);
  const sinCobro = liquidacion.valor === 0;
  const porMensualidad = liquidacion.motivo === 'mensualidad_activa';
  const esInvitado = liquidacion.tipo_ingreso === 'invitado';
  // Si el ticket ya se cerró (por ejemplo, desde otra portería) no hay nada que cobrar.
  const yaCerrado = error?.codigo === 'ticket_cerrado' || error?.codigo === 'ticket_no_existe';

  async function confirmar() {
    setEnviando(true);
    setError(null);
    try {
      const { data } = await api.post('/api/accesos/salida/confirmar', {
        ticket_id: liquidacion.ticket_id,
        metodo_pago: medio,
      });
      onConfirmado(data);
    } catch (e) {
      setError(errorPorteria(e));
      setEnviando(false);
    }
  }

  return (
    <section className="tarjeta liquidacion" aria-labelledby="titulo-liquidacion">
      <h2 id="titulo-liquidacion" className="sr-only">
        Liquidación de {formatearPlaca(liquidacion.placa)}
      </h2>
      <div className="liquidacion__vehiculo">
        <span className="placa">{formatearPlaca(liquidacion.placa)}</span>
        <span className="liquidacion__tipo">
          {NOMBRE_TIPO[liquidacion.tipo_vehiculo] ?? liquidacion.tipo_vehiculo}
        </span>
        {esInvitado && <span className="chip">Invitado</span>}
      </div>

      <dl className="liquidacion__datos">
        <div>
          <dt>Hora de entrada</dt>
          <dd>
            <time dateTime={liquidacion.hora_entrada}>{horaConDia(entrada, salida)}</time>
          </dd>
        </div>
        <div>
          <dt>Hora de salida</dt>
          <dd>
            <time dateTime={liquidacion.hora_salida}>{horaConDia(salida, salida)}</time>
          </dd>
        </div>
        <div>
          <dt>Tiempo total</dt>
          <dd>{formatearDuracion(liquidacion.minutos)}</dd>
        </div>
        <div>
          <dt>Tarifa aplicada</dt>
          <dd>{textoTarifa(liquidacion)}</dd>
        </div>
      </dl>

      <div className="total">
        <p className="total__etiqueta">Total a cobrar</p>
        <p className="total__valor">{formatoPesos.format(liquidacion.valor)}</p>
        {porMensualidad && (
          <p className="etiqueta-mensualidad">
            <span className="estado-punto estado-punto--activo" aria-hidden="true" />
            Sin cobro: el conductor tiene mensualidad activa
          </p>
        )}
      </div>

      {!sinCobro && <SelectorMedio valor={medio} onCambiar={setMedio} disabled={enviando} />}

      <ErrorCaja error={error} />

      <div className="liquidacion__acciones">
        {!yaCerrado && (
          <button type="button" className="boton boton--primario boton--bloque" onClick={confirmar} disabled={enviando}>
            {enviando
              ? 'Registrando…'
              : sinCobro
                ? 'Registrar salida y abrir talanquera'
                : 'Registrar pago y abrir talanquera'}
          </button>
        )}
        <button type="button" className="boton boton--secundario boton--bloque" onClick={onCancelar} disabled={enviando}>
          {yaCerrado ? 'Volver al lector' : 'Cancelar'}
        </button>
      </div>
    </section>
  );
}

// ---- Pantalla ----------------------------------------------------------------------

export default function Cobros() {
  const { liquidacion, setLiquidacion } = useOutletContext();
  const navigate = useNavigate();

  function confirmado(recibo) {
    const valorMostrado = liquidacion.valor;
    setLiquidacion(null);
    navigate(RUTA_LECTOR, { state: { salida: recibo, valorMostrado } });
  }

  function cancelar() {
    // El ticket sigue abierto: no hay nada que deshacer en el servidor.
    setLiquidacion(null);
    navigate(RUTA_LECTOR);
  }

  return (
    <div className="porteria">
      <header className="saludo">
        <h1 className="saludo__titulo">Cobro de salida</h1>
        <p className="texto-suave">
          {liquidacion
            ? 'Revisa la liquidación, recibe el pago y registra la salida.'
            : 'Aquí aparece la liquidación al leer el QR de salida.'}
        </p>
      </header>

      {liquidacion ? (
        <Liquidacion
          key={liquidacion.ticket_id}
          liquidacion={liquidacion}
          onCancelar={cancelar}
          onConfirmado={confirmado}
        />
      ) : (
        <SinCobro onLiquidado={setLiquidacion} />
      )}
    </div>
  );
}
