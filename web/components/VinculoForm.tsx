"use client";

import { useState } from "react";

import type { Place } from "@/app/api/geocode/route";
import { PlaceField } from "@/components/PlaceField";
import { VINCULO } from "@/content/vinculo";
import { armarDatosCarta, errorDeFecha } from "@/lib/datosCarta";
import type { Dict, Locale } from "@/lib/i18n";
import { track } from "@/lib/telemetry";
import {
  TIPOS_VINCULO,
  type MotivoFallo,
  type TipoVinculo,
  type VinculoPreview,
} from "@/lib/vinculo";

// El formulario de las dos personas de un vínculo. No calcula nada: junta los
// datos y se los manda al backend, igual que `NewChartForm`, y comparte con él
// cómo se arma el cuerpo y cómo se valida la fecha (`lib/datosCarta.ts`).
//
// El alias vive sólo acá: sirve para que quien mira reconozca a cada persona en
// el resultado, y nunca viaja. Son dos personas que no aceptaron nada y una de
// ellas ni siquiera está usando el sitio.

type Persona = {
  alias: string;
  date: string;
  time: string;
  timeUnknown: boolean;
  place: Place | null;
};

const VACIA: Persona = { alias: "", date: "", time: "", timeUnknown: false, place: null };

/** Del status y del cuerpo de una respuesta fallida, al motivo que se muestra.
 *  Sólo `misma_persona` es un motivo que el servidor puede dictar: cualquier
 *  otra cosa que diga se reduce a un motivo conocido, nunca se muestra tal cual. */
function motivoDe(status: number, cuerpo: unknown): MotivoFallo {
  if (status === 429) return "demasiadas";
  if (status === 400) {
    const error = (cuerpo as { error?: unknown } | null)?.error;
    return error === "misma_persona" ? "misma_persona" : "datos_invalidos";
  }
  return "no_disponible";
}

export function VinculoForm({
  locale,
  dict,
  onResultado,
}: {
  locale: Locale;
  dict: Dict;
  onResultado: (
    preview: VinculoPreview,
    tipo: TipoVinculo,
    alias: { a: string; b: string },
  ) => void;
}) {
  const t = VINCULO[locale];
  const nc = dict.newChart;

  const [tipo, setTipo] = useState<TipoVinculo>("pareja");
  const [a, setA] = useState<Persona>(VACIA);
  const [b, setB] = useState<Persona>(VACIA);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const completo = Boolean(a.date && a.place && b.date && b.place);

  function fallo(motivo: MotivoFallo) {
    track("vinculo_preview_fallido", { motivo });
    setError(t.errores[motivo]);
    setSending(false);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (sending) return;

    for (const persona of [a, b]) {
      const errorFecha = errorDeFecha(persona.date);
      if (errorFecha) return setError(nc[errorFecha]);
    }
    if (!a.place || !b.place) return setError(nc.needPlace);
    setError(null);
    setSending(true);

    // `name: null` siempre: el alias no sale de este componente.
    const datos = (p: Persona, place: Place) =>
      armarDatosCarta({ name: null, date: p.date, time: p.time, timeUnknown: p.timeUnknown, place });

    let res: Response;
    try {
      res = await fetch("/api/vinculo/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lang: locale, a: datos(a, a.place), b: datos(b, b.place) }),
      });
    } catch {
      return fallo("no_disponible");
    }

    if (!res.ok) {
      const cuerpo: unknown = await res.json().catch(() => null);
      return fallo(motivoDe(res.status, cuerpo));
    }

    const preview = (await res.json()) as VinculoPreview;
    setSending(false);
    onResultado(preview, tipo, { a: a.alias.trim(), b: b.alias.trim() });
  }

  return (
    <form className="form" onSubmit={submit} noValidate>
      <div className="field">
        <label className="fieldLabel" htmlFor="vinculo-tipo">
          {t.tipoLabel}
        </label>
        <select
          id="vinculo-tipo"
          className="input"
          value={tipo}
          onChange={(e) => setTipo(e.target.value as TipoVinculo)}
        >
          {TIPOS_VINCULO.map((codigo) => (
            <option key={codigo} value={codigo}>
              {t.tipos[codigo]}
            </option>
          ))}
        </select>
      </div>

      <PersonaCampos id="a" legend={t.personaA} persona={a} onChange={setA} dict={dict} locale={locale} />
      <PersonaCampos id="b" legend={t.personaB} persona={b} onChange={setB} dict={dict} locale={locale} />

      {error && (
        <p className="formError" role="alert">
          {error}
        </p>
      )}

      <button type="submit" className="btn btnPrimary" disabled={!completo || sending}>
        {sending ? t.calculando : t.calcular}
      </button>
      <p className="fieldNote">{t.privacidad}</p>
    </form>
  );
}

function PersonaCampos({
  id,
  legend,
  persona,
  onChange,
  dict,
  locale,
}: {
  id: string;
  legend: string;
  persona: Persona;
  onChange: (p: Persona) => void;
  dict: Dict;
  locale: Locale;
}) {
  const t = VINCULO[locale];
  const nc = dict.newChart;
  const set = <K extends keyof Persona>(clave: K, valor: Persona[K]) =>
    onChange({ ...persona, [clave]: valor });

  return (
    <fieldset className="vinculoPersona">
      <legend className="fieldLabel">{legend}</legend>

      <div className="field">
        <label className="fieldLabel" htmlFor={`vinculo-${id}-alias`}>
          {t.alias}
        </label>
        <input
          id={`vinculo-${id}-alias`}
          className="input"
          type="text"
          value={persona.alias}
          onChange={(e) => set("alias", e.target.value)}
        />
        <p className="fieldNote">{t.aliasHint}</p>
      </div>

      <div className="fieldRow">
        <div className="field">
          <label className="fieldLabel" htmlFor={`vinculo-${id}-date`}>
            {nc.date}
          </label>
          <input
            id={`vinculo-${id}-date`}
            className="input"
            type="date"
            required
            value={persona.date}
            onChange={(e) => set("date", e.target.value)}
          />
        </div>

        <div className="field">
          <label className="fieldLabel" htmlFor={`vinculo-${id}-time`}>
            {nc.time}
          </label>
          <input
            id={`vinculo-${id}-time`}
            className="input"
            type="time"
            value={persona.time}
            disabled={persona.timeUnknown}
            onChange={(e) => set("time", e.target.value)}
          />
        </div>
      </div>

      <div className="checkboxField">
        <label className="checkboxLabel">
          <input
            type="checkbox"
            checked={persona.timeUnknown}
            onChange={(e) => set("timeUnknown", e.target.checked)}
          />
          {nc.timeUnknown}
        </label>
        {persona.timeUnknown && <p className="fieldNote">{nc.timeUnknownHint}</p>}
      </div>

      <PlaceField
        value={persona.place}
        onSelect={(place) => set("place", place)}
        labels={{
          label: nc.place,
          placeholder: nc.placePlaceholder,
          searching: nc.searching,
          empty: nc.noPlaces,
          change: nc.changePlace,
        }}
      />
    </fieldset>
  );
}
