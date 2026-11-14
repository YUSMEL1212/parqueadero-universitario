/**
 * Pantalla principal del conductor (/conductor):
 *   1. Saludo.
 *   2. Cupos libres de carro y de moto, en vivo (ws/cupos, con respaldo por HTTP).
 *   3. QR dinámico del vehículo elegido, con su cuenta regresiva.
 *   4. Estado de la mensualidad del tipo de ese vehículo.
 */
import { QRCodeSVG } from 'qrcode.react';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import api from '../../api/client';
import { leerError } from '../../api/errores';
import { useAuth } from '../../auth/AuthContext';
import useCupos from '../../hooks/useCupos';
import useQR from '../../hooks/useQR';
import { RUTA_PAGAR_MENSUALIDAD, RUTA_VEHICULOS } from './rutas';

const CLAVE_VEHICULO = 'parqueadero.vehiculo-elegido';
const NOMBRE_TIPO = { carro: 'Carro', moto: 'Moto' };
const DIAS_AVISO_RENOVAR = 5;
const MS_DIA = 24 * 60 * 60 * 1000;

const formatoFecha = new Intl.DateTimeFormat('es-CO', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});

/** ABC123 → "ABC 123"; ABC12D → "ABC 12D". */
function formatearPlaca(placa = '') {
  return placa.length === 6 ? `${placa.slice(0, 3)} ${placa.slice(3)}` : placa;
}

function leerVehiculoGuardado() {
  try {
    return localStorage.getItem(CLAVE_VEHICULO);
  } catch {
    return null;
  }
}

function guardarVehiculo(id) {
  try {
    localStorage.setItem(CLAVE_VEHICULO, id);
  } catch {
    // Sin almacenamiento: la elección dura lo que dure la pantalla.
  }
}

/** Pide `url` al montar; `recargar()` la vuelve a pedir. */
function useConsulta(url) {
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
  return { ...estado, recargar };
}

/** Hora actual, actualizada cada `cadaMs` mientras `activo` sea true. */
function useAhora(activo, cadaMs = 250) {
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    if (!activo) return undefined;
    const id = setInterval(() => setAhora(Date.now()), cadaMs);
    return () => clearInterval(id);
  }, [activo, cadaMs]);
  return ahora;
}

// ---- Cupos -------------------------------------------------------------------------

function TarjetaCupo({ etiqueta, valor, destacada }) {
  const sinDato = valor == null;
  return (
    <div className={destacada ? 'cupo cupo--destacado' : 'cupo'}>
      <span className="cupo__etiqueta">{etiqueta}</span>
      <span className={valor === 0 ? 'cupo__numero cupo__numero--cero' : 'cupo__numero'}>
        {sinDato ? '—' : valor}
      </span>
      {valor === 0 && <span className="cupo__nota">Sin cupos</span>}
    </div>
  );
}

function Cupos({ tipoElegido }) {
  const { libres, enVivo, error } = useCupos();

  let estado = 'Conectando…';
  if (enVivo) estado = 'En vivo';
  else if (libres) estado = 'Reconectando… se actualiza cada 15 s';
  else if (error) estado = 'No se pudo consultar. Reintentando…';

  return (
    <section className="bloque" aria-labelledby="titulo-cupos">
      <div className="bloque__encabezado">
        <h2 id="titulo-cupos" className="bloque__titulo">
          Cupos disponibles
        </h2>
        <span className={enVivo ? 'en-vivo en-vivo--activo' : 'en-vivo'} role="status">
          <span className="en-vivo__punto" aria-hidden="true" />
          {estado}
        </span>
      </div>
      <div className="cupos" aria-live="polite">
        <TarjetaCupo etiqueta="Carros libres" valor={libres?.carro} destacada={tipoElegido === 'carro'} />
        <TarjetaCupo etiqueta="Motos libres" valor={libres?.moto} destacada={tipoElegido === 'moto'} />
      </div>
    </section>
  );
}

// ---- QR ----------------------------------------------------------------------------

