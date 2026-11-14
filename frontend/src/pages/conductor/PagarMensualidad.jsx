/**
 * Pagar mensualidad (/conductor/pagos).
 *
 * Formulario: tipo de vehículo (actualiza el precio, que sale de la tabla de tarifas),
 * medio de pago (PSE con banco, o tarjeta de crédito), correo para el comprobante y
 * total. "Pagar" llama a POST /api/pagos/mensualidad y lleva al conductor a `url_pago`:
 * el checkout de Wompi o, sin llaves configuradas, la pasarela simulada del backend.
 *
 * Regreso: la pasarela vuelve aquí con `?referencia=…` (Wompi agrega `&id=…`). La
 * pantalla consulta GET /api/pagos/mensualidad/{referencia} cada 2 s hasta que el pago
 * deje de estar pendiente y muestra el resultado. La mensualidad la crea el webhook, no
 * esta pantalla: si el pago se rechaza no se activa nada.
 */
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import api from '../../api/client';
import { leerError } from '../../api/errores';
import { useAuth } from '../../auth/AuthContext';
import Aviso from '../../components/Aviso';
import Campo from '../../components/Campo';
import SelectorTipo from '../../components/SelectorTipo';
import useConsulta from '../../hooks/useConsulta';
import { formatoFecha, formatoPesos } from '../../utils/formato';
import { RUTA_INICIO_CONDUCTOR } from './rutas';
import { NOMBRE_TIPO } from './vehiculos';

const MEDIOS = [
  { valor: 'pse', texto: 'PSE' },
  { valor: 'tarjeta', texto: 'Tarjeta de crédito' },
];

const INTERVALO_CONSULTA_MS = 2000;
const MAX_CONSULTAS = 30; // ~1 minuto esperando la confirmación

const PATRON_CORREO = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const tipoValido = (tipo) => (tipo in NOMBRE_TIPO ? tipo : 'carro');
const nombreTipo = (tipo) => NOMBRE_TIPO[tipo]?.toLowerCase() ?? tipo;

function sinCampo(errores, campo) {
  const resto = { ...errores };
  delete resto[campo];
  return resto;
}

// ---- Resultado al volver de la pasarela ---------------------------------------------

function useEstadoPago(referencia, transaccion) {
  const [estado, setEstado] = useState({ pago: null, error: null, agotado: false });
  const [ronda, setRonda] = useState(0);

  useEffect(() => {
    let vigente = true;
    let temporizador;
    let intentos = 0;
    const url = `/api/pagos/mensualidad/${encodeURIComponent(referencia)}`;
    const params = transaccion ? { transaccion } : undefined;

    function consultar() {
      intentos += 1;
      api
        .get(url, { params })
        .then(({ data }) => {
          if (!vigente) return;
          const agotado = data.estado === 'pendiente' && intentos >= MAX_CONSULTAS;
          setEstado({ pago: data, error: null, agotado });
          if (data.estado === 'pendiente' && !agotado) {
            temporizador = setTimeout(consultar, INTERVALO_CONSULTA_MS);
          }
        })
        .catch((error) => {
          if (!vigente) return;
          // Un fallo de red no es definitivo: se reintenta mientras queden intentos.
          if (!error.response && intentos < MAX_CONSULTAS) {
            temporizador = setTimeout(consultar, INTERVALO_CONSULTA_MS);
          } else {
            setEstado((e) => ({ ...e, error }));
          }
        });
    }

    consultar();
    return () => {
      vigente = false;
      clearTimeout(temporizador);
    };
  }, [referencia, transaccion, ronda]);

  const reintentar = () => {
    setEstado({ pago: null, error: null, agotado: false });
    setRonda((n) => n + 1);
  };

  return { ...estado, reintentar };
}

