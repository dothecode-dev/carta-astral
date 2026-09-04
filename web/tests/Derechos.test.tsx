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

/** Las líneas de la lista, por su texto visible. */
const lineas = () => screen.queryAllByRole("listitem").map((li) => li.textContent);

describe("Derechos", () => {
  it("abre una línea por unidad disponible, no un recuento", () => {
    // El bloque decía "3 lecturas breves": informa cuántas hay, no qué hacer
    // con ellas. Cada línea es ahora una cosa que se puede hacer.
    render(
      <Derechos
        derechos={[derecho("lectura_breve", 3), derecho("informe_natal", 1)]}
        dict={dict}
        locale="es"
        hayCartas
      />,
    );

    expect(lineas().filter((t) => t?.includes(dict.auth.usoBreve))).toHaveLength(3);
    expect(lineas().filter((t) => t?.includes(dict.auth.usoInforme))).toHaveLength(1);
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

  it("no lista lo que ya se agotó", () => {
    render(
      <Derechos
        derechos={[derecho("lectura_breve", 0), derecho("informe_natal", 1)]}
        dict={dict}
        locale="es"
        hayCartas
      />,
    );

    expect(lineas()).toHaveLength(1);
    expect(lineas()[0]).toContain(dict.auth.usoInforme);
  });

  // Un pack de cinco da cinco renglones, que se leen bien. Tres packs darían
  // quince idénticos: ahí la lista deja de informar y se vuelve ruido.
  it("con demasiadas de un tipo vuelve al recuento agrupado", () => {
    render(
      <Derechos derechos={[derecho("informe_natal", 12)]} dict={dict} locale="es" hayCartas />,
    );

    expect(lineas()).toHaveLength(1);
    expect(screen.getByText(/12/)).toBeInTheDocument();
  });

  it("cinco todavía se listan de a una", () => {
    render(
      <Derechos derechos={[derecho("informe_natal", 5)]} dict={dict} locale="es" hayCartas />,
    );

    expect(lineas()).toHaveLength(5);
  });
});

describe("a dónde lleva cada línea", () => {
  const unInforme = [derecho("informe_natal", 1)];

  it("con cartas, a elegir una", () => {
    render(<Derechos derechos={unInforme} dict={dict} locale="es" hayCartas />);

    expect(screen.getByRole("link", { name: /Informe completo/ })).toHaveAttribute(
      "href",
      "#tus-cartas",
    );
  });

  it("sin ninguna carta todavía, a calcular la primera", () => {
    render(<Derechos derechos={unInforme} dict={dict} locale="es" hayCartas={false} />);

    expect(screen.getByRole("link", { name: /Informe completo/ })).toHaveAttribute(
      "href",
      "/es/nueva",
    );
  });

  it("comprar más queda debajo del listado, no en el medio", () => {
    render(<Derechos derechos={unInforme} dict={dict} locale="es" hayCartas />);

    const enlaces = screen.getAllByRole("link").map((a) => a.textContent);
    expect(enlaces[enlaces.length - 1]).toContain(dict.auth.verPrecios);
  });
});