function SelectorVehiculo({ vehiculos, elegido, onElegir }) {
  return (
    <fieldset className="selector">
      <legend className="selector__leyenda">¿Con qué vehículo ingresas?</legend>
      <div className="selector__opciones">
        {vehiculos.map((v) => (
          <label key={v.id} className="selector__opcion">
            <input
              type="radio"
              name="vehiculo"
              value={v.id}
              checked={v.id === elegido}
              onChange={() => onElegir(v.id)}
            />
            <span className="selector__placa">{formatearPlaca(v.placa)}</span>
            <span className="selector__tipo">{NOMBRE_TIPO[v.tipo] ?? v.tipo}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function CodigoQR({ vehiculo }) {
  const { qr, cargando, error, reintentar } = useQR(vehiculo.id);
  const ahora = useAhora(Boolean(qr));

  if (error && !qr) {
    const { general } = leerError(error, {
      404: 'Este vehículo ya no está activo. Actualiza la página o elige otro.',
      403: 'Tu cuenta no puede generar códigos de ingreso.',
    });
    return (
      <div className="qr qr--vacio">
        <p className="qr__mensaje-titulo">No se pudo generar tu código</p>
        <p className="texto-suave">{general}</p>
        <button type="button" className="boton boton--primario" onClick={reintentar}>
          Reintentar
        </button>
      </div>
    );
  }

  const restantes = qr
    ? Math.min(qr.total, Math.max(0, Math.ceil((qr.venceLocal - ahora) / 1000)))
    : 0;
  const porcentaje = qr ? Math.min(100, (Math.max(0, qr.venceLocal - ahora) / (qr.total * 1000)) * 100) : 0;
  // Al llegar a cero el código ya no sirve: se tapa mientras llega el nuevo.
  const renovando = !qr || restantes === 0 || cargando;

  return (
    <div className="qr">
      <div className={renovando ? 'qr__lienzo qr__lienzo--renovando' : 'qr__lienzo'}>
        {qr ? (
          <QRCodeSVG
            value={qr.token}
            size={240}
            level="M"
            marginSize={2}
            title={`Código de ingreso para ${vehiculo.placa}`}
            className="qr__imagen"
          />
        ) : (
          <div className="qr__imagen qr__imagen--vacia" />
        )}
        {renovando && (
          <div className="qr__capa" role="status">
            <span className="spinner" aria-hidden="true" />
            <span>{qr ? 'Generando código nuevo…' : 'Generando código…'}</span>
          </div>
        )}
      </div>

      <div className="qr__vehiculo">
        <span className="placa">{formatearPlaca(vehiculo.placa)}</span>
        <span className="texto-suave">{NOMBRE_TIPO[vehiculo.tipo] ?? vehiculo.tipo}</span>
      </div>

      <div className="qr__tiempo">
        <div
          className="progreso"
          role="progressbar"
          aria-label="Vigencia del código"
          aria-valuemin={0}
          aria-valuemax={qr?.total ?? 60}
          aria-valuenow={restantes}
        >
          <div className="progreso__barra" style={{ width: `${porcentaje}%` }} />
        </div>
        <p className="qr__contador texto-suave">
          {qr && restantes > 0 ? `Se renueva en ${restantes} s` : 'Renovando…'}
        </p>
      </div>
      <p className="qr__ayuda texto-suave">Muestra este código al lector de la entrada.</p>
    </div>
  );
}

function SinVehiculos() {
  return (
    <div className="qr qr--vacio">
      <p className="qr__mensaje-titulo">Aún no tienes vehículos registrados</p>
      <p className="texto-suave">
        Registra tu carro o tu moto para generar el código QR con el que ingresas al
        parqueadero.
      </p>
      <Link to={RUTA_VEHICULOS} className="boton boton--primario">
        Registrar vehículo
      </Link>
    </div>
  );
}

function SeccionQR({ vehiculos, error, cargando, recargar, elegido, onElegir }) {
  const vehiculo = vehiculos?.find((v) => v.id === elegido);

  let contenido;
  if (cargando && !vehiculos) {
    contenido = (
      <div className="qr qr--vacio" role="status">
        <span className="spinner" aria-hidden="true" />
        <span className="texto-suave">Cargando tus vehículos…</span>
      </div>
    );
  } else if (error) {
    contenido = (
      <div className="qr qr--vacio">
        <p className="qr__mensaje-titulo">No se pudieron cargar tus vehículos</p>
        <p className="texto-suave">{leerError(error).general}</p>
        <button type="button" className="boton boton--primario" onClick={recargar}>
          Reintentar
        </button>
      </div>
    );
  } else if (!vehiculos?.length) {
    contenido = <SinVehiculos />;
  } else {
    contenido = (
      <>
        {vehiculos.length > 1 && (
          <SelectorVehiculo vehiculos={vehiculos} elegido={elegido} onElegir={onElegir} />
        )}
        {/* key: al cambiar de vehículo el QR arranca de cero, sin mostrar el anterior. */}
        {vehiculo && <CodigoQR key={vehiculo.id} vehiculo={vehiculo} />}
      </>
    );
  }

  return (
    <section className="tarjeta" aria-labelledby="titulo-qr">
      <h2 id="titulo-qr" className="bloque__titulo">
        Tu código de ingreso
      </h2>
      {contenido}
    </section>
  );
}

// ---- Mensualidad -------------------------------------------------------------------

function FranjaMensualidad({ tipo }) {
  const { datos, error, cargando, recargar } = useConsulta('/api/mensualidades/vigentes');
  const [ahora] = useState(Date.now);

  if (cargando && !datos) {
    return (
      <div className="franja" role="status">
        <span className="spinner" aria-hidden="true" />
        <span className="texto-suave">Consultando tu mensualidad…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="franja">
        <div className="franja__texto">
          <p className="franja__titulo">No se pudo consultar tu mensualidad</p>
          <p className="texto-suave">{leerError(error).general}</p>
        </div>
        <button type="button" className="boton boton--secundario" onClick={recargar}>
          Reintentar
        </button>
      </div>
    );
  }

  // Cada mensualidad cubre solo su tipo de vehículo. Sin vehículo elegido, cualquiera.
  const vigentes = (datos ?? []).filter((m) => !tipo || m.tipo_vehiculo === tipo);
  const actual = vigentes.reduce(
    (mejor, m) => (!mejor || Date.parse(m.vence_en) > Date.parse(mejor.vence_en) ? m : mejor),
    null,
  );
  const sufijoTipo = tipo ? ` de ${NOMBRE_TIPO[tipo]?.toLowerCase() ?? tipo}` : '';
  const destinoPago = tipo ? `${RUTA_PAGAR_MENSUALIDAD}?tipo=${tipo}` : RUTA_PAGAR_MENSUALIDAD;

  if (!actual) {
    return (
      <div className="franja">
        <div className="franja__texto">
          <p className="franja__titulo">
            <span className="estado-punto" aria-hidden="true" />
            Sin mensualidad{sufijoTipo}
          </p>
          <p className="texto-suave">Pagas por tiempo cada vez que sales.</p>
        </div>
        <Link to={destinoPago} className="boton boton--primario">
          Pagar mensualidad
        </Link>
      </div>
    );
  }

  const vence = new Date(actual.vence_en);
  const dias = Math.ceil((vence.getTime() - ahora) / MS_DIA);
  const porVencer = dias <= DIAS_AVISO_RENOVAR;

  return (
    <div className="franja franja--activa">
      <div className="franja__texto">
        <p className="franja__titulo">
          <span className="estado-punto estado-punto--activo" aria-hidden="true" />
          Mensualidad{sufijoTipo} activa
        </p>
        <p className="texto-suave">
          Hasta el {formatoFecha.format(vence)}
          {porVencer && ` · vence en ${dias} ${dias === 1 ? 'día' : 'días'}`}
        </p>
      </div>
      {porVencer && (
        <Link to={destinoPago} className="boton boton--secundario">
          Renovar
        </Link>
      )}
    </div>
  );
}

// ---- Pantalla ----------------------------------------------------------------------

export default function InicioConductor() {
  const { usuario } = useAuth();
  const consultaVehiculos = useConsulta('/api/vehiculos');
  const vehiculos = consultaVehiculos.datos?.filter((v) => v.activo) ?? null;

  const [elegido, setElegido] = useState(leerVehiculoGuardado);
  // Si el guardado ya no existe (o no hay ninguno), se usa el primero de la lista.
  const idElegido = vehiculos?.some((v) => v.id === elegido) ? elegido : vehiculos?.[0]?.id ?? null;
  const vehiculoElegido = vehiculos?.find((v) => v.id === idElegido) ?? null;

  function elegir(id) {
    setElegido(id);
    guardarVehiculo(id);
  }

  const primerNombre = usuario.nombre.trim().split(/\s+/)[0];

  return (
    <div className="conductor">
      <header className="saludo">
        <h1 className="saludo__titulo">Hola, {primerNombre}</h1>
        <p className="texto-suave">Revisa los cupos y muestra tu código en la entrada.</p>
      </header>

      <Cupos tipoElegido={vehiculoElegido?.tipo} />

      <SeccionQR
        vehiculos={vehiculos}
        error={consultaVehiculos.error}
        cargando={consultaVehiculos.cargando}
        recargar={consultaVehiculos.recargar}
        elegido={idElegido}
        onElegir={elegir}
      />

      <FranjaMensualidad tipo={vehiculoElegido?.tipo} />
    </div>
  );
}