function ResultadoPago({ referencia, transaccion, onNuevoPago }) {
  const { pago, error, agotado, reintentar } = useEstadoPago(referencia, transaccion);

  if (error) {
    const noExiste = error.response?.status === 404;
    return (
      <div className="vacio">
        <p className="vacio__titulo">
          {noExiste ? 'No encontramos ese pago' : 'No se pudo consultar el pago'}
        </p>
        <p className="texto-suave">
          {noExiste
            ? 'La referencia no corresponde a un pago de tu cuenta.'
            : leerError(error).general}
        </p>
        {noExiste ? (
          <button type="button" className="boton boton--primario" onClick={() => onNuevoPago()}>
            Ir al pago de mensualidad
          </button>
        ) : (
          <button type="button" className="boton boton--primario" onClick={reintentar}>
            Reintentar
          </button>
        )}
      </div>
    );
  }

  if (!pago || (pago.estado === 'pendiente' && !agotado)) {
    return (
      <div className="vacio" role="status" aria-live="polite">
        <span className="spinner" aria-hidden="true" />
        <p className="vacio__titulo">Confirmando tu pago…</p>
        <p className="texto-suave">Esperamos la respuesta de la pasarela. No cierres esta pantalla.</p>
      </div>
    );
  }

  if (pago.estado === 'pendiente') {
    return (
      <div className="vacio" role="status">
        <p className="vacio__titulo">Tu pago sigue en proceso</p>
        <p className="texto-suave">
          La pasarela aún no confirma el pago. Algunos pagos por PSE tardan unos minutos; tu
          mensualidad se activará en cuanto se apruebe.
        </p>
        <button type="button" className="boton boton--primario" onClick={reintentar}>
          Consultar de nuevo
        </button>
      </div>
    );
  }

  const tipo = nombreTipo(pago.tipo_vehiculo);

  if (pago.estado === 'aprobado') {
    const vence = pago.mensualidad ? new Date(pago.mensualidad.vence_en) : null;
    return (
      <section className="tarjeta" aria-labelledby="titulo-resultado">
        <div className="resultado resultado--exito" role="status">
          <p id="titulo-resultado" className="resultado__titulo">
            Pago aprobado
          </p>
          <p>
            Tu mensualidad de {tipo} está activa
            {vence && (
              <>
                {' '}hasta el <strong>{formatoFecha.format(vence)}</strong>
              </>
            )}
            . Entras y sales sin cobro con tu {tipo}.
          </p>
        </div>
        <dl className="liquidacion__datos">
          <div>
            <dt>Valor pagado</dt>
            <dd>{formatoPesos.format(pago.valor)}</dd>
          </div>
          <div>
            <dt>Vence</dt>
            <dd>{vence ? formatoFecha.format(vence) : '—'}</dd>
          </div>
          <div className="liquidacion__dato--ancho">
            <dt>Referencia</dt>
            <dd className="referencia">{pago.referencia}</dd>
          </div>
        </dl>
        <Link to={RUTA_INICIO_CONDUCTOR} className="boton boton--primario boton--bloque">
          Ir al inicio
        </Link>
      </section>
    );
  }

  return (
    <section className="tarjeta" aria-labelledby="titulo-resultado">
      <div className="resultado resultado--error" role="alert">
        <p id="titulo-resultado" className="resultado__titulo">
          Pago rechazado
        </p>
        <p>
          La pasarela no aprobó el pago de {formatoPesos.format(pago.valor)}. No se activó ninguna
          mensualidad. Revisa los datos de tu medio de pago o intenta con otro.
        </p>
      </div>
      <button
        type="button"
        className="boton boton--primario boton--bloque"
        onClick={() => onNuevoPago(pago.tipo_vehiculo)}
      >
        Intentar de nuevo
      </button>
      <Link to={RUTA_INICIO_CONDUCTOR} className="boton boton--secundario boton--bloque">
        Volver al inicio
      </Link>
    </section>
  );
}

// ---- Formulario --------------------------------------------------------------------

