/**
 * Invitados (/porteria/invitados): ingreso de un vehículo sin cuenta.
 *
 *   1. Formulario Carro/Moto + placa, con la misma validación de formato que
 *      "Mis vehículos" (el backend la repite).
 *   2. POST /api/accesos/invitados → ticket con el código de salida en grande.
 *   3. Imprimir (vista limpia solo del ticket, ver @media print en index.css) o
 *      enviar el código por WhatsApp con https://wa.me/.
 *
 * Al salir, el invitado presenta el código y el guarda lo escribe en el Lector (modo
 * Salida) o en Cobros.
 */
import { useRef, useState } from 'react';

import api from '../../api/client';
import Aviso from '../../components/Aviso';
import Campo from '../../components/Campo';
import SelectorTipo from '../../components/SelectorTipo';
import { formatoFecha, formatoHora } from '../../utils/formato';
import { NOMBRE_TIPO, ejemploPlaca, errorDePlaca, formatearPlaca, normalizarPlaca } from '../conductor/vehiculos';
import { errorPorteria, gruposCodigo } from './porteria';

// ---- WhatsApp ----------------------------------------------------------------------

/**
 * Celular escrito por el guarda → número para wa.me (solo dígitos, con indicativo).
 * Vacío → '' (WhatsApp deja elegir el contacto). Un celular colombiano de 10 dígitos
 * recibe el 57; con "+" se respeta el indicativo escrito.
 * Devuelve { numero } o { error }.
 */
function numeroWhatsApp(celular) {
  const texto = celular.trim();
  if (!texto) return { numero: '' };
  const digitos = texto.replace(/\D/g, '');
  if (texto.startsWith('+')) {
    return digitos.length >= 8 && digitos.length <= 15
      ? { numero: digitos }
      : { error: 'Revisa el número: con indicativo debe tener entre 8 y 15 dígitos.' };
  }
  if (digitos.length === 10 && digitos.startsWith('3')) return { numero: `57${digitos}` };
  if (digitos.length === 12 && digitos.startsWith('573')) return { numero: digitos };
  return { error: 'Escribe un celular de 10 dígitos, por ejemplo 300 123 4567, o déjalo vacío.' };
}

function mensajeTicket(ticket) {
  const entrada = new Date(ticket.hora_entrada);
  return [
    'Parqueadero Universitario – Ticket de invitado',
    `Código de salida: ${ticket.codigo_salida}`,
    `Placa: ${formatearPlaca(ticket.placa)} (${NOMBRE_TIPO[ticket.tipo_vehiculo] ?? ticket.tipo_vehiculo})`,
    `Entrada: ${formatoFecha.format(entrada)}, ${formatoHora.format(entrada)}`,
    'Presenta este código en la portería al salir.',
  ].join('\n');
}

// ---- Ticket ------------------------------------------------------------------------

function DatosTicket({ ticket }) {
  const entrada = new Date(ticket.hora_entrada);
  return (
    <>
      <div className="ticket__codigo">
        <p className="ticket__etiqueta">Código de salida</p>
        <p className="ticket__valor" aria-label={ticket.codigo_salida.split('').join(' ')}>
          {gruposCodigo(ticket.codigo_salida).map((grupo, i) => (
            // Los grupos pueden repetirse ("ABCDABCD"): la posición es la clave.
            <span key={i}>{grupo}</span>
          ))}
        </p>
      </div>
      <dl className="ticket__datos">
        <div>
          <dt>Placa</dt>
          <dd>{formatearPlaca(ticket.placa)}</dd>
        </div>
        <div>
          <dt>Tipo</dt>
          <dd>{NOMBRE_TIPO[ticket.tipo_vehiculo] ?? ticket.tipo_vehiculo}</dd>
        </div>
        <div>
          <dt>Hora de entrada</dt>
          <dd>
            <time dateTime={ticket.hora_entrada}>
              {formatoHora.format(entrada)}
              <span className="ticket__fecha"> · {formatoFecha.format(entrada)}</span>
            </time>
          </dd>
        </div>
      </dl>
    </>
  );
}

/** Copia del ticket que solo aparece al imprimir. */
function TicketImpresion({ ticket }) {
  return (
    <div className="ticket-impresion" aria-hidden="true">
      <p className="ticket-impresion__marca">Parqueadero Universitario</p>
      <p className="ticket-impresion__titulo">Ticket de invitado</p>
      <DatosTicket ticket={ticket} />
      <p className="ticket-impresion__pie">Presente este código en la portería al salir.</p>
    </div>
  );
}

