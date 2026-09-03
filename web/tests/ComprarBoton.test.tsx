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

    // Con a dónde volver y qué venía a comprar: sin eso, el login lo depositaba
    // en su cuenta vacía y la compra se perdía en el camino.
    expect(screen.getByRole("link", { name: dict.precios.comprar })).toHaveAttribute(
      "href", "/es/entrar?next=%2Fes%2Fprecios&comprar=pack_5_natal",
    );
  });

  it("al volver del login abre el checkout de lo que se había pedido, una sola vez", async () => {
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      value: { assign }, writable: true, configurable: true,
    });
    const replaceState = vi.spyOn(window.history, "replaceState");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ url: "https://checkout.stripe.com/c/pay/cs_test_1" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(
      <ComprarBoton codigo="pack_5_natal" locale="es" dict={dict} signedIn reanudar />,
    );
    await screen.findByRole("button");
    rerender(<ComprarBoton codigo="pack_5_natal" locale="es" dict={dict} signedIn reanudar />);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      producto: "pack_5_natal", locale: "es",
    });
    // La URL queda sin el pedido: volver de Stripe con el botón "atrás" no
    // puede relanzarle el pago a quien acaba de decidir que no.
    expect(replaceState).toHaveBeenCalledWith(null, "", "/es/precios");
  });

  it("no reanuda nada si no se pidió", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<ComprarBoton codigo="pack_5_natal" locale="es" dict={dict} signedIn />);
    await screen.findByRole("button");

    expect(fetchMock).not.toHaveBeenCalled();
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
