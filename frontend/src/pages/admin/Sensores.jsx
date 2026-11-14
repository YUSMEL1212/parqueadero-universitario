/**
 * Sensores y bahías (/admin/sensores): resumen de bahías y sensores, alerta de sensores
 * desconectados y la tabla de GET /api/iot/sensores.
 *
 * Se actualiza sola cada 15 segundos. Con la pestaña oculta no consulta, y al volver
 * pide los datos de inmediato. Si una actualización falla se siguen mostrando los datos
 * anteriores con un aviso.
 *
 * El estado del sensor lo calcula el backend al consultar: sin pulso en más de 90 s es
 * `desconectado`; `falla` lo marca el administrador.
 */
import { useCallback, useEffect, useState } from 'react';

import api from '../../api/client';
import Aviso from '../../components/Aviso';
import { formatoHora } from '../../utils/formato';
import { NOMBRE_TIPO } from '../conductor/vehiculos';
import { NOMBRE_ESTADO_BAHIA, NOMBRE_ESTADO_SENSOR, haceTiempo, mensajeError } from './admin';

const INTERVALO_MS = 15000;

const formatoHoraSegundos = new Intl.DateTimeFormat('es-CO', {
  hour: 'numeric',
  minute: '2-digit',
  second: '2-digit',
});

const formatoFechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'medium' });

/** Consulta `url` cada `intervalo` ms mientras la pestaña está visible. */
function useConsultaPeriodica(url, intervalo) {
  const [estado, setEstado] = useState({ datos: null, error: null, cargando: true });
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    let vigente = true;
    function pedir() {
      api
        .get(url)
        .then(({ data }) => vigente && setEstado({ datos: data, error: null, cargando: false }))
        .catch((error) => vigente && setEstado((e) => ({ ...e, error, cargando: false })));
    }
    pedir();
    const id = setInterval(() => {
      if (!document.hidden) pedir();
    }, intervalo);
    const alVolver = () => {
      if (!document.hidden) pedir();
    };
    document.addEventListener('visibilitychange', alVolver);
    return () => {
      vigente = false;
      clearInterval(id);
      document.removeEventListener('visibilitychange', alVolver);
    };
  }, [url, intervalo, intento]);

  const recargar = useCallback(() => {
    setEstado((e) => ({ ...e, cargando: true }));
    setIntento((n) => n + 1);
  }, []);

  return { ...estado, recargar };
}

const tieneProblema = (fila) => fila.estado_sensor !== 'ok';

function resumen(filas) {
  const r = {
    total: filas.length,
    libres: { carro: 0, moto: 0 },
    ocupadas: { carro: 0, moto: 0 },
    fueraServicio: 0,
    desconectados: [],
    enFalla: 0,
    sinSensor: 0,
  };
  for (const f of filas) {
    if (f.estado_bahia === 'libre') r.libres[f.tipo_vehiculo] += 1;
    else if (f.estado_bahia === 'ocupada') r.ocupadas[f.tipo_vehiculo] += 1;
    else r.fueraServicio += 1;

    if (f.estado_sensor === 'desconectado') r.desconectados.push(f);
    else if (f.estado_sensor === 'falla') r.enFalla += 1;
    else if (f.estado_sensor == null) r.sinSensor += 1;
  }
  return r;
}

const suma = (porTipo) => porTipo.carro + porTipo.moto;
const porTipo = (conteo) => `Carro ${conteo.carro} · Moto ${conteo.moto}`;

function Metrica({ etiqueta, valor, nota, alerta }) {
  return (
    <div className={alerta ? 'metrica metrica--alerta' : 'metrica'}>
      <p className="metrica__etiqueta">{etiqueta}</p>
      <p className="metrica__valor">{valor}</p>
      {nota && <p className="metrica__nota">{nota}</p>}
    </div>
  );
}

function Insignia({ tipo, children }) {
  return <span className={`insignia insignia--${tipo}`}>{children}</span>;
}

const TIPO_INSIGNIA_BAHIA = { libre: 'ok', ocupada: 'info', fuera_servicio: 'neutra' };
const TIPO_INSIGNIA_SENSOR = { ok: 'ok', desconectado: 'alerta', falla: 'alerta' };

function UltimoPulso({ fila }) {
  if (!fila.ultimo_pulso) return <span className="texto-suave">Nunca</span>;
  return (
    <time dateTime={fila.ultimo_pulso} title={formatoFechaHora.format(new Date(fila.ultimo_pulso))}>
      {haceTiempo(fila.segundos_sin_pulso)}
    </time>
  );
}

