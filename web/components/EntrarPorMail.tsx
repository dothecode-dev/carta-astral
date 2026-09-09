"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { identificar, track } from "@/lib/telemetry";

// La puerta de acceso por mail — RF15/RF16. Un solo componente con dos pasos
// internos, sin ruta propia: así `next`, `comprar` y `cupon` siguen viajando
// en la URL de `/entrar` como con Google, y esta puerta no tiene que repetir
// esa lectura.
//
// Paso 1 ("pedir"): junta el mail y pide el código a POST /api/session/codigo.
// Paso 2 ("codigo"): junta el código de 6 dígitos y lo canjea contra POST
// /api/session, igual que hace GoogleSignIn con el id_token de Google — mismo
// patrón de fetch envuelto en try/catch, `identificar` envuelto aparte, y
// `router.replace` + `router.refresh()` al final.

/** Cuánto hay que esperar antes de poder reenviar (RF6): el backend manda el
 *  MISMO código, no uno nuevo, así que reenviar antes no ayuda y sólo gasta
 *  el límite de pedidos por hora del lado del servidor. */
const ESPERA_REENVIO_MS = 60_000;

type Paso = "pedir" | "codigo";

/** Motivo de un fallo, tal como lo espera `codigo_fallido` en la telemetría
 *  (Ruling 20). `invalido` sólo puede salir del canje (401): el pedido no
 *  tiene con qué fallar así. */
type Motivo = "invalido" | "demasiados" | "no_disponible" | "red";

function motivoDe(status: number): Motivo {
  if (status === 401) return "invalido";
  if (status === 429) return "demasiados";
  // 503/502 son los explícitos del backend; cualquier otro (400 mal armado,
  // etc.) cae acá también: no hay un quinto balde en la telemetría y no vale
  // la pena inventarlo para un caso que no debería pasar con los campos ya
  // validados del lado del cliente.
  return "no_disponible";
}

type Labels = {
  mailLabel: string;
  mailPlaceholder: string;
  mailButton: string;
  codigoLabel: string;
  codigoPlaceholder: string;
  /** Que puede tardar y que hay que mirar spam (RF15). */
  codigoHelp: string;
  codigoButton: string;
  enviando: string;
  reenviar: string;
  cambiarMail: string;
  codigoInvalido: string;
  demasiadosIntentos: string;
  noDisponible: string;
  errorRed: string;
};

type Sesion = { account_id?: number; destino?: string };

