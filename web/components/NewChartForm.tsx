"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { Place } from "@/app/api/geocode/route";
import { CartaPreview } from "@/components/CartaPreview";
import { track } from "@/lib/telemetry";
import { PlaceField } from "@/components/PlaceField";
import type { CartaDibujable } from "@/lib/chart";
import { armarDatosCarta, errorDeFecha, TRATOS, type DatosCarta, type Trato } from "@/lib/datosCarta";
import type { Dict, Locale } from "@/lib/i18n";
import { leerLectura, type LecturaGuardada } from "@/lib/lecturaLocal";
import { useLecturaAnonima } from "@/components/useLecturaAnonima";

// El formulario no calcula nada: junta los datos y se los manda al backend, que
// es el único que sabe de efemérides. Lo único que resuelve acá es que no se
// envíe algo que el backend va a rechazar.
//
// Tiene dos modos, y la diferencia es de dónde viene quien está mirando:
//
// - Con sesión, calcula y guarda: la carta queda en la cuenta y se va derecho
//   a ella, que es lo que se vino a hacer.
// - Sin sesión, calcula y muestra, sin guardar nada. Hasta el 04-09-2026 esta
//   página redirigía al login antes de mostrar nada, así que el visitante frío
//   —el de Instagram, el de una búsqueda— tenía que crear una cuenta para ver
//   si el sitio servía. Ahora ve SU carta y la cuenta se pide para la lectura,
//   que es lo que cuesta plata.

/** Dónde espera la carta calculada mientras la persona pasa por el login.
 *
 * `sessionStorage` y no `localStorage`: son datos de nacimiento, y su vida
 * útil es exactamente la del viaje de ida y vuelta al login. Muere con la
 * pestaña aunque algo falle en el medio. */
const PENDIENTE = "astra-carta-pendiente";
const TRATO_CLAVE = {
  femenino: "tratoFemenino",
  masculino: "tratoMasculino",
  neutro: "tratoNeutro",
} as const;

/** A la carta recién calculada. Ahí se elige qué leer: calcularla no gasta nada. */
function destinoDe(locale: Locale, id: string | undefined): string {
  if (!id) return `/${locale}/cuenta`;
  return `/${locale}/carta/${id}`;
}

/** De quién es una lectura guardada, para el botón de «verla»: el nombre que
 *  puso o, si no puso, la fecha de nacimiento. */
function quienDe(datos: DatosCarta): string {
  return datos.name || datos.date;
}

async function motivoDe(res: Response): Promise<string | null> {
  try {
    const cuerpo = (await res.json()) as { motivo?: unknown };
    return typeof cuerpo.motivo === "string" ? cuerpo.motivo : null;
  } catch {
    return null;
  }
}

