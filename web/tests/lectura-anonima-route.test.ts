import { beforeEach, describe, expect, it, vi } from "vitest";

const callApi = vi.fn();
vi.mock("@/lib/session", async () => {
  const real = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...real, callApi: (...a: unknown[]) => callApi(...a) };
});
let cookieActual: string | undefined;
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (n: string) => (n === "astra_lectura" && cookieActual ? { value: cookieActual } : undefined) }),
  headers: async () => new Headers(),
}));

import { ApiError } from "@/lib/session";
import { GET, POST } from "@/app/api/lectura-anonima/route";

const pedido = (body: unknown) =>
  new Request("http://x/api/lectura-anonima", { method: "POST", body: JSON.stringify(body) });

describe("POST /api/lectura-anonima", () => {
  beforeEach(() => { callApi.mockReset(); cookieActual = undefined; });

  it("202 pone la cookie con el token y no lo devuelve en el cuerpo", async () => {
    callApi.mockResolvedValue({ token: "tok", estado: "generando" });
    const res = await POST(pedido({ lang: "es" }));
    expect(res.status).toBe(202);
    expect(await res.json()).toEqual({ estado: "generando" });
    expect(res.headers.get("set-cookie")).toContain("astra_lectura=tok");
  });

  it("reenvía el token de la cookie en el header", async () => {
    cookieActual = "viejo";
    callApi.mockResolvedValue({ token: "viejo", estado: "generando" });
    await POST(pedido({ lang: "es" }));
    expect(callApi.mock.calls[0][1].headers).toEqual({ "X-Lectura-Token": "viejo" });
    expect(callApi.mock.calls[0][1].auth).toBe(false);
  });

  it.each([
    [409, "usado"], [429, "ip"], [503, "cupo"], [503, "ocupado"], [503, "mantenimiento"], [400, "datos"],
  ])("%s %s pasa con su motivo", async (status, motivo) => {
    callApi.mockRejectedValue(new ApiError(status, "x", JSON.stringify({ motivo })));
    const res = await POST(pedido({ lang: "es" }));
    expect(res.status).toBe(status);
    expect(await res.json()).toEqual({ motivo });
  });

  it("un 400 del parser del backend (sin motivo) es 400 datos, no 502", async () => {
    callApi.mockRejectedValue(new ApiError(400, "x", JSON.stringify({ detail: "JSON parse error" })));
    const res = await POST(pedido([1, 2]));
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ motivo: "datos" });
  });

  it("un cuerpo que no es JSON es 400 datos sin llamar al backend", async () => {
    const res = await POST(new Request("http://x/api/lectura-anonima", { method: "POST", body: "no json" }));
    expect(res.status).toBe(400);
    expect(callApi).not.toHaveBeenCalled();
  });

  it("cualquier otra cosa es 502", async () => {
    callApi.mockRejectedValue(new Error("red"));
    const res = await POST(pedido({ lang: "es" }));
    expect(res.status).toBe(502);
  });
});

describe("GET /api/lectura-anonima", () => {
  beforeEach(() => { callApi.mockReset(); cookieActual = undefined; });

  it("sin cookie es 404 sin llamar al backend", async () => {
    const res = await GET();
    expect(res.status).toBe(404);
    expect(callApi).not.toHaveBeenCalled();
  });

  it("con cookie devuelve lo del backend", async () => {
    cookieActual = "tok";
    callApi.mockResolvedValue({ estado: "lista", texto: "t", lang: "es", disclaimer: "d" });
    const res = await GET();
    expect(await res.json()).toEqual({ estado: "lista", texto: "t", lang: "es", disclaimer: "d" });
  });
});
