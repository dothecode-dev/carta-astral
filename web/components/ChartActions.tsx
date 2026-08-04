"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { SolarSystem } from "@/components/SolarSystem";
import type { Dict, Locale } from "@/lib/i18n";

// El botón que gasta el crédito, y la espera mientras se escribe la lectura.
//
// La espera es la misma coreografía que la app: el sistema solar girando y tres
// pasos que se encienden. La generación real tarda unos 25-30 segundos; los
// pasos no miden nada, acompañan.

const STEP_MS = 9000;
/** Cada cuánto se pregunta si la lectura ya está, mientras otra petición la escribe. */
const POLL_MS = 5000;
/** Techo de esa espera, en consultas: dos minutos. Después, algo salió mal de verdad. */
const POLL_TRIES = 24;

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

export function ChartActions({
  locale,
  chartId,
  langs,
  dict,
}: {
  locale: Locale;
  chartId: string;
  langs: string[];
  dict: Dict;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  // `router.refresh()` no avisa cuándo terminó. Envuelto en una transición,
  // `refrescando` dice cuándo el servidor ya devolvió la lectura: sin eso la
  // animación se quedaba encendida para siempre debajo del texto ya escrito.
  const [refrescando, startTransition] = useTransition();
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const yaLeida = langs.includes(locale);
  // Si ya existe en otro idioma, traducirla no cuesta: el backend no vuelve a
  // cobrar. Decir "usa 1 crédito" ahí sería mentir, y es lo que hace la app.
  const enOtroIdioma = !yaLeida && langs.length > 0;

  useEffect(() => {
    if (!busy || step >= dict.chart.waitSteps.length - 1) return;
    const timer = window.setTimeout(() => setStep((s) => s + 1), STEP_MS);
    return () => window.clearTimeout(timer);
  }, [busy, step, dict.chart.waitSteps.length]);

  /**
   * Espera a que aparezca una lectura que otra petición ya está escribiendo.
   *
   * El backend responde 409 cuando dos pedidos coinciden sobre la misma carta:
   * uno la escribe y el otro rebota. Rendirse ahí sería mentir —la lectura está
   * en camino—, así que se pregunta cada tanto hasta que existe.
   */
  async function waitForReading(): Promise<boolean> {
    for (let intento = 0; intento < POLL_TRIES; intento++) {
      await sleep(POLL_MS);
      const res = await fetch(`/api/charts/${chartId}/interpretation?lang=${locale}`);
      if (res.ok) return true;
    }
    return false;
  }

  async function interpret() {
    setStep(0);
    setBusy(true);
    setError(null);

    const res = await fetch(`/api/charts/${chartId}/interpretation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lang: locale }),
    });

    if (res.status === 409 && (await waitForReading())) {
      startTransition(() => router.refresh());
      setBusy(false);
      return;
    }

    if (!res.ok) {
      setBusy(false);
      setError(res.status === 402 ? dict.chart.noCredits : dict.chart.failed);
      return;
    }

    // La lectura queda debajo de la carta, en esta misma página. La animación
    // sigue hasta que el refresh trae el texto, no hasta que responde el POST.
    startTransition(() => router.refresh());
    setBusy(false);
  }

  if (busy || refrescando) {
    return (
      <section className="waiting">
        <SolarSystem size={200} speed={2.5} />
        <div className="waitingCopy">
          <h2 className="display waitingTitle">{dict.chart.waitTitle}</h2>
          <p className="waitingBody">{dict.chart.waitBody}</p>
        </div>
        <ol className="waitingSteps">
          {dict.chart.waitSteps.map((texto, i) => {
            if (i > step) return <li key={texto} className="waitingStep" aria-hidden="true" />;
            const hecho = i < step;
            return (
              <li key={texto} className={`waitingStep ${hecho ? "waitingDone" : "waitingNow"}`}>
                <span aria-hidden="true">{hecho ? "●" : "○"}</span>
                {texto}
              </li>
            );
          })}
        </ol>
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
      {error && (
        <p className="formError" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
