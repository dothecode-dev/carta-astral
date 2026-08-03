import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AspectMatrix } from "@/components/AspectMatrix";
import { getDict } from "@/lib/i18n";

const dict = getDict("es");

const BODIES = ["Sun", "Moon", "Mars", "Saturn"];
const ASPECTS = [
  { a: "Sun", b: "Moon", type: "trine", orb: 1.24 },
  { a: "Mars", b: "Saturn", type: "square", orb: 3.5 },
];

function pintar(aspects = ASPECTS, bodies = BODIES) {
  return render(
    <AspectMatrix bodies={bodies} aspects={aspects} locale="es" titulo={dict.chart.aspects} />,
  );
}

describe("AspectMatrix", () => {
  it("la lista traduce el aspecto y dice el orbe", () => {
    // Es lo que la matriz calla: el orbe sólo está acá y en el title de la celda.
    pintar();
    const lista = screen.getByText(dict.chart.aspects, { selector: "summary" }).closest("details")!;
    expect(within(lista).getByText("Trígono")).toBeInTheDocument();
    expect(within(lista).getByText("1.2°")).toBeInTheDocument();
    expect(within(lista).getByText("3.5°")).toBeInTheDocument();
  });

  it("la matriz pone un glifo por aspecto, no más", () => {
    const { container } = pintar();
    const celdas = container.querySelectorAll(".aspectMatrix .matrixCell abbr");
    expect(celdas).toHaveLength(ASPECTS.length);
  });

  it("el glifo cae en el cruce de los dos cuerpos, con su orbe en el title", () => {
    const { container } = pintar();
    const trigono = container.querySelector('.aspectMatrix abbr[title*="Trígono"]')!;
    expect(trigono.getAttribute("title")).toContain("1.2°");
    expect(trigono.textContent).toBe("△");
  });

  it("suma al eje los ángulos que aspectan, y no los cuerpos", () => {
    const { container } = pintar([{ a: "Sun", b: "Ascendant", type: "square", orb: 2 }]);
    const encabezados = [...container.querySelectorAll(".aspectMatrix .matrixHead")].map(
      (th) => th.textContent,
    );
    expect(encabezados).toContain("AC");
    // El Descendente no aspecta a nadie: no ocupa una fila vacía.
    expect(encabezados).not.toContain("DC");
  });

  it("descarta el aspecto de un cuerpo que no está en la carta", () => {
    // Pasa cuando la efeméride no pudo calcular un cuerpo: la celda no existe,
    // pero el componente no puede romperse por eso.
    const { container } = pintar([{ a: "Sun", b: "Ceres", type: "trine", orb: 1 }]);
    expect(container.querySelectorAll(".aspectMatrix .matrixCell abbr")).toHaveLength(0);
  });

  it("sin aspectos no dibuja ninguna celda ocupada", () => {
    const { container } = pintar([]);
    expect(container.querySelectorAll(".matrixCell abbr")).toHaveLength(0);
  });
});
