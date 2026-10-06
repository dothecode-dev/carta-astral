import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/vinculo/preview/route";
import { SESSION_COOKIE } from "@/lib/session";

// El BFF de la vista previa de Vínculo: el navegador le habla a esta ruta y
// ésta al backend. Se prueba contra el `callApi` real, con el `fetch` y el
// almacén de cookies reemplazados, como `bff.test.ts`.

type Cookie = { value: string };
let store: Map<string, Cookie>;

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => store.get(name),
    set: () => {},
    delete: () => {},
  }),
  headers: async () => new Headers(),
}));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const post = (body: unknown) =>
  new Request("http://x/api/vinculo/preview", { method: "POST", body: JSON.stringify(body) });

const PERSONA = { date: "1976-05-31", time: "19:30", time_known: true, lat: -34.5, lng: -58.5 };

beforeEach(() => {
  store = new Map([[SESSION_COOKIE, { value: "un-token" }]]);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("POST /api/vinculo/preview", () => {
  it("reenvía al backend sin la sesión y devuelve el preview", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ a: {}, b: {}, aspectos: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const r = await POST(post({ lang: "es", a: PERSONA, b: PERSONA }));

    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ a: {}, b: {}, aspectos: [] });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/vinculo\/preview\/$/);
    // Quien mira la vista previa puede tener sesión, pero el cálculo no la usa.
    expect(init.headers.Authorization).toBeUndefined();
  });

  it("sólo reenvía lang, a y b: un campo de más no llega al backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ a: {}, b: {}, aspectos: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await POST(post({ lang: "es", a: PERSONA, b: PERSONA, alias: { a: "Ana" }, extra: 1 }));

    const enviado = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(Object.keys(enviado).sort()).toEqual(["a", "b", "lang"]);
    expect(JSON.stringify(enviado)).not.toContain("Ana");
  });

  it("pasa el motivo del 400 si es uno conocido", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "misma_persona" }, 400)));
    const r = await POST(post({ lang: "es", a: PERSONA, b: PERSONA }));
    expect(r.status).toBe(400);
    expect(await r.json()).toEqual({ error: "misma_persona" });
  });

  it("un motivo desconocido del 400 se reduce a datos_invalidos", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "<script>x</script>" }, 400)));
    const r = await POST(post({ lang: "es", a: PERSONA, b: PERSONA }));
    expect(r.status).toBe(400);
    expect(await r.json()).toEqual({ error: "datos_invalidos" });
  });

  it("un 400 con cuerpo que no es JSON también es datos_invalidos", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("boom", { status: 400 })));
    const r = await POST(post({ lang: "es", a: PERSONA, b: PERSONA }));
    expect(r.status).toBe(400);
    expect(await r.json()).toEqual({ error: "datos_invalidos" });
  });

  it("429 dice demasiadas", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({}, 429)));
    const r = await POST(post({ lang: "es", a: PERSONA, b: PERSONA }));
    expect(r.status).toBe(429);
    expect(await r.json()).toEqual({ error: "demasiadas" });
  });

  it("404 del backend (flag apagado) es 404", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({}, 404)));
    const r = await POST(post({ lang: "es", a: PERSONA, b: PERSONA }));
    expect(r.status).toBe(404);
  });

  it("un 500 del backend es 502 no_disponible y no filtra el cuerpo", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Traceback: fecha 1976", { status: 500 })));
    const r = await POST(post({ lang: "es", a: PERSONA, b: PERSONA }));
    expect(r.status).toBe(502);
    const cuerpo = await r.json();
    expect(cuerpo).toEqual({ error: "no_disponible" });
  });

  it("si la red se cae, 502 no_disponible", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    const r = await POST(post({ lang: "es", a: PERSONA, b: PERSONA }));
    expect(r.status).toBe(502);
    expect(await r.json()).toEqual({ error: "no_disponible" });
  });

  it("un cuerpo que no es JSON es 400 sin llamar al backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const r = await POST(new Request("http://x", { method: "POST", body: "{" }));
    expect(r.status).toBe(400);
    expect(await r.json()).toEqual({ error: "datos_invalidos" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("un JSON que no es objeto es 400 sin llamar al backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const r = await POST(post([1, 2]));
    expect(r.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
