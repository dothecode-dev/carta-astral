import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChartBody } from "@/components/ChartBody";
import type { ApiChart } from "@/lib/chart";
import { getDict } from "@/lib/i18n";

// La tabla de posiciones es la pantalla que sostiene el producto y no tenía
// ningún test de render: `formatDegree` y `signOf` estaban cubiertos por
// separado, pero nada verificaba que la celda saliera armada.
//
// `houses: null` deja a `toWheel` devolviendo null (lib/chart.ts), así que no
// se monta el canvas de la rueda —que jsdom no dibuja— y queda la tabla sola.

function chartCon(data: Partial<ApiChart["data"]>): ApiChart {
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
const CARTA = chartCon({
  placements: [
    { name: "Sun", sign: "Can", abs_pos: 112.487, house: "Twelfth_House", retrograde: false },
  ],
  angles: [
    { name: "Ascendant", abs_pos: 357 },
    { name: "Medium_Coeli", abs_pos: 266.73 },
  ],
});

describe("ChartBody", () => {
  it("nombra el signo al lado del glifo, en los cuerpos y en los ejes", () => {
    render(<ChartBody chart={CARTA} dict={getDict("es")} locale="es" />);

    expect(screen.getByText("22°29′ ♋ Cáncer")).toBeInTheDocument();
    expect(screen.getByText("27°00′ ♓ Piscis")).toBeInTheDocument();
    expect(screen.getByText("26°43′ ♐ Sagitario")).toBeInTheDocument();
  });

  it("traduce el nombre del signo", () => {
    render(<ChartBody chart={CARTA} dict={getDict("en")} locale="en" />);

    expect(screen.getByText("27°00′ ♓ Pisces")).toBeInTheDocument();
    expect(screen.getByText("22°29′ ♋ Cancer")).toBeInTheDocument();
  });

  it("deja la casa en números romanos, sin tocarla", () => {
    render(<ChartBody chart={CARTA} dict={getDict("es")} locale="es" />);

    expect(screen.getByText("XII")).toBeInTheDocument();
  });
});
