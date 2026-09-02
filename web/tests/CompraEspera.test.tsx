import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompraEspera, POLL_MS, POLL_TRIES } from "@/components/CompraEspera";
import { getDict } from "@/lib/i18n";

// Adónde va quien vuelve de pagar, y qué ve mientras tanto.
//
// La pantalla existe por una carrera: Polar redirige el navegador al instante y
// su webhook —el que acredita— puede llegar unos segundos después. Mandar de
// una a la carta sería mostrarle el botón de comprar a alguien que acaba de
// pagar, que es el bug que costó el 02-09-2026.

const replace = vi.fn();
// Referencia estable, como el `useRouter()` real: uno nuevo por llamada
// dispararía de nuevo el efecto que sondea, en cada render.
const routerMock = { replace };
vi.mock("next/navigation", () => ({ useRouter: () => routerMock }));

const dict = getDict("es");
const CHECKOUT = "polar_c_Kx5P6blTxLQQE4yA69NVfeLeMowXxRac";
const CARTA = "58712ace-2602-4319-b8ed-785585b80955";

const reply = (status: number, body: unknown = {}) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

function renderEspera() {
  return render(<CompraEspera locale="es" checkoutId={CHECKOUT} dict={dict} />);
}

/** Deja correr los timers y las promesas pendientes del sondeo. */
async function correr(veces = 1) {
  for (let i = 0; i < veces; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS);
    });
  }
}

beforeEach(() => {
  vi.useFakeTimers();
  replace.mockClear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("CompraEspera", () => {
  it("con la compra acreditada y una carta, lleva a esa carta", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        reply(200, { estado: "acreditado", destino: { tipo: "carta", id: CARTA } }),
      ),
    );

    renderEspera();
    await correr();

    expect(replace).toHaveBeenCalledWith(`/es/carta/${CARTA}`);
  });

  it("con un pack, lleva a la cuenta", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(reply(200, { estado: "acreditado", destino: { tipo: "cuenta" } })),
    );

    renderEspera();
    await correr();

    expect(replace).toHaveBeenCalledWith("/es/cuenta");
  });

  it("mientras el pago no está confirmado, espera sin mandar a ningún lado", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(200, { estado: "pendiente" })));

    renderEspera();
    await correr(3);

    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByText(dict.compra.body)).toBeInTheDocument();
  });

  it("si la confirmación nunca llega, lo dice sin pedir que pague de nuevo", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(200, { estado: "pendiente" })));

    renderEspera();
    await correr(POLL_TRIES + 1);

    expect(screen.getByText(dict.compra.demoraTitle)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: dict.compra.irACuenta })).toHaveAttribute(
      "href",
      "/es/cuenta",
    );
    expect(replace).not.toHaveBeenCalled();
  });

  it("un corte de red no rompe la espera: sigue sondeando", async () => {
    // Sin el try/catch del componente, el rechazo del fetch abortaba el bucle
    // entero y dejaba la animación girando para siempre.
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("sin red"))
      .mockResolvedValue(reply(200, { estado: "acreditado", destino: { tipo: "cuenta" } }));
    vi.stubGlobal("fetch", fetchMock);

    renderEspera();
    await correr(2);

    expect(replace).toHaveBeenCalledWith("/es/cuenta");
  });

  it("si la sesión se venció mientras pagaba, manda a entrar", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(401, { error: "sin sesión" })));

    renderEspera();
    await correr();

    expect(replace).toHaveBeenCalledWith("/es/entrar");
  });

  it("un checkout que no es de esta cuenta no se espera para siempre", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(404, { error: "no existe" })));

    renderEspera();
    await correr();

    expect(screen.getByText(dict.compra.demoraTitle)).toBeInTheDocument();
  });
});
