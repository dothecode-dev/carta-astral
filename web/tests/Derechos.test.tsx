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

// Lo que la cuenta tiene para usar, y a qué se le asigna. El caso que esto
// tiene que cubrir (06-09-2026): «tengo un informe pago y quiero dárselo a
// Carlos, que todavía no tiene carta, sin gastar una lectura gratuita». Antes
// había una fila por unidad que sólo hacía scroll, y ese camino no existía.

describe("Derechos", () => {
  it("una línea por producto, con cuántas quedan", () => {
    render(
      <Derechos
        derechos={[derecho("lectura_breve", 3), derecho("informe_natal", 1)]}
        dict={dict}
        locale="es"
        hayCartas
      />,
    );

    expect(lineas()).toHaveLength(2);
    expect(lineas()[0]).toContain(dict.auth.derechosBreve.replace("{n}", "3"));
    expect(lineas()[1]).toContain(dict.auth.derechosInformeUno);
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
    expect(lineas()[0]).toContain(dict.auth.derechosInformeUno);
  });
});

describe("a qué se asigna cada cosa", () => {
  const ambos = [derecho("lectura_breve", 2), derecho("informe_natal", 1)];

  it("cada producto se puede usar en una carta nueva, sin pasar por las que existen", () => {
    render(<Derechos derechos={ambos} dict={dict} locale="es" hayCartas />);

    const nuevas = screen.getAllByRole("link", { name: dict.auth.usarEnNueva });
    expect(nuevas.map((a) => a.getAttribute("href"))).toEqual(["/es/nueva", "/es/nueva"]);
  });

  it("con cartas, también en una de las que ya tiene", () => {
    render(<Derechos derechos={ambos} dict={dict} locale="es" hayCartas />);

    const mias = screen.getAllByRole("link", { name: dict.auth.usarEnMisCartas });
    expect(mias).toHaveLength(2);
    expect(mias[0]).toHaveAttribute("href", "#tus-cartas");
  });

  it("sin ninguna carta, sólo la nueva, y dice por qué hace falta una", () => {
    render(<Derechos derechos={ambos} dict={dict} locale="es" hayCartas={false} />);

    expect(screen.queryByRole("link", { name: dict.auth.usarEnMisCartas })).toBeNull();
    expect(screen.getAllByRole("link", { name: dict.auth.usarEnNueva })).toHaveLength(2);
    expect(screen.getByText(dict.auth.listoSinCartasNota)).toBeInTheDocument();
  });

  it("aclara que nada se gasta hasta pedirlo en la carta", () => {
    render(<Derechos derechos={ambos} dict={dict} locale="es" hayCartas />);

    expect(screen.getByText(dict.auth.listoNota)).toBeInTheDocument();
  });

  it("comprar más queda debajo del listado, no en el medio", () => {
    render(<Derechos derechos={ambos} dict={dict} locale="es" hayCartas />);

    const enlaces = screen.getAllByRole("link").map((a) => a.textContent);
    expect(enlaces[enlaces.length - 1]).toContain(dict.auth.verPrecios);
  });
});
