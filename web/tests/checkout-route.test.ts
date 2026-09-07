import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST as checkoutPost } from "@/app/api/checkout/route";
import { SESSION_COOKIE } from "@/lib/session";

type Cookie = { value: string; options?: Record<string, unknown> };
let store: Map<string, Cookie>;

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => store.get(name),
    set: (name: string, value: string, options?: Record<string, unknown>) =>
      store.set(name, { value, options }),
    delete: (name: string) => store.delete(name),
  }),
}));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const post = (body: unknown) =>
  new Request("http://x/api/checkout", { method: "POST", body: JSON.stringify(body) });

beforeEach(() => {
  store = new Map([[SESSION_COOKIE, { value: "un-token" }]]);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("/api/checkout con cupón", () => {
  it("pasa el cupón al backend tal cual", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ url: "https://checkout" }));
    vi.stubGlobal("fetch", fetchMock);

    await checkoutPost(post({ producto: "informe_natal", locale: "es", cupon: "PROMO30" }));

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({ producto: "informe_natal", cupon: "PROMO30" });
  });

  it("deja pasar el motivo del rechazo, que la pantalla traduce", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "el cupón no sirve", motivo: "agotado" }, 400)));

    const res = await checkoutPost(post({ producto: "informe_natal", cupon: "PROMO30" }));

    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "el cupón no sirve", motivo: "agotado" });
  });

  it("un 400 sin motivo sigue siendo «producto inválido»", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "falta el producto" }, 400)));

    const res = await checkoutPost(post({ producto: "nada" }));

    expect(await res.json()).toEqual({ error: "producto inválido" });
  });
});
