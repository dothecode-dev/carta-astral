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
          { codigo_producto: "pack_5_natal", acreditada: true, created_at: "2026-09-03T12:00:00Z" },
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
          { codigo_producto: "informe_natal", acreditada: false, created_at: "2026-09-03T12:00:00Z" },
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
