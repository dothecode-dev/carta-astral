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
import { limpiarRestosDeLectura } from "@/lib/lecturaLocal";
import { leerProcedencia } from "@/lib/procedencia";
import type { Moneda } from "@/lib/monedas";

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
  moneda,
}: {
  locale: Locale;
  dict: Dict;
  /** La moneda en que se mostró `precio`: la compra sin cuenta se cobra en esa (RF26). */
  moneda: Moneda;
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
  const [comprando, setComprando] = useState(false);
  const [errorCompra, setErrorCompra] = useState<string | null>(null);
  const datos = useRef<DatosCarta | null>(null);

  // La lectura anónima ya no existe: se van los datos de nacimiento que dejó.
  useEffect(limpiarRestosDeLectura, []);

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
      // De dónde llegó la visita: el servidor la reduce a canal y lugar y la
      // cuenta, sin guardar nada de la persona (lib/procedencia).
      body: JSON.stringify({ ...cuerpo, procedencia: leerProcedencia() }),
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
      const carta = (await res.json()) as CartaDibujable;
      setPreview(carta);
      setSending(false);
      // Una vez por carta calculada, cuando el teaser llega a la pantalla
      // (RF10). Es el denominador de «checkout_iniciado / carta». Sin teaser
      // (un backend viejo) no hay nada visto que medir.
      if (carta.teaser) {
        track("teaser_visto", { con_hora: cuerpo.time_known, secciones: carta.teaser.informe.secciones });
      }
      return;
    }

    track("carta_creada", { desde: "formulario" });

    // Directo a la carta recién calculada, que es lo que se vino a ver.
    const chart: { id?: string } = await res.json();
    router.replace(destinoDe(locale, chart.id));
    router.refresh();
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
        body: JSON.stringify({ ...datos.current, locale, moneda }),
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

  if (preview) {
    return (
      <CartaPreview
        carta={preview}
        dict={dict}
        locale={locale}
        onVolver={() => {
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
