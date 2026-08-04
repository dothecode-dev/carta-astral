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
    <AspectMatrix
      bodies={bodies}
      aspects={aspects}
      locale="es"
      titulo={dict.chart.aspects}
      orbeLabel={dict.chart.aspectColumns.orb}
    />,
  );
}

describe("AspectMatrix", () => {
  it("el desplegable dice cuantos aspectos hay", () => {
    // Con la matriz al lado, repetir "Aspectos" no aportaba; el numero si.
    pintar();
    expect(screen.getByRole("group").querySelector("summary")?.textContent?.trim()).toBe(
      `${ASPECTS.length} ${dict.chart.aspects.toLowerCase()}`,
    );
  });

  it("la lista traduce el aspecto y dice el orbe", () => {
    // Es lo que la matriz calla: el orbe sólo está acá y en el title de la celda.
    pintar();
    const lista = screen.getByRole("group").querySelector("table")!;
    expect(within(lista).getByText("Trígono")).toBeInTheDocument();
    expect(within(lista).getByText("1.2°")).toBeInTheDocument();
    expect(within(lista).getByText("3.5°")).toBeInTheDocument();
  });

  it("la matriz pone un glifo por aspecto, no más", () => {
    const { container } = pintar();
    const celdas = container.querySelectorAll(".aspectMatrix .matrixCell .matrixMark");
    expect(celdas).toHaveLength(ASPECTS.length);
  });

  it("la ficha nombra a los dos cuerpos, el angulo, el orbe y que significa", () => {
    const { container } = pintar();
    const ficha = container.querySelector(".matrixTip")!;
    expect(ficha.textContent).toContain("Sol");
    expect(ficha.textContent).toContain("Luna");
    expect(ficha.textContent).toContain("trígono");
    expect(ficha.textContent).toContain("120°");
    expect(ficha.textContent).toContain("1.2°");
    // La explicacion es lo que separa una ficha de un tooltip que repite el dato.
    expect(ficha.textContent).toContain("Fluye sin esfuerzo");
  });

  it("no usa el tooltip del navegador ni el cursor de ayuda", () => {
    const { container } = pintar();
    expect(container.querySelector("abbr")).toBeNull();
    expect(container.querySelector("[title]")).toBeNull();
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
    expect(container.querySelectorAll(".aspectMatrix .matrixCell .matrixMark")).toHaveLength(0);
  });

  it("sin aspectos no dibuja ninguna celda ocupada", () => {
    const { container } = pintar([]);
    expect(container.querySelectorAll(".matrixCell .matrixMark")).toHaveLength(0);
  });
});
