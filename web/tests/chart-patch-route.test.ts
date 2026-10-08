import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PATCH } from "@/app/api/charts/[id]/route";
import { SESSION_COOKIE } from "@/lib/session";

// Cambiar el trato de una carta ya creada. La ruta sólo agrega la sesión (que
// sale de la cookie, nunca del cuerpo) y reenvía `{trato}` al backend.

let store: Map<string, { value: string }>;

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (name: string) => store.get(name) }),
  headers: async () => new Headers(),
}));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const ID = "58712ace-2602-4319-b8ed-785585b80955";
const ctx = { params: Promise.resolve({ id: ID }) };
const req = (body: unknown) =>
  new Request(`http://x/api/charts/${ID}`, { method: "PATCH", body: JSON.stringify(body) });

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  store = new Map([[SESSION_COOKIE, { value: "tok" }]]);
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("PATCH /api/charts/[id]", () => {
  it("reenvía {trato} al backend con la sesión y devuelve su respuesta", async () => {
    fetchMock.mockResolvedValue(json({ id: ID, trato: "femenino" }));

    const res = await PATCH(req({ trato: "femenino" }), ctx);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(new RegExp(`/api/charts/${ID}/$`));
    expect(init.method).toBe("PATCH");
    expect(init.headers.Authorization).toBe("Bearer tok");
    expect(JSON.parse(init.body)).toEqual({ trato: "femenino" });
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ id: ID, trato: "femenino" });
  });

  it("deja pasar el trato vacío (sin elegir)", async () => {
    fetchMock.mockResolvedValue(json({ id: ID, trato: "" }));
    await PATCH(req({ trato: "" }), ctx);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ trato: "" });
  });

  it("sin sesión: 401 y no llama al backend", async () => {
    store.clear();
    const res = await PATCH(req({ trato: "neutro" }), ctx);
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("cuerpo que no es JSON: 400 sin llamar al backend", async () => {
    const res = await PATCH(new Request("http://x", { method: "PATCH", body: "no" }), ctx);
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("traduce el 400 y el 404 del backend", async () => {
    fetchMock.mockResolvedValueOnce(json({ error: "trato inválido" }, 400));
    expect((await PATCH(req({ trato: "x" }), ctx)).status).toBe(400);
    fetchMock.mockResolvedValueOnce(json({}, 404));
    expect((await PATCH(req({ trato: "neutro" }), ctx)).status).toBe(404);
  });

  it("cualquier otro fallo del backend: 502", async () => {
    fetchMock.mockResolvedValue(json({}, 500));
    expect((await PATCH(req({ trato: "neutro" }), ctx)).status).toBe(502);
  });
});
