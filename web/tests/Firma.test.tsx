import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Firma } from "@/components/Firma";
import { getDict } from "@/lib/i18n";

// Sol, Luna y Ascendente en palabras, debajo del nombre de la carta. Es lo
// único que entiende quien no sabe leer glifos, y hasta acá había que pescarlo
// en las filas 3, 4 y 1 de la tabla de posiciones.

const FIRMA = [
  { cuerpo: "Sun" as const, signo: "Gem", frases: { es: "Frase del Sol.", en: "Sun phrase.", pt: "Frase do Sol." } },
  { cuerpo: "Moon" as const, signo: "Sco", frases: { es: "Frase de la Luna.", en: "Moon phrase.", pt: "Frase da Lua." } },
  { cuerpo: "Ascendant" as const, signo: "Can", frases: { es: "Frase del Asc.", en: "Asc phrase.", pt: "Frase do Asc." } },
];

describe("Firma", () => {
  it("nombra cuerpo y signo en el idioma de la página, con su frase", () => {
    render(<Firma firma={FIRMA} dict={getDict("es")} locale="es" />);
    expect(screen.getByText("Sol en Géminis")).toBeInTheDocument();
    expect(screen.getByText("Luna en Escorpio")).toBeInTheDocument();
    expect(screen.getByText("Ascendente en Cáncer")).toBeInTheDocument();
    expect(screen.getByText("Frase del Sol.")).toBeInTheDocument();
  });

  it("en otro idioma, traduce el signo y elige la frase de ese idioma", () => {
    render(<Firma firma={FIRMA} dict={getDict("en")} locale="en" />);
    expect(screen.getByText("Moon in Scorpio")).toBeInTheDocument();
    expect(screen.getByText("Moon phrase.")).toBeInTheDocument();
    expect(screen.queryByText("Frase de la Luna.")).toBeNull();
  });

  it("sin firma no renderiza nada", () => {
    const { container } = render(<Firma firma={undefined} dict={getDict("es")} locale="es" />);
    expect(container.innerHTML).toBe("");
  });
});