function TablaSensores({ filas }) {
  return (
    <div className="tabla-contenedor">
      <table className="tabla">
        <caption className="sr-only">Estado de cada bahía y su sensor</caption>
        <thead>
          <tr>
            <th scope="col">Bahía</th>
            <th scope="col">Tipo</th>
            <th scope="col">Estado de la bahía</th>
            <th scope="col">Estado del sensor</th>
            <th scope="col">Último pulso</th>
          </tr>
        </thead>
        <tbody>
          {filas.map((f) => (
            <tr key={f.bahia} className={tieneProblema(f) ? 'fila--problema' : undefined}>
              <th scope="row" className="tabla__principal">
                {f.bahia}
              </th>
              <td>{NOMBRE_TIPO[f.tipo_vehiculo] ?? f.tipo_vehiculo}</td>
              <td>
                <Insignia tipo={TIPO_INSIGNIA_BAHIA[f.estado_bahia] ?? 'neutra'}>
                  {NOMBRE_ESTADO_BAHIA[f.estado_bahia] ?? f.estado_bahia}
                </Insignia>
              </td>
              <td>
                {f.device_uid ? (
                  <div className="tabla__pila">
                    <Insignia tipo={TIPO_INSIGNIA_SENSOR[f.estado_sensor] ?? 'neutra'}>
                      {NOMBRE_ESTADO_SENSOR[f.estado_sensor] ?? f.estado_sensor}
                    </Insignia>
                    <span className="tabla__codigo texto-suave">{f.device_uid}</span>
                  </div>
                ) : (
                  <Insignia tipo="neutra">Sin sensor</Insignia>
                )}
              </td>
              <td className="tabla__fecha">
                <UltimoPulso fila={f} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Sensores() {
  const { datos, error, cargando, recargar } = useConsultaPeriodica('/api/iot/sensores', INTERVALO_MS);

  let contenido;
  if (!datos) {
    contenido = error ? (
      <div className="vacio">
        <p className="vacio__titulo">No se pudo cargar el estado de los sensores</p>
        <p className="texto-suave">{mensajeError(error)}</p>
        <button type="button" className="boton boton--primario" onClick={recargar}>
          Reintentar
        </button>
      </div>
    ) : (
      <div className="vacio" role="status">
        <span className="spinner" aria-hidden="true" />
        <span className="texto-suave">Cargando sensores…</span>
      </div>
    );
  } else if (!datos.bahias.length) {
    contenido = (
      <div className="vacio">
        <p className="vacio__titulo">No hay bahías registradas</p>
        <p className="texto-suave">Las bahías y sus sensores se cargan con el seed del proyecto.</p>
      </div>
    );
  } else {
    const r = resumen(datos.bahias);
    const conProblema = r.desconectados.length + r.enFalla;
    const notaFallas = [
      r.desconectados.length && `${r.desconectados.length} desconectado${r.desconectados.length === 1 ? '' : 's'}`,
      r.enFalla && `${r.enFalla} en falla`,
      r.sinSensor && `${r.sinSensor} bahía${r.sinSensor === 1 ? '' : 's'} sin sensor`,
    ]
      .filter(Boolean)
      .join(' · ');

    contenido = (
      <>
        <div className="metricas">
          <Metrica
            etiqueta="Bahías totales"
            valor={r.total}
            nota={r.fueraServicio ? `${r.fueraServicio} fuera de servicio` : undefined}
          />
          <Metrica etiqueta="Libres" valor={suma(r.libres)} nota={porTipo(r.libres)} />
          <Metrica etiqueta="Ocupadas" valor={suma(r.ocupadas)} nota={porTipo(r.ocupadas)} />
          <Metrica
            etiqueta="Sensores con falla"
            valor={conProblema}
            nota={notaFallas || 'Todos en línea'}
            alerta={conProblema > 0}
          />
        </div>

        {r.desconectados.length > 0 && (
          <div className="franja franja--alerta">
            <div className="franja__texto">
              <p className="franja__titulo">
                <span className="estado-punto estado-punto--alerta" aria-hidden="true" />
                {r.desconectados.length === 1
                  ? '1 sensor desconectado'
                  : `${r.desconectados.length} sensores desconectados`}
              </p>
              <p>
                {r.desconectados.map((f, i) => (
                  <span key={f.bahia}>
                    {i > 0 && ', '}
                    <strong>{f.device_uid}</strong> (bahía {f.bahia})
                  </span>
                ))}
                . Llevan más de 90 segundos sin enviar señal: revisa su alimentación y la conexión
                WiFi.
              </p>
            </div>
          </div>
        )}

        <TablaSensores filas={datos.bahias} />
      </>
    );
  }

  return (
    <div className="panel">
      <header className="saludo">
        <h1 className="saludo__titulo">Sensores y bahías</h1>
        <div className="bloque__encabezado">
          <p className="texto-suave">Se actualiza sola cada 15 segundos.</p>
          {datos && (
            <span className={error ? 'en-vivo' : 'en-vivo en-vivo--activo'}>
              <span className="en-vivo__punto" aria-hidden="true" />
              Actualizado a las {formatoHoraSegundos.format(new Date(datos.generado_en))}
              <button
                type="button"
                className="boton boton--texto"
                onClick={recargar}
                disabled={cargando}
              >
                {cargando ? 'Actualizando…' : 'Actualizar ahora'}
              </button>
            </span>
          )}
        </div>
      </header>

      {error && datos && (
        <Aviso tipo="error">
          No se pudo actualizar ({mensajeError(error)}). Se muestran los datos de las{' '}
          {formatoHora.format(new Date(datos.generado_en))}.
        </Aviso>
      )}

      {contenido}
    </div>
  );
}
