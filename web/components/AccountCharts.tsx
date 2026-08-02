import Link from "next/link";

import { signOf } from "@/lib/ephemeris";
import type { Dict, Locale } from "@/lib/i18n";
import { INTL_LOCALE } from "@/lib/i18n";

// Una carta tal como la devuelve GET /api/charts/. Sólo se declara lo que la
// lista muestra: el payload trae la carta entera y no hace falta acá.
export type ChartSummary = {
  id: string;
  interpretation_langs: string[];
  birth: {
    name: string | null;
    date: string;
    time: string | null;
    place_label: string;
  };
  data: {
    placements: { name: string; abs_pos: number }[];
  };
};

/** El glifo de la lista es el signo solar, como en la app. */
function sunSign(chart: ChartSummary): string {
  const sun = chart.data?.placements?.find((p) => p.name === "Sun");
  return sun ? signOf(sun.abs_pos) : "☉";
}

function birthLine(chart: ChartSummary, locale: Locale): string {
  const [y, m, d] = chart.birth.date.split("-").map(Number);
  const fecha = new Intl.DateTimeFormat(INTL_LOCALE[locale], {
    // "medium" da "17 may 2007"; armarlo por partes daba "17 de may de 2007".
    dateStyle: "medium",
    // Fecha de nacimiento, no un instante: sin zona horaria no se corre un día.
    timeZone: "UTC",
  }).format(new Date(Date.UTC(y, m - 1, d)));
  return chart.birth.time ? `${fecha} · ${chart.birth.time}` : fecha;
}

export function AccountCharts({
  charts,
  locale,
  dict,
}: {
  charts: ChartSummary[];
  locale: Locale;
  dict: Dict;
}) {
  if (charts.length === 0) {
    return (
      <div className="emptyCharts">
        <p className="emptyChartsText">{dict.auth.chartsEmpty}</p>
        <Link className="btn btnPrimary" href={`/${locale}/nueva`}>
          {dict.auth.chartsEmptyCta}
        </Link>
      </div>
    );
  }

  return (
    <div className="notes">
      {charts.map((chart) => (
        // Hasta que exista la página de una carta, lleva a la de ejemplo.
        <Link className="note" href={`/${locale}/ejemplo`} key={chart.id}>
          <span className="noteMeta">{birthLine(chart, locale)}</span>
          <span className="chartLine">
            <h3 className="noteTitle">{chart.birth.name || dict.auth.unnamedChart}</h3>
            <span className="chartPlace">{chart.birth.place_label}</span>
            {chart.interpretation_langs.length > 0 && (
              <span className="chartLangs">
                {dict.auth.readIn} {chart.interpretation_langs.join(" · ").toUpperCase()}
              </span>
            )}
          </span>
          <span className="noteSign" aria-hidden="true">
            {sunSign(chart)}
          </span>
        </Link>
      ))}
    </div>
  );
}
