import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Derechos } from "@/components/Derechos";
import { getDict } from "@/lib/i18n";

const dict = getDict("es");

const derecho = (codigo: string, n: number) => ({
  codigo_producto: codigo,
  cantidad_restante: n,
  vigente_hasta: null,
});

/** El recuento ya formado, como lo escribe la frase. */
const frase = (que: string) => dict.auth.derechosFrase.replace("{que}", que);

// Lo que la cuenta tiene para usar. Hasta el 06-10-2026 era un inventario
// —una fila por producto con dos enlaces chicos— y lo más visible de la
// cuenta era el recuadro de borrado. Ahora es una frase y una sola salida.

describe("Derechos", () => {
  it("dice en una frase qué hay para leer", () => {
    render(
      <Derechos
        derechos={[derecho("lectura_breve", 3), derecho("informe_natal", 1)]}
        dict={dict}
        locale="es"
        hayCartas
      />,
    );

    expect(
      screen.getByText(frase(`${dict.auth.derechosBreve.replace("{n}", "3")} · ${dict.auth.derechosInformeUno}`)),
    ).toBeInTheDocument();
  });

  it("no habla de créditos en ninguna parte", () => {
    render(
      <Derechos derechos={[derecho("lectura_breve", 2)]} dict={dict} locale="es" hayCartas />,
    );

    expect(screen.queryByText(/crédito/i)).toBeNull();
  });

  it("sin derechos ofrece el informe en vez de mostrar un cero", () => {
    render(<Derechos derechos={[]} dict={dict} locale="es" hayCartas />);

    expect(screen.queryByText("0")).toBeNull();
    expect(screen.getByText(dict.auth.sinDerechos)).toBeInTheDocument();
  });

  it("no nombra lo que ya se agotó", () => {
    render(
      <Derechos
        derechos={[derecho("lectura_breve", 0), derecho("informe_natal", 1)]}
        dict={dict}
        locale="es"
        hayCartas
      />,
    );

    expect(screen.getByText(frase(dict.auth.derechosInformeUno))).toBeInTheDocument();
    expect(screen.queryByText(/lecturas breves/)).toBeNull();
  });
});

describe("a dónde se va a usar", () => {
  const ambos = [derecho("lectura_breve", 2), derecho("informe_natal", 1)];

  it("con cartas, una sola salida: elegir una de las que ya tiene", () => {
    render(<Derechos derechos={ambos} dict={dict} locale="es" hayCartas />);

    expect(screen.getByRole("link", { name: dict.auth.elegirCarta })).toHaveAttribute("href", "#tus-cartas");
    expect(screen.queryByRole("link", { name: dict.auth.usarEnNueva })).toBeNull();
  });

  it("sin ninguna carta, la salida es calcular una, y dice por qué hace falta", () => {
    render(<Derechos derechos={ambos} dict={dict} locale="es" hayCartas={false} />);

    expect(screen.getByRole("link", { name: dict.auth.chartsEmptyCta })).toHaveAttribute("href", "/es/nueva");
    expect(screen.queryByRole("link", { name: dict.auth.elegirCarta })).toBeNull();
    expect(screen.getByText(dict.auth.listoSinCartasNota)).toBeInTheDocument();
  });

  it("aclara que nada se gasta hasta pedirlo en la carta", () => {
    render(<Derechos derechos={ambos} dict={dict} locale="es" hayCartas />);

    expect(screen.getByText(dict.auth.listoNota)).toBeInTheDocument();
  });

  it("comprar más queda al final, no en el medio", () => {
    render(<Derechos derechos={ambos} dict={dict} locale="es" hayCartas />);

    const enlaces = screen.getAllByRole("link").map((a) => a.textContent);
    expect(enlaces[enlaces.length - 1]).toContain(dict.auth.verPrecios);
  });
});
