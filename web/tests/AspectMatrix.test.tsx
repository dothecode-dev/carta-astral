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
      glosarioTitulo={dict.chart.aspectGlossary}
      glosarioCuenta={dict.chart.aspectGlossaryCount}
      verAspectos={dict.chart.verAspectos}
    />,
  );
}

/** Cuántos aspectos de ese tipo dice el glosario, o null si no lo lista. */
function cuentaDelGlosario(container: HTMLElement, nombre: string): string | null {
  const item = [...container.querySelectorAll(".glossaryItem")].find((el) =>
    el.querySelector(".glossaryName")?.textContent?.includes(nombre),
  );
  return item?.querySelector(".glossaryCount")?.textContent ?? null;
}

describe("AspectMatrix", () => {
  it("el desplegable se lee como acción, con la cuenta", () => {
    // «+ 39 ASPECTOS» en mono mayúscula se leía como rótulo y nadie lo tocaba:
    // ahora es una frase con verbo, y el número sigue porque es lo que informa.
    pintar();
    expect(screen.getByRole("group").querySelector("summary")?.textContent?.trim()).toBe(
      dict.chart.verAspectos.replace("{n}", String(ASPECTS.length)),
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

/**
 * El glosario: qué significa cada tipo de aspecto que la carta tiene.
 *
 * Hasta el 09-09-2026 la explicación estaba sólo en la ficha de la matriz, que
 * abre con `:hover` sobre una matriz que el CSS oculta hasta los 900px. En un
 * teléfono la carta mostraba sesenta y dos aspectos y ni una línea de qué
 * significan.
 */
describe("glosario de aspectos", () => {
  it("la explicación está fuera de la matriz, que en pantalla angosta no se dibuja", () => {
    // Éste es el test del arreglo: si la glosa vuelve a vivir sólo en la ficha
    // de la matriz, acá se cae. `.matrixWrap` es lo que el CSS apaga por debajo
    // de 900px, así que lo de adentro no cuenta como alcanzable.
    const { container } = pintar();
    const matriz = container.querySelector(".matrixWrap")!;
    const fuera = [...container.querySelectorAll(".glossaryMeaning")].filter(
      (el) => !matriz.contains(el),
    );
    expect(fuera.map((el) => el.textContent).join(" ")).toContain("Fluye sin esfuerzo");
  });

  it("lista un tipo de aspecto, no un par: dos trígonos son una entrada", () => {
    const { container } = pintar([
      { a: "Sun", b: "Moon", type: "trine", orb: 1 },
      { a: "Sun", b: "Mars", type: "trine", orb: 2 },
      { a: "Mars", b: "Saturn", type: "square", orb: 3 },
    ]);
    expect(container.querySelectorAll(".glossaryItem")).toHaveLength(2);
    expect(cuentaDelGlosario(container, "Trígono")).toBe("2 en tu carta");
    expect(cuentaDelGlosario(container, "Cuadratura")).toBe("1 en tu carta");
  });

  it("pone primero el tipo que más veces aparece", () => {
    // De qué está hecha la carta se lee en el orden, sin contar filas.
    const { container } = pintar([
      { a: "Sun", b: "Moon", type: "square", orb: 1 },
      { a: "Sun", b: "Mars", type: "trine", orb: 2 },
      { a: "Moon", b: "Mars", type: "trine", orb: 3 },
      { a: "Mars", b: "Saturn", type: "trine", orb: 4 },
    ]);
    const nombres = [...container.querySelectorAll(".glossaryName")].map((el) => el.textContent);
    expect(nombres).toEqual(["Trígono", "Cuadratura"]);
  });

  it("no nombra un aspecto que la carta no tiene", () => {
    const { container } = pintar([{ a: "Sun", b: "Moon", type: "trine", orb: 1 }]);
    expect(cuentaDelGlosario(container, "Oposición")).toBeNull();
  });

  it("descarta el aspecto cuyo cuerpo no está en la carta, igual que la matriz", () => {
    // `pairs` ya los filtra; el glosario cuenta sobre eso y no sobre el crudo.
    const { container } = pintar([{ a: "Sun", b: "Ceres", type: "trine", orb: 1 }]);
    expect(container.querySelectorAll(".glossaryItem")).toHaveLength(0);
  });

  it("sin aspectos no hay glosario, ni su título", () => {
    const { container } = pintar([]);
    expect(container.querySelector(".aspectGlossary")).toBeNull();
    expect(screen.queryByText(dict.chart.aspectGlossary)).toBeNull();
  });
});
