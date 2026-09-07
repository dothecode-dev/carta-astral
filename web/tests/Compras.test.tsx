import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Compras } from "@/components/Compras";
import { getDict } from "@/lib/i18n";

const dict = getDict("es");

describe("Compras", () => {
  it("muestra qué compró y cuándo, con el nombre del producto", () => {
    render(
      <Compras
        compras={[
          {
            codigo_producto: "pack_5_natal", acreditada: true, created_at: "2026-09-03T12:00:00Z",
            monto_centavos: 12500, cupon: null, reembolsado_centavos: 0,
          },
        ]}
        locale="es"
        dict={dict}
      />,
    );

    expect(screen.getByText(dict.precios.nombre.pack_5_natal)).toBeInTheDocument();
    // El código interno no se le muestra a nadie.
    expect(screen.queryByText(/pack_5_natal/)).toBeNull();
  });

  it("una compra sin acreditar se ve como pendiente, no desaparece", () => {
    // Si alguien pagó y el webhook todavía no llegó, esconder la compra haría
    // pensar que se perdió la plata.
    render(
      <Compras
        compras={[
          {
            codigo_producto: "informe_natal", acreditada: false, created_at: "2026-09-03T12:00:00Z",
            monto_centavos: 2900, cupon: null, reembolsado_centavos: 0,
          },
        ]}
        locale="es"
        dict={dict}
      />,
    );

    expect(screen.getByText(dict.auth.compraPendiente)).toBeInTheDocument();
  });

  it("sin compras ofrece la tienda en vez de dejar el hueco vacío", () => {
    render(<Compras compras={[]} locale="es" dict={dict} />);

    expect(screen.getByText(dict.auth.comprasEmpty)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: dict.auth.verPrecios })).toHaveAttribute(
      "href", "/es/precios",
    );
  });
});

describe("Compras: cuánto, con qué cupón, y si volvió la plata", () => {
  const base = { codigo_producto: "informe_natal", acreditada: true, created_at: "2026-09-07T01:50:00Z" };

  it("dice lo que se pagó y el cupón con el que se pagó", () => {
    render(
      <Compras
        compras={[{ ...base, monto_centavos: 2030, cupon: "PROMO30", reembolsado_centavos: 0 }]}
        locale="es"
        dict={dict}
      />,
    );

    expect(screen.getByText(/20,30/)).toBeInTheDocument();
    expect(screen.getByText(/PROMO30/)).toBeInTheDocument();
  });

  it("un regalo del 100 % no dice US$ 0: dice gratis, con su cupón", () => {
    render(
      <Compras
        compras={[{ ...base, monto_centavos: 0, cupon: "REGALO", reembolsado_centavos: 0 }]}
        locale="es"
        dict={dict}
      />,
    );

    expect(screen.getByText(dict.precios.gratisPrecio)).toBeInTheDocument();
    expect(screen.queryByText(/US\$\s?0\b/)).toBeNull();
  });

  it("una compra reembolsada entera lo dice, y una parcial dice cuánto volvió", () => {
    render(
      <Compras
        compras={[
          { ...base, monto_centavos: 2030, cupon: "PROMO30", reembolsado_centavos: 2030 },
          {
            ...base, codigo_producto: "pack_5_natal", created_at: "2026-09-06T01:50:00Z",
            monto_centavos: 12500, cupon: null, reembolsado_centavos: 5000,
          },
        ]}
        locale="es"
        dict={dict}
      />,
    );

    expect(screen.getByText(dict.auth.compraReembolsada)).toBeInTheDocument();
    const parcial = new RegExp(dict.auth.compraReembolsoParcial.replace("{monto}", ".*50"));
    expect(screen.getByText(parcial)).toBeInTheDocument();
  });
});