function TicketInvitado({ ticket, onNuevo }) {
  const [celular, setCelular] = useState('');
  const [errorCelular, setErrorCelular] = useState(null);

  function enviarWhatsApp() {
    const { numero, error } = numeroWhatsApp(celular);
    if (error) {
      setErrorCelular(error);
      return;
    }
    setErrorCelular(null);
    const url = `https://wa.me/${numero}?text=${encodeURIComponent(mensajeTicket(ticket))}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  return (
    <>
      <section className="tarjeta ticket no-imprimir" aria-labelledby="titulo-ticket">
        <div className="ticket__encabezado">
          <h2 id="titulo-ticket" className="bloque__titulo">
            Ingreso registrado
          </h2>
          <span className="chip">Invitado</span>
        </div>
        <DatosTicket ticket={ticket} />
        <p className="texto-suave ticket__nota">
          Entrega este código al invitado: lo necesita para salir.
        </p>

        <button type="button" className="boton boton--primario boton--bloque" onClick={() => window.print()}>
          Imprimir ticket
        </button>

        <div className="ticket__whatsapp">
          <Campo
            etiqueta="Celular del invitado (opcional)"
            name="celular"
            type="tel"
            inputMode="tel"
            value={celular}
            onChange={(e) => {
              setCelular(e.target.value);
              if (errorCelular) setErrorCelular(null);
            }}
            error={errorCelular}
            ayuda="Si lo dejas vacío, WhatsApp te deja elegir el contacto."
            placeholder="300 123 4567"
            autoComplete="off"
            maxLength={20}
          />
          <button type="button" className="boton boton--secundario boton--bloque" onClick={enviarWhatsApp}>
            Enviar código por WhatsApp
          </button>
        </div>
      </section>

      <button type="button" className="boton boton--texto no-imprimir" onClick={onNuevo}>
        Registrar otro invitado
      </button>

      <TicketImpresion ticket={ticket} />
    </>
  );
}

// ---- Formulario --------------------------------------------------------------------

function FormularioInvitado({ onRegistrado }) {
  const [tipo, setTipo] = useState('carro');
  const [placa, setPlaca] = useState('');
  const [errorPlaca, setErrorPlaca] = useState(null);
  const [error, setError] = useState(null);
  const [enviando, setEnviando] = useState(false);
  const campoPlaca = useRef(null);

  function cambiarPlaca(valor) {
    const texto = valor.toUpperCase();
    setPlaca(texto);
    if (errorPlaca) setErrorPlaca(errorDePlaca(texto, tipo));
  }

  function cambiarTipo(nuevo) {
    setTipo(nuevo);
    if (errorPlaca) setErrorPlaca(errorDePlaca(placa, nuevo));
  }

  async function enviar(evento) {
    evento.preventDefault();
    setError(null);

    const errorFormato = errorDePlaca(placa, tipo);
    if (errorFormato) {
      setErrorPlaca(errorFormato);
      campoPlaca.current?.focus();
      return;
    }

    setEnviando(true);
    try {
      const { data } = await api.post('/api/accesos/invitados', { tipo, placa: normalizarPlaca(placa) });
      onRegistrado(data);
    } catch (e) {
      const info = errorPorteria(e);
      if (info.campos.placa) {
        setErrorPlaca(info.campos.placa);
        campoPlaca.current?.focus();
      } else {
        setError(info.campos.tipo ? { titulo: info.titulo, texto: info.campos.tipo } : info);
      }
      setEnviando(false);
    }
  }

  return (
    <form className="tarjeta" onSubmit={enviar} noValidate aria-labelledby="titulo-invitado">
      <h2 id="titulo-invitado" className="bloque__titulo">
        Datos del vehículo
      </h2>
      {error && (
        <Aviso tipo="error">
          <strong>{error.titulo}.</strong> {error.texto}
        </Aviso>
      )}
      <SelectorTipo valor={tipo} onCambiar={cambiarTipo} disabled={enviando} />
      <Campo
        ref={campoPlaca}
        etiqueta="Placa"
        name="placa"
        value={placa}
        onChange={(e) => cambiarPlaca(e.target.value)}
        error={errorPlaca}
        ayuda={`Por ejemplo ${ejemploPlaca(tipo)}. Puedes escribirla con o sin guion.`}
        placeholder={ejemploPlaca(tipo)}
        maxLength={9}
        autoComplete="off"
        autoCapitalize="characters"
        spellCheck={false}
        readOnly={enviando}
      />
      <button type="submit" className="boton boton--primario boton--bloque" disabled={enviando}>
        {enviando ? 'Registrando…' : 'Registrar ingreso'}
      </button>
    </form>
  );
}

// ---- Pantalla ----------------------------------------------------------------------

export default function Invitados() {
  const [ticket, setTicket] = useState(null);

  return (
    <div className="porteria">
      <header className="saludo no-imprimir">
        <h1 className="saludo__titulo">Invitados</h1>
        <p className="texto-suave">
          Registra el ingreso de un vehículo sin cuenta. Los invitados pagan la tarifa completa al
          salir.
        </p>
      </header>

      {ticket ? (
        <TicketInvitado ticket={ticket} onNuevo={() => setTicket(null)} />
      ) : (
        <FormularioInvitado onRegistrado={setTicket} />
      )}
    </div>
  );
}
