import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// RF23: la moneda del visitante. Cookie si vale una moneda conocida; si no,
// la que el backend deduce de la IP; ante cualquier falla, `usd`.
let cookieMoneda: string | undefined;

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => (name === "astra_moneda" && cookieMoneda !== undefined ? { value: cookieMoneda } : undefined),
  }),
  headers: async () => new Headers({ "x-forwarded-for": "200.1.2.3" }),
}));

import { MONEDAS, monedaDelVisitante, monedaPara } from "@/lib/moneda";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  cookieMoneda = undefined;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("monedaDelVisitante", () => {
  it("con la cookie elegida no le pregunta al backend", async () => {
    cookieMoneda = "brl";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    expect(await monedaDelVisitante()).toBe("brl");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sin cookie usa la que el backend deduce de la IP, reenviándole la IP", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ moneda: "brl", pais: "BR" }));
    vi.stubGlobal("fetch", fetchMock);

    expect(await monedaDelVisitante()).toBe("brl");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/moneda\/$/);
    expect((init.headers as Record<string, string>)["x-forwarded-for"]).toBe("200.1.2.3");
  });

  it("una cookie con cualquier otra cosa se ignora", async () => {
    cookieMoneda = "ars";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ moneda: "usd", pais: "AR" })));

    expect(await monedaDelVisitante()).toBe("usd");
  });

  it.each([
    ["el backend no responde", () => Promise.reject(new Error("timeout"))],
    ["el backend da error", () => Promise.resolve(json({}, 500))],
    ["el backend responde una moneda que no conocemos", () => Promise.resolve(json({ moneda: "ars" }))],
  ])("si %s, usd", async (_caso, respuesta) => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(respuesta));
    vi.spyOn(console, "warn").mockImplementation(() => {});

    expect(await monedaDelVisitante()).toBe("usd");
  });

  it("una falla de la consulta deja rastro en el log (no se traga en silencio)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("timeout")));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    await monedaDelVisitante();

    expect(warn).toHaveBeenCalledWith(expect.stringContaining("moneda"), expect.anything());
  });
});

describe("monedaPara", () => {
  const INFORME = { precios: { usd: 500, brl: 2490 } };
  const VINCULO = { precios: { usd: 900 } };

  it("la del visitante si el producto tiene precio en ella", () => {
    expect(monedaPara(INFORME, "brl")).toBe("brl");
  });

  it("usd si el producto no tiene precio en esa moneda (EC2)", () => {
    expect(monedaPara(VINCULO, "brl")).toBe("usd");
  });

  it("conoce usd y brl", () => {
    expect([...MONEDAS]).toEqual(["usd", "brl"]);
  });
});
