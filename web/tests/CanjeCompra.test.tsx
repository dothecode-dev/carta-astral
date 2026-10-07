import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CanjeCompra, POLL_MS, POLL_TRIES } from "@/components/CanjeCompra";
import { getDict, LOCALES } from "@/lib/i18n";

// La vuelta del pago de quien compró sin cuenta (RF13, RF14). Pregunta al canje
// y, según la respuesta, entra a la carta, pide el código o espera. Lo que más
// importa: sólo `pendiente` se vuelve a preguntar. Repetir el canje después de
// `codigo` mandaría otro mail; después de `sesion` o `invalido` no hay nada
// más que preguntar.

const replace = vi.fn();
const refresh = vi.fn();
const routerMock = { replace, refresh };
vi.mock("next/navigation", () => ({ useRouter: () => routerMock }));
const identificar = vi.fn();
vi.mock("@/lib/telemetry", () => ({ identificar: (id: number) => identificar(id), track: vi.fn() }));

const dict = getDict("es");
const CHECKOUT = "cs_test_a1Sh1ZbUWea0ALlpcnM7qsHid0vYGjWtPNhtxZOwIt1";
const CARTA = "/es/carta/58712ace-2602-4319-b8ed-785585b80955";

const reply = (status: number, body: unknown = {}) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

function renderCanje() {
  return render(<CanjeCompra locale="es" checkoutId={CHECKOUT} dict={dict} />);
}

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
  refresh.mockClear();
  identificar.mockClear();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CanjeCompra", () => {
  it("espera 2 minutos como máximo, preguntando cada 3 segundos", () => {
    expect(POLL_MS).toBe(3000);
    expect(POLL_MS * POLL_TRIES).toBe(120_000);
  });

  it("pide el canje de ESE checkout, por POST y sin nonce (lo pone el servidor)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, { estado: "pendiente" }));
    vi.stubGlobal("fetch", fetchMock);

    renderCanje();
    await correr();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/compra/canjear");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ checkout_id: CHECKOUT });
  });

  it("sesion: entra a la carta y refresca, y no vuelve a preguntar", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(reply(200, { estado: "sesion", destino: CARTA, account_id: 7 }));
    vi.stubGlobal("fetch", fetchMock);

    renderCanje();
    await correr(3);

    expect(replace).toHaveBeenCalledWith(CARTA);
    expect(refresh).toHaveBeenCalled();
    expect(identificar).toHaveBeenCalledWith(7);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["vacío", ""],
    ["externo", "https://malo.example"],
    ["protocol-relative", "//malo.example"],
    ["con barra invertida", "/\\malo.example"],
  ])("sesion con un destino %s: va a la cuenta", async (_m, destino) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(200, { estado: "sesion", destino })));

    renderCanje();
    await correr();

    expect(replace).toHaveBeenCalledWith("/es/cuenta");
  });

  it("codigo: muestra el mail enmascarado y el texto de soporte", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(reply(200, { estado: "codigo", email: "g***@gmail.com", destino: CARTA }));
    vi.stubGlobal("fetch", fetchMock);

    renderCanje();
    await correr(3);

    expect(screen.getByText(/g\*\*\*@gmail\.com/)).toBeInTheDocument();
    const soporte = screen.getByText(/info@astraguia\.com/);
    expect(soporte).toHaveTextContent("NhtxZOwIt1");
    expect(soporte).not.toHaveTextContent(CHECKOUT);
    expect(screen.getByRole("link", { name: dict.compra.canjeEntrar })).toHaveAttribute(
      "href",
      `/es/entrar?next=${encodeURIComponent(CARTA)}`,
    );
    expect(replace).not.toHaveBeenCalled();
    // Volver a canjear mandaría otro mail: con `codigo` se deja de preguntar.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("codigo con un destino que no es del sitio: el enlace no lo lleva", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(reply(200, { estado: "codigo", email: "g***@gmail.com", destino: "//malo" })),
    );

    renderCanje();
    await correr();

    expect(screen.getByRole("link", { name: dict.compra.canjeEntrar })).toHaveAttribute("href", "/es/entrar");
  });

  it("pendiente: sigue preguntando sin mandar a ningún lado", async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, { estado: "pendiente" }));
    vi.stubGlobal("fetch", fetchMock);

    renderCanje();
    await correr(3);

    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByText(dict.compra.body)).toBeInTheDocument();
  });

  it("pendiente y después sesion: entra", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(reply(200, { estado: "pendiente" }))
        .mockResolvedValue(reply(200, { estado: "sesion", destino: CARTA })),
    );

    renderCanje();
    await correr(2);

    expect(replace).toHaveBeenCalledWith(CARTA);
  });

  it("a los 2 minutos de pendiente: «tu pago está en proceso», y deja de preguntar", async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, { estado: "pendiente" }));
    vi.stubGlobal("fetch", fetchMock);

    renderCanje();
    await correr(POLL_TRIES + 1);
    const llamadas = fetchMock.mock.calls.length;
    await correr(5);

    expect(screen.getByText(dict.compra.canjeProcesoTitle)).toBeInTheDocument();
    expect(llamadas).toBe(POLL_TRIES);
    expect(fetchMock).toHaveBeenCalledTimes(llamadas);
  });

  it("invalido: lo dice, manda a la cuenta y deja de preguntar", async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, { estado: "invalido" }));
    vi.stubGlobal("fetch", fetchMock);

    renderCanje();
    await correr(3);

    expect(screen.getByText(dict.compra.canjeInvalidoTitle)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: dict.compra.irACuenta })).toHaveAttribute("href", "/es/cuenta");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("un corte de red o un 429 no rompen la espera", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockRejectedValueOnce(new Error("sin red"))
        .mockResolvedValueOnce(reply(429, { error: "demasiados" }))
        .mockResolvedValue(reply(200, { estado: "sesion", destino: CARTA })),
    );

    renderCanje();
    await correr(3);

    expect(replace).toHaveBeenCalledWith(CARTA);
  });
});

describe("textos del canje", () => {
  it.each(LOCALES)("%s: el soporte nombra el mail de contacto y el número de compra", (locale) => {
    const t = getDict(locale).compra;
    expect(t.canjeSoporte).toContain("info@astraguia.com");
    expect(t.canjeSoporte).toContain("{numero}");
    expect(t.canjeCodigoTitle).toContain("{email}");
  });
});
