import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DatosCarta } from "@/components/DatosCarta";
import { getDict } from "@/lib/i18n";

import { CARTA, chartCon } from "./fixtures/carta";

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

  // Sin hora, si la Luna cambia de signo ese día, la tabla no puede afirmar
  // uno: el teaser y la firma ya no la nombran.
  const FLAGS = { moon_approximate: true, precision_degraded: false, bodies_missing: false, house_system_fallback: false };
  const LUNA = { name: "Moon", sign: "Leo", abs_pos: 145, house: null, retrograde: false };

  it("con la Luna dudosa muestra los dos signos y no el grado", () => {
    const carta = chartCon({
      placements: [LUNA],
      flags: { ...FLAGS, moon_sign_uncertain: true, moon_sign_options: ["Leo", "Vir"] },
    });
    render(<DatosCarta chart={carta} dict={dict} locale="es" />);
    expect(screen.getByText("♌ Leo o ♍ Virgo")).toBeInTheDocument();
    expect(screen.queryByText(/25°/)).toBeNull();
  });

  it("con la Luna dudosa y sin opciones dice que el signo es incierto", () => {
    const carta = chartCon({
      placements: [LUNA],
      flags: { ...FLAGS, moon_sign_uncertain: true, moon_sign_options: [] },
    });
    render(<DatosCarta chart={carta} dict={dict} locale="es" />);
    expect(screen.getByText(dict.chart.lunaIncierta)).toBeInTheDocument();
  });

  it("con la Luna estable muestra el grado como siempre", () => {
    const carta = chartCon({ placements: [LUNA], flags: { ...FLAGS, moon_sign_uncertain: false } });
    render(<DatosCarta chart={carta} dict={dict} locale="es" />);
    expect(screen.getByText(/25°00′ ♌ Leo/)).toBeInTheDocument();
  });
});
