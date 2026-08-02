"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Dict, Locale } from "@/lib/i18n";

// El botón que gasta el crédito. Se deshabilita mientras espera: generar una
// lectura tarda, y dos clicks serían dos pedidos —el backend deduplica por
// contenido, pero no hay razón para mandarle el segundo—.

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
  const [error, setError] = useState<string | null>(null);

  const yaLeida = langs.includes(locale);

  async function interpret() {
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

    router.push(`/${locale}/carta/${chartId}/lectura`);
  }

  if (yaLeida) {
    return (
      <div className="chartActions">
        <a className="btn btnPrimary" href={`/${locale}/carta/${chartId}/lectura`}>
          {dict.chart.readAgain}
        </a>
      </div>
    );
  }

  return (
    <div className="chartActions">
      <button type="button" className="btn btnPrimary" onClick={interpret} disabled={busy}>
        {busy ? dict.chart.interpreting : dict.chart.interpret}
      </button>
      <p className="fieldNote">{dict.chart.interpretCost}</p>
      {error && (
        <p className="formError" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
