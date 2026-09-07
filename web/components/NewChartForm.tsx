"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { Place } from "@/app/api/geocode/route";
import { CartaPreview } from "@/components/CartaPreview";
import { track } from "@/lib/telemetry";
import { PlaceField } from "@/components/PlaceField";
import type { CartaDibujable } from "@/lib/chart";
import type { Dict, Locale } from "@/lib/i18n";
import type { Usar } from "@/lib/usar";

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

/** Los datos del formulario, tal como los espera el backend. */
type DatosCarta = {
  name: string | null;
  date: string;
  time: string | null;
  time_known: boolean;
  lat: number;
  lng: number;
  place_label: string;
};

/** Dónde espera la carta calculada mientras la persona pasa por el login.
 *
 * `sessionStorage` y no `localStorage`: son datos de nacimiento, y su vida
 * útil es exactamente la del viaje de ida y vuelta al login. Muere con la
 * pestaña aunque algo falle en el medio. */
const PENDIENTE = "astra-carta-pendiente";
/** Lo que se venía a usar en la carta nueva (`?usar=`), para que el viaje al
 *  login no lo pierda. Aparte de los datos, que viajan tal cual al backend. */
const USAR_PENDIENTE = "astra-usar-pendiente";

/** A la carta recién calculada, con lo que se venía a usar en ella. */
function destinoDe(locale: Locale, id: string | undefined, usar: Usar | null): string {
  if (!id) return `/${locale}/cuenta`;
  return `/${locale}/carta/${id}${usar ? `?usar=${encodeURIComponent(usar)}` : ""}`;
}

export function NewChartForm({
  locale,
  dict,
  signedIn = false,
  usar = null,
  disponibles = null,
}: {
  locale: Locale;
  dict: Dict;
  signedIn?: boolean;
  /** Qué se venía a usar en la carta (`?usar=`, «Usar en una carta nueva»
   *  desde la cuenta). Ya validado por la página contra la lista cerrada. Sólo
   *  cuenta si hay algo disponible: tecleado a mano sin derecho, se ignora. */
  usar?: Usar | null;
  /** Cuántas lecturas breves y cuántos informes tiene la cuenta, si la página
   *  lo sabe. Con algo disponible, el formulario ofrece elegir qué hacer con
   *  la carta antes de calcularla. */
  disponibles?: { lectura_breve: number; informe_natal: number } | null;
}) {
  const router = useRouter();
  const t = dict.newChart;

  // Qué hacer con la carta al calcularla. La opción elegida es el aviso: un
  // informe pago no se gasta sin que la pantalla lo diga. Sin nada disponible
  // no se ofrece nada, y el `?usar=` de la URL sólo preselecciona lo que hay.
  const ofrece = Boolean(disponibles && (disponibles.lectura_breve > 0 || disponibles.informe_natal > 0));
  const [usarElegido, setUsarElegido] = useState<Usar | null>(
    disponibles && usar && disponibles[usar] > 0 ? usar : null,
  );

  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [timeUnknown, setTimeUnknown] = useState(false);
  const [place, setPlace] = useState<Place | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [preview, setPreview] = useState<CartaDibujable | null>(null);
  const [retomando, setRetomando] = useState(false);
  const datos = useRef<DatosCarta | null>(null);

  // Vuelve del login con una carta que ya vio: se la guardamos y la llevamos a
  // ella. El `sessionStorage` se limpia ANTES de crear nada —y hay un guard de
  // una sola corrida— porque en desarrollo React monta dos veces y dos altas
  // dejarían la carta duplicada en la cuenta.
  const retomado = useRef(false);
  useEffect(() => {
    if (!signedIn || retomado.current) return;
    retomado.current = true;

    let guardado: string | null = null;
    let usarGuardado: Usar | null = null;
    try {
      guardado = sessionStorage.getItem(PENDIENTE);
      sessionStorage.removeItem(PENDIENTE);
      const u = sessionStorage.getItem(USAR_PENDIENTE);
      sessionStorage.removeItem(USAR_PENDIENTE);
      usarGuardado = u === "lectura_breve" || u === "informe_natal" ? u : null;
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
        router.replace(destinoDe(locale, chart.id, usarGuardado));
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

    if (!date) return setError(t.needDate);
    const year = Number(date.slice(0, 4));
    if (year < 1800 || new Date(date) > new Date()) return setError(t.badDate);
    if (!place) return setError(t.needPlace);
    setError(null);
    setSending(true);

    const cuerpo: DatosCarta = {
      name: name.trim() || null,
      date,
      // Sin hora, el backend calcula igual pero sin casas ni ángulos.
      time: timeUnknown ? null : time || null,
      time_known: !timeUnknown && Boolean(time),
      lat: place.lat,
      lng: place.lng,
      place_label: place.place_query,
    };

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
    router.replace(destinoDe(locale, chart.id, ofrece ? usarElegido : null));
    router.refresh();
  }

  /** Quiere la lectura: acá recién aparece el registro. */
  function pedirLectura() {
    try {
      if (datos.current) sessionStorage.setItem(PENDIENTE, JSON.stringify(datos.current));
      if (usar) sessionStorage.setItem(USAR_PENDIENTE, usar);
    } catch {
      // Sin storage se pierde lo cargado y hay que reescribirlo después de
      // entrar. Peor sería no dejarlo entrar.
    }
    track("lectura_pedida_sin_cuenta", {});
    router.push(`/${locale}/entrar?next=${encodeURIComponent(`/${locale}/nueva`)}`);
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
        onPedirLectura={pedirLectura}
        onVolver={() => setPreview(null)}
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

      {/* Calcular la carta no genera ninguna lectura: con sesión y algo
          disponible, se elige acá qué hacer con ella. Por defecto, nada: se
          decide en la carta, que es donde siempre se pudo. */}
      {ofrece && disponibles && (
        <fieldset className="formUsar">
          <legend className="fieldLabel">{t.alCalcularla}</legend>
          <label className="formUsarOpcion">
            <input
              type="radio"
              name="usar"
              checked={usarElegido === null}
              onChange={() => setUsarElegido(null)}
            />
            <span>{t.decidoEnLaCarta}</span>
          </label>
          {disponibles.informe_natal > 0 && (
            <label className="formUsarOpcion">
              <input
                type="radio"
                name="usar"
                checked={usarElegido === "informe_natal"}
                onChange={() => setUsarElegido("informe_natal")}
              />
              <span>{t.usarInforme.replace("{n}", String(disponibles.informe_natal))}</span>
            </label>
          )}
          {disponibles.lectura_breve > 0 && (
            <label className="formUsarOpcion">
              <input
                type="radio"
                name="usar"
                checked={usarElegido === "lectura_breve"}
                onChange={() => setUsarElegido("lectura_breve")}
              />
              <span>{t.leerBreve.replace("{n}", String(disponibles.lectura_breve))}</span>
            </label>
          )}
        </fieldset>
      )}

      <button type="submit" className="btn btnPrimary" disabled={sending}>
        {sending ? t.submitting : t.submit}
      </button>
    </form>
  );
}
