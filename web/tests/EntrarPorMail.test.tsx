import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EntrarPorMail } from "@/components/EntrarPorMail";
import { getDict } from "@/lib/i18n";
import { identificar as identificarReal, track as trackReal } from "@/lib/telemetry";

// La puerta de acceso por mail: pedir el código de 6 dígitos y canjearlo,
// RF15/RF16. El backend ya está probado aparte (tests de
// api/session/codigo y api/session); acá lo que importa es que el
// componente hable bien con esas dos rutas y deje rastro de cada paso.

vi.mock("@/lib/telemetry", () => ({ track: vi.fn(), identificar: vi.fn() }));
const track = vi.mocked(trackReal);
const identificar = vi.mocked(identificarReal);

const replace = vi.fn();
const refresh = vi.fn();
const router = { replace, refresh };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const dict = getDict("es");
const labels = {
  mailLabel: dict.auth.mailLabel,
  mailPlaceholder: dict.auth.mailPlaceholder,
  mailButton: dict.auth.mailButton,
  codigoLabel: dict.auth.codigoLabel,
  codigoPlaceholder: dict.auth.codigoPlaceholder,
  codigoHelp: dict.auth.codigoHelp,
  codigoButton: dict.auth.codigoButton,
  enviando: dict.auth.enviando,
  reenviar: dict.auth.reenviar,
  cambiarMail: dict.auth.cambiarMail,
  codigoInvalido: dict.auth.codigoInvalido,
  demasiadosIntentos: dict.auth.demasiadosIntentos,
  noDisponible: dict.auth.noDisponible,
  errorRed: dict.auth.errorRed,
};

const reply = (status: number, body: unknown = {}) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

/** Escribe el mail y pide el código. Deja el componente en el paso 2. */
async function pedirCodigo(email: string) {
  fireEvent.change(screen.getByLabelText(labels.mailLabel), { target: { value: email } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: labels.mailButton }));
  });
}

async function canjearCodigo(codigo: string) {
  fireEvent.change(screen.getByLabelText(labels.codigoLabel), { target: { value: codigo } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: labels.codigoButton }));
  });
}

beforeEach(() => {
  replace.mockClear();
  refresh.mockClear();
  track.mockClear();
  identificar.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("EntrarPorMail — pedir el código", () => {
  it("el input de mail tiene label, type y autocomplete de verdad", () => {
    render(<EntrarPorMail locale="es" labels={labels} />);

    const input = screen.getByLabelText(labels.mailLabel);
    expect(input).toHaveAttribute("type", "email");
    expect(input).toHaveAttribute("autocomplete", "email");
  });

  it("pide el código con el mail, el idioma y el destino, y mide el pedido", async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(202));
    vi.stubGlobal("fetch", fetchMock);

    render(<EntrarPorMail locale="es" next="/es/precios" labels={labels} />);
    await pedirCodigo("juan@gmail.com");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/session/codigo");
    expect(JSON.parse(init.body)).toEqual({
      email: "juan@gmail.com",
      lang: "es",
      destino: "/es/precios",
    });
    expect(track).toHaveBeenCalledWith("codigo_pedido", {});
    // Pasó al paso 2: ya se ve el campo del código.
    expect(screen.getByLabelText(labels.codigoLabel)).toBeInTheDocument();
  });

  it("sin destino manda la cadena vacía, no undefined ni null", async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(202));
    vi.stubGlobal("fetch", fetchMock);

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");

    expect(JSON.parse(fetchMock.mock.calls[0][1].body).destino).toBe("");
  });

  it("un 429 al pedir deja el formulario en el paso 1, con aviso y medición", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(429, { error: "demasiados pedidos" })));

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");

    expect(screen.getByText(labels.demasiadosIntentos)).toBeInTheDocument();
    // Sigue en el paso 1: no apareció el campo del código.
    expect(screen.queryByLabelText(labels.codigoLabel)).not.toBeInTheDocument();
    expect(track).toHaveBeenCalledWith("codigo_fallido", { paso: "pedido", motivo: "demasiados" });
  });

  it("un 503 al pedir avisa que el acceso por mail no está disponible", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(503, { error: "login no disponible" })));

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");

    expect(screen.getByText(labels.noDisponible)).toBeInTheDocument();
    expect(track).toHaveBeenCalledWith("codigo_fallido", { paso: "pedido", motivo: "no_disponible" });
  });

  it("si el fetch del pedido ni vuelve (red caída), lo dice y lo mide", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");

    expect(screen.getByText(labels.errorRed)).toBeInTheDocument();
    expect(track).toHaveBeenCalledWith("codigo_fallido", { paso: "pedido", motivo: "red" });
    expect(consoleError).toHaveBeenCalled();
    for (const [, ...args] of consoleError.mock.calls) {
      expect(args.join(" ")).not.toContain("juan@gmail.com");
    }
    consoleError.mockRestore();
  });
});

