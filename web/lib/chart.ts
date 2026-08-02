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

/** Los diez cuerpos que dibuja la rueda, en su orden tradicional. */
const WHEEL_BODIES = [
  "Sun", "Moon", "Mercury", "Venus", "Mars",
  "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
];

const HOUSE_ORDER = [
  "First_House", "Second_House", "Third_House", "Fourth_House",
  "Fifth_House", "Sixth_House", "Seventh_House", "Eighth_House",
  "Ninth_House", "Tenth_House", "Eleventh_House", "Twelfth_House",
];

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
