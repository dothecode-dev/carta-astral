import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChartBody } from "@/components/ChartBody";
import { ChartTables } from "@/components/ChartTables";
import { getDict } from "@/lib/i18n";

import { CARTA, chartCon } from "./fixtures/carta";

// La tabla de posiciones es la pantalla que sostiene el producto y no tenía
// ningún test de render: `formatDegree` y `signOf` estaban cubiertos por
// separado, pero nada verificaba que la celda saliera armada.
//
// `houses: null` deja a `toWheel` devolviendo null (lib/chart.ts), así que no
// se monta el canvas de la rueda —que jsdom no dibuja— y queda la tabla sola.

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

  it("con soloRueda no dibuja la tabla de posiciones", () => {
    render(<ChartBody chart={CARTA} dict={getDict("es")} locale="es" soloRueda />);

    expect(screen.queryByText(getDict("es").chart.columns.position)).toBeNull();
  });

  it("deja la casa en números romanos, sin tocarla", () => {
    render(<ChartBody chart={CARTA} dict={getDict("es")} locale="es" />);

    expect(screen.getByText("XII")).toBeInTheDocument();
  });
});

describe("ChartTables", () => {
  it("las casas se abren con una frase, no con un rótulo", () => {
    const conCasas = chartCon({ houses: [{ name: "First_House", abs_pos: 357 }] });
    render(<ChartTables chart={conCasas} dict={getDict("es")} locale="es" />);
    expect(screen.getByText(getDict("es").chart.verCasas)).toBeInTheDocument();
  });
});