export function EntrarPorMail({
  locale,
  next,
  labels,
}: {
  locale: string;
  /** A dónde volver al entrar. Ya validado contra `destinoSeguro` por quien
   *  renderiza: acá llega una ruta interna o nada.
   *
   *  Se manda al PEDIR el código para que sobreviva el viaje a Mail (RF16).
   *  Al canjear, `next` sigue siendo el que manda: el `destino` que devuelve
   *  el canje es sólo el respaldo para cuando la persona volvió por una
   *  pestaña nueva y ese `next` original ya no está en la URL. */
  next?: string | null;
  labels: Labels;
}) {
  const router = useRouter();
  const [paso, setPaso] = useState<Paso>("pedir");
  const [email, setEmail] = useState("");
  const [codigo, setCodigo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [puedeReenviar, setPuedeReenviar] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  function armarEsperaDeReenvio() {
    setPuedeReenviar(false);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setPuedeReenviar(true), ESPERA_REENVIO_MS);
  }

  /** Pide (o reenvía) el código para `correo`. Común a los dos casos: el
   *  backend no distingue un pedido de un reenvío, es la misma ruta —
   *  `reenvio` es sólo para la telemetría (I4), nunca viaja al backend.
   *
   *  Arma la espera de 60s ANTES del fetch y para los dos desenlaces, no sólo
   *  el éxito (m6): si no, un 429 o un 503 dejaban `puedeReenviar` en lo que
   *  ya estaba —true, si el click vino del propio botón de reenviar— y el
   *  botón quedaba habilitado para martillarlo, cada clic gastando un pedido
   *  más contra el balde de C1. */
  async function pedirCodigo(correo: string, reenvio: boolean) {
    setEnviando(true);
    setError(null);
    armarEsperaDeReenvio();

    let res: Response;
    try {
      res = await fetch("/api/session/codigo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: correo, lang: locale, destino: next ?? "" }),
      });
    } catch (err) {
      // Igual que en GoogleSignIn: una red caída rechaza antes de devolver
      // respuesta, y sin este catch la persona se queda mirando el botón de
      // "enviando" para siempre.
      console.error("No se pudo llegar a /api/session/codigo:", err);
      setEnviando(false);
      setError(labels.errorRed);
      track("codigo_fallido", { paso: "pedido", motivo: "red" });
      return;
    }

    setEnviando(false);
    if (!res.ok) {
      const motivo = motivoDe(res.status);
      setError(motivo === "demasiados" ? labels.demasiadosIntentos : labels.noDisponible);
      track("codigo_fallido", { paso: "pedido", motivo });
      return;
    }

    setPaso("codigo");
    track("codigo_pedido", { reenvio });
  }

  async function onPedirSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const correo = email.trim();
    if (!correo || enviando) return;
    await pedirCodigo(correo, false);
  }

  async function onReenviar() {
    if (!puedeReenviar || enviando) return;
    // El mismo mail que se usó al pedir (RF6): no hay campo para cambiarlo
    // en este paso.
    await pedirCodigo(email.trim(), true);
  }

  async function onCodigoSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const codigoLimpio = codigo.trim();
    if (!codigoLimpio || enviando) return;

    setEnviando(true);
    setError(null);

    let res: Response;
    try {
      res = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: "email", email: email.trim(), codigo: codigoLimpio }),
      });
    } catch (err) {
      console.error("No se pudo llegar a /api/session:", err);
      setEnviando(false);
      setError(labels.errorRed);
      track("codigo_fallido", { paso: "canje", motivo: "red" });
      return;
    }

    setEnviando(false);
    if (!res.ok) {
      const motivo = motivoDe(res.status);
      // Un 401 deja el formulario tal cual: el código estaba mal o venció, y
      // la persona lo puede volver a escribir sin perder el mail ni el paso.
      setError(
        motivo === "invalido"
          ? labels.codigoInvalido
          : motivo === "demasiados"
            ? labels.demasiadosIntentos
            : labels.noDisponible,
      );
      track("codigo_fallido", { paso: "canje", motivo });
      return;
    }

    // La sesión ya es válida en este punto: un cuerpo ilegible cuesta la
    // identificación, jamás el login. Ver GoogleSignIn.
    let sesion: Sesion = {};
    try {
      sesion = await res.json();
      if (typeof sesion.account_id === "number") identificar(sesion.account_id);
    } catch (error) {
      // Ver arriba: sin id no hay a quién atribuir, y se sigue de largo.
      // Sólo el motivo del error, nunca `sesion`, el mail ni el código.
      console.error("No se pudo leer la respuesta de /api/session:", error);
    }

    track("codigo_canjeado", {});
    // El evento del embudo compartido con las otras dos puertas (Ruling 20):
    // sin esto el embudo de login deja de cerrar para quien entra por mail.
    track("login", { provider: "email" });

    router.replace(next ?? sesion.destino ?? `/${locale}/cuenta`);
    router.refresh();
  }

  function volverAPedir() {
    if (timer.current) clearTimeout(timer.current);
    setPaso("pedir");
    setCodigo("");
    setError(null);
  }

  if (paso === "pedir") {
    return (
      <form className="form" onSubmit={onPedirSubmit}>
        <div className="field">
          <label className="fieldLabel" htmlFor="entrar-mail">
            {labels.mailLabel}
          </label>
          <input
            id="entrar-mail"
            className="input"
            type="email"
            autoComplete="email"
            placeholder={labels.mailPlaceholder}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={enviando}
            required
          />
        </div>
        {error && (
          <p className="formError" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="btn btnPrimary" disabled={enviando}>
          {enviando ? labels.enviando : labels.mailButton}
        </button>
      </form>
    );
  }

  return (
    <form className="form" onSubmit={onCodigoSubmit}>
      <div className="field">
        <label className="fieldLabel" htmlFor="entrar-codigo">
          {labels.codigoLabel}
        </label>
        <input
          id="entrar-codigo"
          className="input"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder={labels.codigoPlaceholder}
          value={codigo}
          onChange={(e) => setCodigo(e.target.value)}
          disabled={enviando}
          required
        />
      </div>
      <p className="fieldNote">{labels.codigoHelp}</p>
      {error && (
        <p className="formError" role="alert">
          {error}
        </p>
      )}
      <div className="authMailActions">
        <button type="submit" className="btn btnPrimary" disabled={enviando}>
          {enviando ? labels.enviando : labels.codigoButton}
        </button>
        <button
          type="button"
          className="linkButton"
          onClick={onReenviar}
          disabled={!puedeReenviar || enviando}
        >
          {labels.reenviar}
        </button>
        <button type="button" className="linkButton" onClick={volverAPedir} disabled={enviando}>
          {labels.cambiarMail}
        </button>
      </div>
    </form>
  );
}
