import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DatosCarta } from "@/components/DatosCarta";
import { getDict } from "@/lib/i18n";

import { CARTA } from "./fixtures/carta";

// Posiciones, casas y aspectos, plegados detrás de la lectura: son datos de
// astrólogo, y quien llega por «carta natal gratis» quiere la rueda y la
// firma. Lo abre quien ya sabe qué busca.

const dict = getDict("es");

describe("DatosCarta", () => {
  it("arranca plegado y se abre con una frase", () => {
    render(<DatosCarta chart={CARTA} dict={dict} locale="es" />);
    const details = screen.getByText(dict.chart.verDatos).closest("details");
    expect(details).not.toBeNull();
    expect(details!.open).toBe(false);
  });

  it("adentro están las posiciones", () => {
    render(<DatosCarta chart={CARTA} dict={dict} locale="es" />);
    expect(screen.getByText(dict.chart.columns.position)).toBeInTheDocument();
  });
});
