import type { ApiChart } from "@/lib/chart";
import { toWheel } from "@/lib/chart";
import { formatDegree, signOf } from "@/lib/ephemeris";
import {
  ASPECT_GLYPHS,
  ASPECT_NAMES,
  INTL_LOCALE,
  PLANET_GLYPHS,
  PLANET_NAME_BY_KEY,
  type Dict,
  type Locale,
} from "@/lib/i18n";
import { type PdfWheel, toPdfWheel } from "@/lib/wheelPayload";

// El cuerpo que recibe `POST /api/charts/{id}/pdf/`.
//
// Los rótulos van traducidos desde acá porque el diccionario de nombres vive en
// `lib/i18n.ts` y sólo ahí: portarlo a Python sería una tercera copia de la
// misma verdad —la app tiene la suya— y las tres se desincronizarían.

const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];

/** Los ejes no tienen glifo planetario, pero sí aparecen en los aspectos: sin
 *  esto, "Sol conjunción Ascendente" salía como "☉ ☌ ·" en la tabla del PDF. */
const ANGLE_GLYPH: Record<string, string> = {
  Ascendant: "AC", Medium_Coeli: "MC", Descendant: "DC", Imum_Coeli: "IC",
};

function glifo(nombre: string): string {
  return PLANET_GLYPHS[nombre] ?? ANGLE_GLYPH[nombre] ?? "·";
}
const HOUSE_INDEX: Record<string, number> = {
  First_House: 1, Second_House: 2, Third_House: 3, Fourth_House: 4,
  Fifth_House: 5, Sixth_House: 6, Seventh_House: 7, Eighth_House: 8,
  Ninth_House: 9, Tenth_House: 10, Eleventh_House: 11, Twelfth_House: 12,
};

export type PdfPayload = {
  labels: {
    brand_tagline: string;
    eyebrow: string;
    chart_name: string;
    birth_line: string;
    positions: string;
    aspects: string;
    reading: string;
    made_with: string;
  };
  positions: {
    glyph: string; name: string; position: string; house: string; retrograde: boolean;
  }[];
  aspects: { glyph: string; name: string; detail: string }[];
  wheel: PdfWheel | null;
  reading_lang?: string | null;
};

/** La línea de nacimiento tal como se lee arriba de la carta en la web. */
function birthLine(chart: ApiChart, locale: Locale): string {
  const fecha = new Intl.DateTimeFormat(INTL_LOCALE[locale], {
    dateStyle: "long",
    timeZone: "UTC",
  }).format(new Date(`${chart.birth.date}T12:00:00Z`));
  return [
    fecha + (chart.birth.time ? ` · ${chart.birth.time}` : ""),
    chart.birth.place_label,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function buildPdfPayload(chart: ApiChart, locale: Locale, dict: Dict): PdfPayload {
  const names = PLANET_NAME_BY_KEY[locale];
  const aspectNames = ASPECT_NAMES[locale];
  const wheel = toWheel(chart);

  // Los ejes primero, como en la tabla de la web y como en el PDF de la app.
  // DC e IC no se listan: son los opuestos exactos de AC y MC.
  const ejes = (chart.data.angles ?? [])
    .filter((a) => a.name === "Ascendant" || a.name === "Medium_Coeli")
    .map((a) => {
      const clave = a.name === "Ascendant" ? ("AC" as const) : ("MC" as const);
      return {
        glyph: clave,
        name: dict.chart.axisNames[clave],
        position: `${formatDegree(a.abs_pos)} ${signOf(a.abs_pos)}`,
        house: "",
        retrograde: false,
      };
    });

  const cuerpos = chart.data.placements.map((p) => ({
    glyph: PLANET_GLYPHS[p.name] ?? "·",
    name: names[p.name] ?? p.name.replace(/_/g, " "),
    position: `${formatDegree(p.abs_pos)} ${signOf(p.abs_pos)}`,
    house: p.house ? ROMAN[HOUSE_INDEX[p.house] - 1] : "—",
    retrograde: p.retrograde,
  }));

  return {
    labels: {
      brand_tagline: dict.share.tagline,
      eyebrow: dict.share.chartEyebrow,
      chart_name: chart.birth.name || dict.auth.unnamedChart,
      birth_line: birthLine(chart, locale),
      positions: dict.share.positionsTitle,
      aspects: dict.chart.aspects,
      reading: dict.chart.reading,
      made_with: dict.share.madeWith,
    },
    positions: [...ejes, ...cuerpos],
    aspects: chart.data.aspects.map((a) => ({
      glyph: `${glifo(a.p1)} ${ASPECT_GLYPHS[a.aspect] ?? "·"} ${glifo(a.p2)}`,
      name: aspectNames[a.aspect] ?? a.aspect,
      detail: `${dict.chart.aspectColumns.orb} ${a.orbit.toFixed(1)}°`,
    })),
    wheel: wheel ? toPdfWheel(wheel) : null,
  };
}
