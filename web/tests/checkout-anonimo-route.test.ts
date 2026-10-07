import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/checkout/anonimo/route";
import { SESSION_COOKIE } from "@/lib/session";

// Abre el pago de quien no tiene cuenta (RF1, RF2). El backend devuelve el
// nonce del navegador; esta ruta lo guarda en una cookie httpOnly propia de ese
// checkout y al JS de la página le devuelve SÓLO la URL de Stripe: un nonce que
// llegara al cliente se podría leer desde cualquier script de la página.

type Cookie = { value: string; options?: Record<string, unknown> };
let store: Map<string, Cookie>;
let ipVisitante: string | null;

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => store.get(name),
    set: (name: string, value: string, options?: Record<string, unknown>) =>
      store.set(name, { value, options }),
    delete: (name: string) => store.delete(name),
  }),
  headers: async () => new Headers(ipVisitante ? { "x-forwarded-for": ipVisitante } : {}),
}));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const req = (body: unknown) =>
  new Request("http://x/api/checkout/anonimo", { method: "POST", body: JSON.stringify(body) });

const OK = { url: "https://checkout.stripe.com/x", checkout_id: "cs_test_1", nonce: "N" };

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  store = new Map();
  ipVisitante = null;
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("POST /api/checkout/anonimo", () => {
  it("con 200 del backend pone la cookie del nonce y no devuelve el nonce", async () => {
    fetchMock.mockResolvedValue(json(OK));

    const res = await POST(req({ date: "1990-05-10" }));

    expect(await res.json()).toEqual({ url: "https://checkout.stripe.com/x" });
    const cookie = res.headers.get("set-cookie")!;
    expect(cookie).toContain("astra_compra_cs_test_1=N");
    expect(cookie.toLowerCase()).toContain("httponly");
    expect(cookie.toLowerCase()).toContain("samesite=lax");
    expect(cookie).toContain("Max-Age=86400");
    expect(cookie).toContain("Path=/");
  });

  it("le pega al endpoint anónimo, sin sesión aunque haya una", async () => {
    store.set(SESSION_COOKIE, { value: "token-de-otro" });
    fetchMock.mockResolvedValue(json(OK));

    await POST(req({ date: "1990-05-10", locale: "es", cupon: "PROMO30" }));

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/checkout\/anonimo\/$/);
    expect(init.method).toBe("POST");
    expect(init.headers).not.toHaveProperty("Authorization");
    expect(JSON.parse(init.body)).toEqual({ date: "1990-05-10", locale: "es", cupon: "PROMO30" });
  });

  it("reenvía la IP del visitante, para que el techo del backend sea por persona", async () => {
    ipVisitante = "203.0.113.7";
    fetchMock.mockResolvedValue(json(OK));

    await POST(req({ date: "1990-05-10" }));

    expect(fetchMock.mock.calls[0][1].headers).toMatchObject({ "x-forwarded-for": "203.0.113.7" });
  });

  it("un checkout_id con forma rara no se convierte en cookie", async () => {
    fetchMock.mockResolvedValue(json({ ...OK, checkout_id: "x;y=z" }));

    const res = await POST(req({ date: "1990-05-10" }));

    expect(res.status).toBe(502);
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  it("cupón de 100 %: deja pasar el motivo `requiere_cuenta`", async () => {
    fetchMock.mockResolvedValue(json({ error: "el cupón no sirve sin cuenta", motivo: "requiere_cuenta" }, 400));

    const res = await POST(req({ date: "1990-05-10", cupon: "GRATIS" }));

    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "el cupón no sirve", motivo: "requiere_cuenta" });
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  it("429 y 503 llegan como tales", async () => {
    fetchMock.mockResolvedValueOnce(json({}, 429)).mockResolvedValueOnce(json({}, 503));

    expect((await POST(req({}))).status).toBe(429);
    expect((await POST(req({}))).status).toBe(503);
  });

  it("cualquier otra falla del backend es un 502", async () => {
    fetchMock.mockResolvedValue(json({}, 500));

    expect((await POST(req({}))).status).toBe(502);
  });

  it("un cuerpo ilegible es 400 sin llamar al backend", async () => {
    const res = await POST(new Request("http://x/api/checkout/anonimo", { method: "POST", body: "{" }));

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
