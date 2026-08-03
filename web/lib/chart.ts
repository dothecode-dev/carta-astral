import type { WheelInput } from "astra-wheel";

import type { SampleChart } from "@/content/sample-chart";

// La rueda natal se dibujó para la carta de ejemplo, que vive en el repo con un
// formato compacto. El backend devuelve otra cosa —más completa y con los
// nombres del motor—, así que se traduce en un solo lugar y el componente que
// dibuja no se entera de la diferencia.

export type ApiChart = {
  id: string;
  interpretation_langs: string[];
  birth: {
    name: string | null;
    date: string;
    time: string | null;
    time_known: boolean;
    place_label: string;
  };
  data: {
    placements: {
      name: string;
      sign: string;
      abs_pos: number;
      house: string | null;
      retrograde: boolean;
    }[];
    houses: { name: string; abs_pos: number }[] | null;
    angles: { name: string; abs_pos: number }[] | null;
    aspects: { p1: string; p2: string; aspect: string; orbit: number }[];
    flags: {
      moon_approximate: boolean;
      precision_degraded: boolean;
      bodies_missing: boolean;
      house_system_fallback: boolean;
    };
  };
};

/**
 * Los cuerpos que dibuja la rueda, en su orden tradicional.
 *
 * Son los catorce que calcula el motor. Hasta el 2026-08-03 eran diez: los
 * cuatro que faltaban —Quirón, los nodos y Lilith— se calculaban, viajaban en
 * la respuesta y se descartaban acá, así que la misma carta se veía distinta
 * en la web que en el PDF.
 */
const WHEEL_BODIES = [
  "Sun", "Moon", "Mercury", "Venus", "Mars",
  "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
  "Chiron", "True_North_Lunar_Node", "Mean_Lilith", "True_South_Lunar_Node",
];

const HOUSE_ORDER = [
  "First_House", "Second_House", "Third_House", "Fourth_House",
  "Fifth_House", "Sixth_House", "Seventh_House", "Eighth_House",
  "Ninth_House", "Tenth_House", "Eleventh_House", "Twelfth_House",
];

/**
 * Adapta la carta al formato que entiende `astra-wheel`.
 *
 * La orientación sale de `angles.Ascendant`, nunca de la primera cúspide:
 * coinciden en Placidus, pero en Whole Sign la casa 1 empieza en 0° del signo
 * y el Ascendente cae hasta 29° adentro.
 */
export function toWheelInput(chart: SampleChart): WheelInput {
  return {
    bodies: chart.planets.map((p) => ({ name: p.name, lon: p.lon })),
    cusps: chart.houses,
    ascendant: chart.angles.Ascendant,
    // Solo los dos que se rotulan en el borde. DC e IC quedan implicitos.
    angles: [
      { name: "Ascendant", lon: chart.angles.Ascendant },
      { name: "Medium_Coeli", lon: chart.angles.Medium_Coeli },
    ],
    aspects: chart.aspects.map((a) => ({ a: a.a, b: a.b, type: a.type, orb: a.orb })),
  };
}

/**
 * Adapta la carta del backend al formato que dibuja la rueda.
 *
 * Devuelve null si la carta no tiene casas ni ángulos: eso pasa cuando no se
 * conoce la hora de nacimiento, y una rueda sin Ascendente no se puede orientar.
 */
export function toWheel(chart: ApiChart): SampleChart | null {
  const { houses, angles, placements, aspects } = chart.data;
  if (!houses || !angles) return null;

  const porNombre = new Map(angles.map((a) => [a.name, a.abs_pos]));
  const asc = porNombre.get("Ascendant");
  const mc = porNombre.get("Medium_Coeli");
  if (asc === undefined || mc === undefined) return null;

  const cuspides = HOUSE_ORDER.map((n) => houses.find((h) => h.name === n)?.abs_pos);
  if (cuspides.some((c) => c === undefined)) return null;

  return {
    planets: placements
      .filter((p) => WHEEL_BODIES.includes(p.name))
      .map((p) => ({
        name: p.name,
        lon: p.abs_pos,
        house: p.house ?? "First_House",
        retro: p.retrograde,
      })),
    houses: cuspides as number[],
    angles: {
      Ascendant: asc,
      Medium_Coeli: mc,
      Descendant: porNombre.get("Descendant") ?? (asc + 180) % 360,
      Imum_Coeli: porNombre.get("Imum_Coeli") ?? (mc + 180) % 360,
    },
    aspects: aspects
      .filter((a) => WHEEL_BODIES.includes(a.p1) && WHEEL_BODIES.includes(a.p2))
      .map((a) => ({ a: a.p1, b: a.p2, type: a.aspect, orb: a.orbit })),
  };
}
