import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Derechos } from "@/components/Derechos";
import { getDict } from "@/lib/i18n";

const dict = getDict("es");

describe("Derechos", () => {
  it("dice qué puede hacer la persona, no cuántos créditos tiene", () => {
    render(<Derechos derechos={[
      { codigo_producto: "lectura_breve", cantidad_restante: 2, vigente_hasta: null },
      { codigo_producto: "informe_natal", cantidad_restante: 1, vigente_hasta: null },
    ]} dict={dict} locale="es" />);

    expect(screen.getByText(/2 lecturas breves/i)).toBeInTheDocument();
    expect(screen.getByText(/1 informe completo/i)).toBeInTheDocument();
    expect(screen.queryByText(/crédito/i)).toBeNull();
  });

  it("sin derechos ofrece el informe en vez de mostrar un cero", () => {
    render(<Derechos derechos={[]} dict={dict} locale="es" />);
    expect(screen.queryByText("0")).toBeNull();
    // No sólo evita el "0": ofrece algo en su lugar.
    expect(screen.getByText(dict.auth.sinDerechos)).toBeInTheDocument();
  });

  it("con un solo derecho usa singular, no '1 lecturas breves'", () => {
    render(<Derechos derechos={[
      { codigo_producto: "lectura_breve", cantidad_restante: 1, vigente_hasta: null },
    ]} dict={dict} locale="es" />);
    expect(screen.getByText(/1 lectura breve\b/i)).toBeInTheDocument();
    expect(screen.queryByText(/1 lecturas breves/i)).toBeNull();
  });

  it("un derecho agotado (cantidad 0) no cuenta como disponible", () => {
    render(<Derechos derechos={[
      { codigo_producto: "lectura_breve", cantidad_restante: 0, vigente_hasta: null },
      { codigo_producto: "informe_natal", cantidad_restante: 0, vigente_hasta: null },
    ]} dict={dict} locale="es" />);
    expect(screen.getByText(dict.auth.sinDerechos)).toBeInTheDocument();
  });
});
