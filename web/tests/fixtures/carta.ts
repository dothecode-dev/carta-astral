import type { ApiChart } from "@/lib/chart";

// Una carta mínima para los tests de componentes. `houses: null` deja a
// `toWheel` devolviendo null (lib/chart.ts), así que no se monta el canvas de
// la rueda —que jsdom no dibuja— y queda lo demás solo.

export function chartCon(data: Partial<ApiChart["data"]>): ApiChart {
  return {
    id: "x",
    interpretation_langs: [],
    interpretations: {},
    en_curso: {},
    birth: { name: "Ceci", date: "1989-07-14", time: "23:45", time_known: true, place_label: "x" },
    data: {
      placements: [],
      houses: null,
      angles: null,
      aspects: [],
      flags: {
        moon_approximate: false,
        precision_degraded: false,
        bodies_missing: false,
        house_system_fallback: false,
      },
      ...data,
    },
  };
}

// 357° cae en Piscis a 27°00′: el mismo Ascendente de la captura que originó
// esto. 112.487° es el Sol en Cáncer de la carta de Ceci.
export const CARTA = chartCon({
  placements: [
    { name: "Sun", sign: "Can", abs_pos: 112.487, house: "Twelfth_House", retrograde: false },
  ],
  angles: [
    { name: "Ascendant", abs_pos: 357 },
    { name: "Medium_Coeli", abs_pos: 266.73 },
  ],
});
