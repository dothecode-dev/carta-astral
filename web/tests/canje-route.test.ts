import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/compra/canjear/route";
import { SESSION_COOKIE } from "@/lib/session";

// El canje de la vuelta del pago (RF10-RF14). La ruta lee el nonce de la
// cookie de ESE checkout —nunca del cuerpo, que escribe cualquiera— y se lo
// manda al backend. Si el backend abre sesión, el token va a la cookie de
// sesión (reemplazando la que hubiera: la compra es de esta persona) y jamás
// al cuerpo de la respuesta.

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

const CHECKOUT = "cs_test_a1B2";
const COOKIE = `astra_compra_${CHECKOUT}`;
const CARTA = "/es/carta/58712ace-2602-4319-b8ed-785585b80955";

const req = (body: unknown) =>
  new Request("http://x/api/compra/canjear", { method: "POST", body: JSON.stringify(body) });

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  store = new Map([[COOKIE, { value: "el-nonce" }]]);
  ipVisitante = null;
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("POST /api/compra/canjear", () => {
  it("manda al backend el checkout y el nonce de su cookie, sin sesión", async () => {
    store.set(SESSION_COOKIE, { value: "token-de-otro" });
    fetchMock.mockResolvedValue(json({ estado: "pendiente" }));

    await POST(req({ checkout_id: CHECKOUT }));

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/checkout\/anonimo\/canjear\/$/);
    expect(JSON.parse(init.body)).toEqual({ checkout_id: CHECKOUT, nonce: "el-nonce" });
    expect(init.headers).not.toHaveProperty("Authorization");
  });

  it("reenvía la IP del visitante (el techo `canje_compra` es por IP)", async () => {
    ipVisitante = "203.0.113.7";
    fetchMock.mockResolvedValue(json({ estado: "pendiente" }));

    await POST(req({ checkout_id: CHECKOUT }));

    expect(fetchMock.mock.calls[0][1].headers).toMatchObject({ "x-forwarded-for": "203.0.113.7" });
  });

  it("sesion: guarda la sesión y borra la cookie del nonce", async () => {
    fetchMock.mockResolvedValue(json({ estado: "sesion", token: "secreto", destino: CARTA, account_id: 7 }));

    const res = await POST(req({ checkout_id: CHECKOUT }));
    const cuerpo = await res.json();

    expect(cuerpo).toEqual({ estado: "sesion", destino: CARTA, account_id: 7 });
    expect(JSON.stringify(cuerpo)).not.toContain("secreto");
    expect(store.get(SESSION_COOKIE)?.value).toBe("secreto");
    expect(store.get(SESSION_COOKIE)?.options).toMatchObject({ httpOnly: true });
    expect(store.has(COOKIE)).toBe(false);
  });

  it("sesion con otra cuenta abierta: la reemplaza", async () => {
    store.set(SESSION_COOKIE, { value: "token-de-otro" });
    fetchMock.mockResolvedValue(json({ estado: "sesion", token: "nuevo", destino: CARTA, account_id: 7 }));

    await POST(req({ checkout_id: CHECKOUT }));

    expect(store.get(SESSION_COOKIE)?.value).toBe("nuevo");
  });

  it.each([
    ["a otro sitio", "https://malo.example/x"],
    ["protocol-relative", "//malo.example/x"],
    ["con barra invertida", "/\\malo.example"],
    ["fuera de la lista", "/es/algo-raro"],
  ])("un destino %s no se devuelve: cae a la cuenta", async (_m, destino) => {
    fetchMock.mockResolvedValue(json({ estado: "sesion", token: "t", destino, account_id: 7 }));

    const cuerpo = await (await POST(req({ checkout_id: CHECKOUT }))).json();

    expect(cuerpo.destino).toBe("");
  });

  it("codigo: devuelve el mail enmascarado y el destino, sin sesión", async () => {
    fetchMock.mockResolvedValue(json({ estado: "codigo", email: "g***@gmail.com", destino: CARTA }));

    const res = await POST(req({ checkout_id: CHECKOUT }));

    expect(await res.json()).toEqual({ estado: "codigo", email: "g***@gmail.com", destino: CARTA });
    expect(store.has(SESSION_COOKIE)).toBe(false);
  });

  it("RF5b: reenvía saldo_pendiente en sesion y en codigo", async () => {
    fetchMock.mockResolvedValueOnce(
      json({ estado: "sesion", token: "secreto", destino: CARTA, account_id: 7, saldo_pendiente: true }),
    );
    const sesion = await (await POST(req({ checkout_id: CHECKOUT }))).json();
    expect(sesion).toEqual({ estado: "sesion", destino: CARTA, account_id: 7, saldo_pendiente: true });

    store.set(COOKIE, { value: "el-nonce" });
    fetchMock.mockResolvedValueOnce(
      json({ estado: "codigo", email: "g***@example.com", destino: CARTA, saldo_pendiente: true }),
    );
    const codigo = await (await POST(req({ checkout_id: CHECKOUT }))).json();
    expect(codigo).toEqual({
      estado: "codigo", email: "g***@example.com", destino: CARTA, saldo_pendiente: true,
    });
  });

  it("pendiente: pendiente, y la cookie sigue para el próximo intento", async () => {
    fetchMock.mockResolvedValue(json({ estado: "pendiente" }));

    const res = await POST(req({ checkout_id: CHECKOUT }));

    expect(await res.json()).toEqual({ estado: "pendiente" });
    expect(store.has(COOKIE)).toBe(true);
  });

  it("404 del backend: invalido, y la cookie del nonce se borra", async () => {
    fetchMock.mockResolvedValue(json({ error: "no encontrado" }, 404));

    const res = await POST(req({ checkout_id: CHECKOUT }));

    expect(await res.json()).toEqual({ estado: "invalido" });
    expect(store.has(COOKIE)).toBe(false);
    expect(store.has(SESSION_COOKIE)).toBe(false);
  });

  it("sin cookie del checkout: invalido sin llamar al backend", async () => {
    store.delete(COOKIE);

    const res = await POST(req({ checkout_id: CHECKOUT }));

    expect(await res.json()).toEqual({ estado: "invalido" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("un checkout_id con forma rara: invalido sin llamar al backend", async () => {
    const res = await POST(req({ checkout_id: "x;y" }));

    expect(await res.json()).toEqual({ estado: "invalido" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("429 llega como 429; otra falla, 502; ninguna toca las cookies", async () => {
    fetchMock.mockResolvedValueOnce(json({}, 429)).mockResolvedValueOnce(json({}, 500));

    expect((await POST(req({ checkout_id: CHECKOUT }))).status).toBe(429);
    expect((await POST(req({ checkout_id: CHECKOUT }))).status).toBe(502);
    expect(store.has(COOKIE)).toBe(true);
  });

  it("una respuesta del backend sin token no abre nada", async () => {
    fetchMock.mockResolvedValue(json({ estado: "sesion", destino: CARTA }));

    const res = await POST(req({ checkout_id: CHECKOUT }));

    expect(res.status).toBe(502);
    expect(store.has(SESSION_COOKIE)).toBe(false);
  });
});