describe("EntrarPorMail — el paso del código", () => {
  it("deja que iOS lo autocomplete desde Mail (autocomplete + inputmode)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(202)));

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");

    const input = screen.getByLabelText(labels.codigoLabel);
    expect(input).toHaveAttribute("autocomplete", "one-time-code");
    expect(input).toHaveAttribute("inputmode", "numeric");
  });

  it("avisa que puede tardar y que hay que mirar spam", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(202)));

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");

    expect(screen.getByText(/tardar/i)).toBeInTheDocument();
    expect(screen.getByText(/spam/i)).toBeInTheDocument();
  });

  it("el reenvío recién se habilita a los 60 segundos", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(202)));

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");

    expect(screen.getByRole("button", { name: labels.reenviar })).toBeDisabled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(screen.getByRole("button", { name: labels.reenviar })).toBeEnabled();
  });

  it("reenviar pide el código de nuevo para el MISMO mail", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue(reply(202));
    vi.stubGlobal("fetch", fetchMock);

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: labels.reenviar }));
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).email).toBe("juan@gmail.com");
    expect(track).toHaveBeenCalledWith("codigo_pedido", {});
  });

  it("cambiar de mail vuelve al paso 1 sin perder lo escrito", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(202)));

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");

    fireEvent.click(screen.getByRole("button", { name: labels.cambiarMail }));

    expect(screen.getByLabelText(labels.mailLabel)).toHaveValue("juan@gmail.com");
  });

  it("«Usar otro mail» no revive el paso 1 mientras el canje sigue en vuelo", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(reply(202));
    vi.stubGlobal("fetch", fetchMock);

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");

    // El canje que sigue colgado hasta que esta prueba lo resuelva a mano.
    let resolverCanje: (value: unknown) => void = () => {};
    const canjeEnVuelo = new Promise((resolve) => {
      resolverCanje = resolve;
    });
    fetchMock.mockReturnValueOnce(canjeEnVuelo);

    fireEvent.change(screen.getByLabelText(labels.codigoLabel), { target: { value: "123456" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: labels.codigoButton }));
    });

    // Con el canje todavía en vuelo (enviando === true), "Usar otro mail"
    // tiene que estar deshabilitado igual que el submit y el reenviar.
    expect(screen.getByRole("button", { name: labels.cambiarMail })).toBeDisabled();

    // Se resuelve para no dejar una promesa colgada entre pruebas.
    await act(async () => {
      resolverCanje(reply(200, { account_id: 1 }));
      await canjeEnVuelo;
    });
  });

  it("un código equivocado (401) deja el paso 2 usable, con mensaje", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(reply(202));
    vi.stubGlobal("fetch", fetchMock);

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");

    fetchMock.mockResolvedValueOnce(reply(401, { error: "no pudimos verificar tu identidad" }));
    await canjearCodigo("000000");

    expect(screen.getByText(labels.codigoInvalido)).toBeInTheDocument();
    // Sigue en el paso 2: el campo del código sigue ahí, usable.
    const input = screen.getByLabelText(labels.codigoLabel);
    expect(input).toBeInTheDocument();
    expect(input).not.toBeDisabled();
    expect(replace).not.toHaveBeenCalled();
    expect(track).toHaveBeenCalledWith("codigo_fallido", { paso: "canje", motivo: "invalido" });
  });

  it("un 429 al canjear avisa de demasiados intentos", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(reply(202));
    vi.stubGlobal("fetch", fetchMock);

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");

    fetchMock.mockResolvedValueOnce(reply(429, { error: "demasiados intentos" }));
    await canjearCodigo("123456");

    expect(screen.getByText(labels.demasiadosIntentos)).toBeInTheDocument();
    expect(track).toHaveBeenCalledWith("codigo_fallido", { paso: "canje", motivo: "demasiados" });
  });

  it("si el fetch del canje ni vuelve, lo dice y lo mide sin exponer el código", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const fetchMock = vi.fn().mockResolvedValueOnce(reply(202));
    vi.stubGlobal("fetch", fetchMock);

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");

    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await canjearCodigo("654321");

    expect(screen.getByText(labels.errorRed)).toBeInTheDocument();
    expect(track).toHaveBeenCalledWith("codigo_fallido", { paso: "canje", motivo: "red" });
    for (const [, ...args] of consoleError.mock.calls) {
      expect(args.join(" ")).not.toContain("654321");
    }
    consoleError.mockRestore();
  });
});

describe("EntrarPorMail — el canje exitoso", () => {
  it("canjea, identifica la cuenta y mide el canje y el login compartido", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValueOnce(reply(200, { account_id: 42, derechos: [] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");
    await canjearCodigo("123456");

    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/session");
    expect(JSON.parse(init.body)).toEqual({
      provider: "email",
      email: "juan@gmail.com",
      codigo: "123456",
    });
    expect(identificar).toHaveBeenCalledWith(42);
    expect(track).toHaveBeenCalledWith("codigo_canjeado", {});
    expect(track).toHaveBeenCalledWith("login", { provider: "email" });
    expect(refresh).toHaveBeenCalled();
  });

  it("con next en la URL, next manda por sobre el destino que devuelve el canje", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValueOnce(reply(200, { account_id: 1, destino: "/es/nueva" }));
    vi.stubGlobal("fetch", fetchMock);

    render(<EntrarPorMail locale="es" next="/es/precios" labels={labels} />);
    await pedirCodigo("juan@gmail.com");
    await canjearCodigo("123456");

    expect(replace).toHaveBeenCalledWith("/es/precios");
  });

  it("sin next, usa el destino de respaldo que trae el canje (RF16)", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValueOnce(reply(200, { account_id: 1, destino: "/es/nueva" }));
    vi.stubGlobal("fetch", fetchMock);

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");
    await canjearCodigo("123456");

    expect(replace).toHaveBeenCalledWith("/es/nueva");
  });

  it("sin next y sin destino, va a la cuenta", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValueOnce(reply(200, { account_id: 1 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<EntrarPorMail locale="es" labels={labels} />);
    await pedirCodigo("juan@gmail.com");
    await canjearCodigo("123456");

    expect(replace).toHaveBeenCalledWith("/es/cuenta");
  });
});
