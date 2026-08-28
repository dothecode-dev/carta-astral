"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { SolarSystem } from "@/components/SolarSystem";
import type { Dict, Locale } from "@/lib/i18n";
import { track } from "@/lib/telemetry";

// El botón que gasta el crédito, y la espera mientras se escribe el informe.
//
// El informe tiene ocho secciones (RF1) y el backend las escribe en un hilo
// aparte (RF10): el POST devuelve 202 al instante y esto sondea
// `interpretation/estado` hasta que están todas. Tarda unos cuatro minutos.

/** Cada cuánto se pregunta cuánto avanzó el informe mientras se escribe. */
export const POLL_MS = 5000;
/**
 * Tope de esa espera, en consultas: once minutos.
 *
 * El informe tarda ~4 minutos; el tope viejo (24 intentos × 5 s = 2 minutos)
 * se quedaba corto y la web se rendía en medio de una generación normal.
 */
export const POLL_TRIES = 132;

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

export function ChartActions({
  locale,
  chartId,
  langs,
  timeKnown,
  dict,
}: {
  locale: Locale;
  chartId: string;
  langs: string[];
  /** RF12: si la carta no tiene hora, el informe sale sin la sección de casas. */
  timeKnown: boolean;
  dict: Dict;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  // `router.refresh()` no avisa cuándo terminó. Envuelto en una transición,
  // `refrescando` dice cuándo el servidor ya devolvió la lectura: sin eso la
  // animación se quedaba encendida para siempre debajo del texto ya escrito.
  const [refrescando, startTransition] = useTransition();
  const [progreso, setProgreso] = useState<{ hechas: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const yaLeida = langs.includes(locale);
  // Si ya existe en otro idioma, traducirla no cuesta: el backend no vuelve a
  // cobrar. Decir "usa 1 crédito" ahí sería mentir, y es lo que hace la app.
  const enOtroIdioma = !yaLeida && langs.length > 0;

  /**
   * Sondea cuántas de las ocho secciones ya están escritas, hasta que el
   * informe está completo.
   *
   * El POST sólo arranca la generación (RF10): responde 202 y el texto real
   * tarda varios minutos en un hilo de fondo. Sin este sondeo la web no
   * tendría forma de saber cuándo terminó, ni nada real que mostrar mientras
   * tanto.
   */
  async function waitForReading(): Promise<boolean> {
    for (let intento = 0; intento < POLL_TRIES; intento++) {
      await sleep(POLL_MS);
      const res = await fetch(`/api/charts/${chartId}/interpretation/estado?lang=${locale}`);
      if (!res.ok) continue;
      const estado = (await res.json()) as { completa: boolean; hechas: number; total: number };
      setProgreso({ hechas: estado.hechas, total: estado.total });
      if (estado.completa) return true;
    }
    return false;
  }

  async function interpret() {
    setProgreso(null);
    setBusy(true);
    setError(null);

    const res = await fetch(`/api/charts/${chartId}/interpretation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lang: locale }),
    });

    if (!res.ok) {
      setBusy(false);
      setError(res.status === 402 ? dict.chart.noCredits : dict.chart.failed);
      return;
    }

    // El POST arrancó el hilo de fondo y respondió 202: la lectura todavía no
    // existe. Si el sondeo se agota, se avisa y se deja reintentar (RF7): un
    // botón que desaparece para siempre sería peor que un informe tardío.
    if (!(await waitForReading())) {
      setBusy(false);
      setError(dict.chart.failed);
      return;
    }

    track("interpretacion_generada", { lang: locale });

    // La lectura queda debajo de la carta, en esta misma página. La animación
    // sigue hasta que el refresh trae el texto, no hasta que el informe está.
    startTransition(() => router.refresh());
    setBusy(false);
  }

  if (busy || refrescando) {
    return (
      <section className="waiting">
        <SolarSystem size={200} speed={2.5} />
        <div className="waitingCopy">
          <h2 className="display waitingTitle">{dict.chart.waitTitle}</h2>
          <p className="waitingBody">
            {progreso
              ? dict.chart.waitProgress
                  .replace("{hechas}", String(progreso.hechas))
                  .replace("{total}", String(progreso.total))
              : dict.chart.waitBody}
          </p>
        </div>
      </section>
    );
  }

  if (yaLeida) return null;

  return (
    <div className="chartActions">
      <button type="button" className="btn btnPrimary" onClick={interpret}>
        {dict.chart.interpret}
      </button>
      <p className="fieldNote">
        {enOtroIdioma ? dict.chart.interpretFreeLang : dict.chart.interpretCost}
      </p>
      {!timeKnown && <p className="fieldNote">{dict.chart.noTimeWarning}</p>}
      {error && (
        <p className="formError" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
