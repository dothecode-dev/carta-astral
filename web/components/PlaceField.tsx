"use client";

import { useEffect, useId, useRef, useState } from "react";

import type { Place } from "@/app/api/geocode/route";

// Buscador de lugar de nacimiento. Es lo único del formulario que va y vuelve
// al servidor mientras se escribe, así que espera a que la persona deje de
// teclear y cancela la búsqueda anterior si escribe otra letra.

const DEBOUNCE_MS = 300;
const MIN_CHARS = 3;

export function PlaceField({
  value,
  onSelect,
  labels,
}: {
  value: Place | null;
  onSelect: (place: Place | null) => void;
  labels: { label: string; placeholder: string; searching: string; empty: string; change: string };
}) {
  const [query, setQuery] = useState("");
  const [fetched, setFetched] = useState<Place[] | null>(null);
  const [searching, setSearching] = useState(false);
  const listId = useId();
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    if (value) return;
    const q = query.trim();
    // Con menos de tres letras no se busca; lo que ya se hubiera traído se
    // descarta al renderizar, sin tocar el estado desde acá.
    if (q.length < MIN_CHARS) return;

    const timer = window.setTimeout(async () => {
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      setSearching(true);
      try {
        const res = await fetch("/api/geocode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ q }),
          signal: controller.signal,
        });
        const data: { results?: Place[] } = await res.json();
        setFetched(data.results ?? []);
      } catch {
        // Cancelada por una tecla nueva, o sin red: no se pisa lo que ya se ve.
      } finally {
        if (!controller.signal.aborted) setSearching(false);
      }
    }, DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [query, value]);

  const results = query.trim().length >= MIN_CHARS ? fetched : null;

  if (value) {
    return (
      <div className="field">
        <span className="fieldLabel">{labels.label}</span>
        <div className="placeChosen">
          <span>{value.place_query}</span>
          <button
            type="button"
            className="linkButton"
            onClick={() => {
              onSelect(null);
              setQuery("");
              setFetched(null);
            }}
          >
            {labels.change}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="field">
      <label className="fieldLabel" htmlFor={listId}>
        {labels.label}
      </label>
      <input
        id={listId}
        className="input"
        type="text"
        autoComplete="off"
        placeholder={labels.placeholder}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      {searching && <p className="fieldNote">{labels.searching}</p>}

      {results !== null && results.length === 0 && !searching && (
        <p className="fieldNote">{labels.empty}</p>
      )}

      {results !== null && results.length > 0 && (
        <ul className="placeList">
          {results.map((place) => (
            <li key={`${place.lat},${place.lng}`}>
              <button type="button" className="placeOption" onClick={() => onSelect(place)}>
                <span>{place.place_query}</span>
                {place.tz_name && <span className="placeTz">{place.tz_name}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
