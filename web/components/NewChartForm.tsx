"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Place } from "@/app/api/geocode/route";
import { PlaceField } from "@/components/PlaceField";
import type { Dict } from "@/lib/i18n";

// El formulario no calcula nada: junta los datos y se los manda al backend, que
// es el único que sabe de efemérides. Lo único que resuelve acá es que no se
// envíe algo que el backend va a rechazar.

export function NewChartForm({ locale, dict }: { locale: string; dict: Dict }) {
  const router = useRouter();
  const t = dict.newChart;

  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [timeUnknown, setTimeUnknown] = useState(false);
  const [place, setPlace] = useState<Place | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (sending) return;

    if (!date) return setError(t.needDate);
    const year = Number(date.slice(0, 4));
    if (year < 1800 || new Date(date) > new Date()) return setError(t.badDate);
    if (!place) return setError(t.needPlace);
    setError(null);
    setSending(true);

    const res = await fetch("/api/charts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name.trim() || null,
        date,
        // Sin hora, el backend calcula igual pero sin casas ni ángulos.
        time: timeUnknown ? null : time || null,
        time_known: !timeUnknown && Boolean(time),
        lat: place.lat,
        lng: place.lng,
        place_label: place.place_query,
      }),
    });

    if (!res.ok) {
      setSending(false);
      setError(res.status === 402 ? t.noCredits : t.failed);
      return;
    }

    // La carta ya existe: se ve en la cuenta, junto a las demás.
    router.replace(`/${locale}/cuenta`);
    router.refresh();
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

      <button type="submit" className="btn btnPrimary" disabled={sending}>
        {sending ? t.submitting : t.submit}
      </button>
    </form>
  );
}