export function NewChartForm({
  locale,
  dict,
  signedIn = false,
  precio = null,
}: {
  locale: Locale;
  dict: Dict;
  signedIn?: boolean;
  /** Precio del informe ya formateado; `null` si el catálogo no respondió. */
  precio?: string | null;
}) {
  const router = useRouter();
  const t = dict.newChart;

  const [name, setName] = useState("");
  const [trato, setTrato] = useState<Trato>("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [timeUnknown, setTimeUnknown] = useState(false);
  const [place, setPlace] = useState<Place | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [preview, setPreview] = useState<CartaDibujable | null>(null);
  const [retomando, setRetomando] = useState(false);
  const [comprando, setComprando] = useState(false);
  const [errorCompra, setErrorCompra] = useState<string | null>(null);
  const datos = useRef<DatosCarta | null>(null);
  const lectura = useLecturaAnonima();
  // La lectura breve guardada en este navegador (RF8). Se lee en un efecto:
  // `localStorage` no existe en el servidor y leerlo en el render rompería la
  // hidratación. Se relee cada vez que el hook guarda una —también la que
  // termina de fondo después de que la persona volvió al formulario—, así
  // «Ver tu lectura de …» aparece sin recargar.
  const [guardada, setGuardada] = useState<LecturaGuardada | null>(null);
  const { guardadas } = lectura;
  useEffect(() => {
    if (signedIn) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setGuardada(leerLectura());
  }, [signedIn, guardadas]);

  // Vuelve del login con una carta que ya vio: se la guardamos y la llevamos a
  // ella. El `sessionStorage` se limpia ANTES de crear nada —y hay un guard de
  // una sola corrida— porque en desarrollo React monta dos veces y dos altas
  // dejarían la carta duplicada en la cuenta.
  const retomado = useRef(false);
  useEffect(() => {
    if (!signedIn || retomado.current) return;
    retomado.current = true;

    let guardado: string | null = null;
    try {
      guardado = sessionStorage.getItem(PENDIENTE);
      sessionStorage.removeItem(PENDIENTE);
    } catch {
      // Storage bloqueado: no hay nada que retomar, se muestra el formulario.
      return;
    }
    if (!guardado) return;

    // El lint desaconseja `setState` síncrono dentro de un efecto, y con
    // razón; acá es la excepción que la propia regla contempla: el dato vive
    // en un sistema externo (`sessionStorage`) que no existe en el servidor.
    // Leerlo durante el render haría que el primer render del cliente no
    // coincida con el HTML del servidor —que muestra el formulario— y eso es
    // un error de hidratación, peor que un render de más.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRetomando(true);
    void (async () => {
      try {
        const res = await fetch("/api/charts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: guardado,
        });
        if (!res.ok) throw new Error(String(res.status));
        track("carta_creada", { desde: "preview" });
        const chart: { id?: string } = await res.json();
        router.replace(destinoDe(locale, chart.id));
        router.refresh();
      } catch {
        // El formulario sigue ahí y los datos están a un tipeo: mejor eso que
        // una pantalla de error sin salida.
        setRetomando(false);
        setError(t.failed);
      }
    })();
  }, [signedIn, locale, router, t.failed]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (sending) return;

    const errorFecha = errorDeFecha(date);
    if (errorFecha) return setError(t[errorFecha]);
    if (!place) return setError(t.needPlace);
    setError(null);
    setSending(true);

    const cuerpo: DatosCarta = armarDatosCarta({
      name: name.trim() || null,
      date,
      time,
      timeUnknown,
      place,
      trato,
    });

    const res = await fetch(signedIn ? "/api/charts" : "/api/charts/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });

    if (!res.ok) {
      setSending(false);
      if (res.status === 429) return setError(t.failed);
      setError(res.status === 402 ? t.sinLeerBreve : t.failed);
      return;
    }

    // Sin propiedades que identifiquen: el nombre, la fecha y el lugar que se
    // acaban de cargar son exactamente lo que la política promete no mandar.
    track("carta_calculada", { con_sesion: signedIn });

    if (!signedIn) {
      datos.current = cuerpo;
      setPreview((await res.json()) as CartaDibujable);
      setSending(false);
      return;
    }

    track("carta_creada", { desde: "formulario" });

    // Directo a la carta recién calculada, que es lo que se vino a ver.
    const chart: { id?: string } = await res.json();
    router.replace(destinoDe(locale, chart.id));
    router.refresh();
  }

  /** Quiere la lectura: se escribe acá mismo, sin cuenta (spec 2026-10-08). */
  function pedirLectura() {
    if (!datos.current || !preview) return;
    void lectura.pedir(datos.current, preview, locale);
  }

  /** Paga el informe sin crear cuenta antes (pagar es entrar): la carta de la
   *  vista previa viaja al backend, que abre Stripe. El nonce de la vuelta
   *  queda en una cookie httpOnly puesta por `/api/checkout/anonimo`. */
  async function comprarSinCuenta() {
    if (comprando || !datos.current) return;
    setComprando(true);
    setErrorCompra(null);
    // Antes de salir del sitio, como en `ComprarBoton`. `anonimo` separa esta
    // puerta de las otras; PostHog une al visitante con la cuenta cuando la
    // carta, ya con sesión, llama a `identify`.
    track("checkout_iniciado", { producto: "informe_natal", desde: "carta", anonimo: true });
    try {
      const res = await fetch("/api/checkout/anonimo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...datos.current, locale }),
      });
      if (!res.ok) {
        setComprando(false);
        const motivo = res.status === 400 ? await motivoDe(res) : null;
        setErrorCompra(
          motivo === "requiere_cuenta"
            ? t.comprarRequiereCuenta
            : (motivo && dict.precios.cuponMotivo[motivo]) || dict.precios.fallo,
        );
        return;
      }
      const { url } = (await res.json()) as { url: string };
      // El checkout de Stripe es otro sitio: no es una navegación de Next.
      window.location.assign(url);
    } catch {
      setComprando(false);
      setErrorCompra(dict.precios.fallo);
    }
  }

  if (retomando) {
    return (
      <p className="formLede" role="status">
        {t.previewRetomando}
      </p>
    );
  }

  if (preview) {
    return (
      <CartaPreview
        carta={preview}
        dict={dict}
        locale={locale}
        lectura={lectura.estado}
        onPedirLectura={pedirLectura}
        onReintentar={pedirLectura}
        onVolver={() => {
          lectura.reiniciar();
          if (!signedIn) setGuardada(leerLectura());
          setPreview(null);
          setErrorCompra(null);
        }}
        precio={precio}
        onComprar={comprarSinCuenta}
        comprando={comprando}
        errorCompra={errorCompra}
      />
    );
  }

  return (
    <form className="form" onSubmit={submit} noValidate>
      {guardada && !signedIn && (
        <button
          type="button"
          className="btn btnGhost"
          onClick={() => {
            // Sin esto el botón de comprar de la vista reabierta no tendría
            // con qué abrir el checkout.
            datos.current = guardada.datos;
            setPreview(guardada.carta);
            lectura.mostrar(guardada);
          }}
        >
          {t.lecturaVerAnterior.replace("{quien}", quienDe(guardada.datos))}
        </button>
      )}

      <div className="field">
        <label className="fieldLabel" htmlFor="chart-name">
          {t.name}
        </label>
        <input
          id="chart-name"
          className="input"
          type="text"
          value={name}
          placeholder={t.namePlaceholder}
          onChange={(e) => setName(e.target.value)}
        />
        <p className="fieldNote">{t.nameHint}</p>
      </div>

      <div className="field">
        <label className="fieldLabel" htmlFor="chart-trato">
          {t.tratoLabel}
        </label>
        <select
          id="chart-trato"
          className="input"
          value={trato}
          onChange={(e) => setTrato(e.target.value as Trato)}
        >
          <option value="">{t.tratoVacio}</option>
          {TRATOS.map((v) => (
            <option key={v} value={v}>
              {t[TRATO_CLAVE[v]]}
            </option>
          ))}
        </select>
        <p className="fieldNote">{t.tratoNota}</p>
      </div>

      <div className="fieldRow">
        <div className="field">
          <label className="fieldLabel" htmlFor="chart-date">
            {t.date}
          </label>
          <input
            id="chart-date"
            className="input"
            type="date"
            required
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>

        <div className="field">
          <label className="fieldLabel" htmlFor="chart-time">
            {t.time}
          </label>
          <input
            id="chart-time"
            className="input"
            type="time"
            value={time}
            disabled={timeUnknown}
            onChange={(e) => setTime(e.target.value)}
          />
        </div>
      </div>

      <div className="checkboxField">
        <label className="checkboxLabel">
          <input
            type="checkbox"
            checked={timeUnknown}
            onChange={(e) => setTimeUnknown(e.target.checked)}
          />
          {t.timeUnknown}
        </label>
        {timeUnknown && <p className="fieldNote">{t.timeUnknownHint}</p>}
      </div>

      <PlaceField
        value={place}
        onSelect={setPlace}
        labels={{
          label: t.place,
          placeholder: t.placePlaceholder,
          searching: t.searching,
          empty: t.noPlaces,
          change: t.changePlace,
        }}
      />

      {error && (
        <p className="formError" role="alert">
          {error}
        </p>
      )}

      <button type="submit" className="btn btnPrimary" disabled={sending}>
        {sending ? t.submitting : t.submit}
      </button>
    </form>
  );
}
