import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ComprarBoton } from "@/components/ComprarBoton";
import { getDict } from "@/lib/i18n";

const dict = getDict("es");

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ComprarBoton", () => {
  it("sin sesión manda a entrar en vez de fallar con un 401", () => {
    render(<ComprarBoton codigo="pack_5_natal" locale="es" dict={dict} signedIn={false} />);

    expect(screen.getByRole("link", { name: dict.precios.comprar })).toHaveAttribute(
      "href", "/es/entrar",
    );
  });

  it("con sesión abre el checkout del producto que se eligió", async () => {
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      value: { assign }, writable: true, configurable: true,
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ url: "https://checkout.stripe.com/c/pay/cs_test_1" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ComprarBoton codigo="pack_5_natal" locale="es" dict={dict} signedIn />);
    await userEvent.click(screen.getByRole("button", { name: dict.precios.comprar }));

    // El producto viaja: es lo que hacía falta para poder vender los packs.
    const enviado = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(enviado).toEqual({ producto: "pack_5_natal", locale: "es" });
    // Y sin carta atada: el derecho se usa después, en la que la persona elija.
    expect(enviado.chart_id).toBeUndefined();
    expect(assign).toHaveBeenCalledWith("https://checkout.stripe.com/c/pay/cs_test_1");
  });

  it("si el checkout no abre, lo dice y deja reintentar", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));

    render(<ComprarBoton codigo="informe_natal" locale="es" dict={dict} signedIn />);
    await userEvent.click(screen.getByRole("button", { name: dict.precios.comprar }));

    expect(await screen.findByRole("alert")).toHaveTextContent(dict.precios.fallo);
    expect(screen.getByRole("button", { name: dict.precios.comprar })).toBeEnabled();
  });
});