function SelectorMedio({ valor, onCambiar, disabled }) {
  return (
    <fieldset className="segmentos" disabled={disabled}>
      <legend className="campo__etiqueta">Medio de pago</legend>
      <div className="segmentos__opciones">
        {MEDIOS.map((m) => (
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

function SelectorBanco({ valor, onCambiar, error, disabled }) {
  const { datos, error: errorCarga, cargando, recargar } = useConsulta('/api/pagos/pse/bancos');

  if (errorCarga) {
    return (
      <Aviso tipo="error">
        No se pudo cargar la lista de bancos.{' '}
        <button type="button" className="boton boton--texto" onClick={recargar}>
          Reintentar
        </button>
      </Aviso>
    );
  }

  const opciones = [
    { valor: '', texto: cargando ? 'Cargando bancos…' : 'Elige tu banco' },
    ...(datos ?? []).map((b) => ({ valor: b.codigo, texto: b.nombre })),
  ];
  return (
    <Campo
      etiqueta="Banco"
      name="banco"
      value={valor}
      opciones={opciones}
      onChange={(e) => onCambiar(e.target.value)}
      error={error}
      disabled={disabled || cargando}
    />
  );
}

function AvisoMensualidadActual({ tipo }) {
  const { datos } = useConsulta('/api/mensualidades/vigentes');
  const actual = (datos ?? []).find((m) => m.tipo_vehiculo === tipo);
  if (!actual) return null;
  return (
    <Aviso tipo="info">
      Ya tienes una mensualidad de {nombreTipo(tipo)} activa hasta el{' '}
      {formatoFecha.format(new Date(actual.vence_en))}. Si pagas ahora, la nueva cuenta 30 días
      desde hoy y no se suma a la actual.
    </Aviso>
  );
}

function FormularioPago({ tipoInicial, onCambiarTipo }) {
  const { usuario } = useAuth();
  const [tipo, setTipo] = useState(tipoInicial);
  const [medio, setMedio] = useState('pse');
  const [banco, setBanco] = useState('');
  const [correo, setCorreo] = useState(usuario?.email ?? '');
  const [errores, setErrores] = useState({});
  const [errorGeneral, setErrorGeneral] = useState(null);
  const [enviando, setEnviando] = useState(false);

  const precio = useConsulta(`/api/pagos/mensualidad/precio?tipo=${tipo}`);
  // Mientras llega el precio del tipo nuevo, no se muestra el del anterior.
  const valor = precio.datos?.tipo_vehiculo === tipo ? precio.datos.valor : null;
  const sinTarifa = precio.error?.response?.status === 409;

  function cambiarTipo(nuevo) {
    setTipo(nuevo);
    onCambiarTipo(nuevo);
  }

  function validar() {
    const nuevos = {};
    if (medio === 'pse' && !banco) nuevos.banco = 'Elige tu banco.';
    if (!PATRON_CORREO.test(correo.trim())) nuevos.correo = 'Escribe un correo válido.';
    setErrores(nuevos);
    return Object.keys(nuevos).length === 0;
  }

  async function pagar(evento) {
    evento.preventDefault();
    setErrorGeneral(null);
    if (!validar()) return;
    setEnviando(true);
    try {
      const { data } = await api.post('/api/pagos/mensualidad', {
        tipo_vehiculo: tipo,
        metodo: medio,
        banco: medio === 'pse' ? banco : '',
        correo: correo.trim(),
        url_retorno: `${window.location.origin}${window.location.pathname}`,
      });
      // La pasarela es otra página: se sale de la PWA y se vuelve con ?referencia=.
      window.location.assign(data.url_pago);
    } catch (e) {
      const { general, campos } = leerError(e);
      setErrores(campos);
      setErrorGeneral(e.response?.data?.detail ?? general);
      setEnviando(false);
    }
  }

  let textoValor;
  if (sinTarifa) textoValor = 'No disponible';
  else if (valor == null) textoValor = precio.error ? '—' : 'Consultando…';
  else textoValor = formatoPesos.format(valor);

  return (
    <form className="tarjeta pago" onSubmit={pagar} noValidate aria-labelledby="titulo-concepto">
      <div className="pago__concepto">
        <div>
          <h2 id="titulo-concepto" className="bloque__titulo">
            Mensualidad de {nombreTipo(tipo)}
          </h2>
          <p className="texto-suave">30 días de entradas y salidas sin cobro, desde que se aprueba el pago.</p>
        </div>
        <p className="pago__precio" aria-live="polite">
          {textoValor}
        </p>
      </div>

      <SelectorTipo valor={tipo} onCambiar={cambiarTipo} disabled={enviando} />
      <AvisoMensualidadActual tipo={tipo} />

      {sinTarifa && (
        <Aviso tipo="error">
          La mensualidad de {nombreTipo(tipo)} no tiene una tarifa vigente. Avisa a la administración
          del parqueadero.
        </Aviso>
      )}
      {precio.error && !sinTarifa && (
        <Aviso tipo="error">
          No se pudo consultar el precio. {leerError(precio.error).general}{' '}
          <button type="button" className="boton boton--texto" onClick={precio.recargar}>
            Reintentar
          </button>
        </Aviso>
      )}

      <SelectorMedio
        valor={medio}
        onCambiar={(m) => {
          setMedio(m);
          setErrores((e) => sinCampo(e, 'banco'));
        }}
        disabled={enviando}
      />

      {medio === 'pse' && (
        <SelectorBanco
          valor={banco}
          onCambiar={(b) => {
            setBanco(b);
            setErrores((e) => sinCampo(e, 'banco'));
          }}
          error={errores.banco}
          disabled={enviando}
        />
      )}

      <Campo
        etiqueta="Correo para el comprobante"
        name="correo"
        type="email"
        value={correo}
        onChange={(e) => setCorreo(e.target.value)}
        error={errores.correo}
        autoComplete="email"
        inputMode="email"
        readOnly={enviando}
      />

      <div className="total">
        <p className="total__etiqueta">Total a pagar</p>
        <p className="total__valor">{valor == null ? '—' : formatoPesos.format(valor)}</p>
      </div>

      <Aviso tipo="error">{errorGeneral}</Aviso>

      <button
        type="submit"
        className="boton boton--primario boton--bloque"
        disabled={enviando || valor == null}
      >
        {enviando ? 'Abriendo la pasarela…' : valor == null ? 'Pagar' : `Pagar ${formatoPesos.format(valor)}`}
      </button>
      <p className="texto-suave pago__nota">
        Te llevaremos a la pasarela de pagos para completar el pago
        {medio === 'pse' ? ' con tu banco' : ' con tu tarjeta'}. Tu mensualidad se activa apenas se
        apruebe.
      </p>
    </form>
  );
}

// ---- Pantalla ----------------------------------------------------------------------

export default function PagarMensualidad() {
  const [params, setParams] = useSearchParams();
  const referencia = params.get('referencia');
  const transaccion = params.get('id');
  const tipo = tipoValido(params.get('tipo'));

  return (
    <div className="conductor">
      <header className="saludo">
        <h1 className="saludo__titulo">Pagar mensualidad</h1>
        <p className="texto-suave">
          {referencia
            ? 'Resultado de tu pago.'
            : 'Con la mensualidad activa no pagas al salir del parqueadero.'}
        </p>
      </header>

      {referencia ? (
        <ResultadoPago
          key={referencia}
          referencia={referencia}
          transaccion={transaccion}
          onNuevoPago={(tipoPago) => setParams({ tipo: tipoPago ?? tipo }, { replace: true })}
        />
      ) : (
        <FormularioPago
          tipoInicial={tipo}
          onCambiarTipo={(nuevo) => setParams({ tipo: nuevo }, { replace: true })}
        />
      )}
    </div>
  );
}
