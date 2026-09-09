import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, callApi, callApiRaw } from "@/lib/session";
import { API_URL } from "@/lib/config";

// El token vive en una cookie httpOnly y sólo lo lee el servidor. Acá se
// reemplaza el almacén de cookies de Next por uno de mentira.
let token: string | null = null;
// La IP del visitante (C1, generalizado): `callApi`/`callApiRaw` la sacan del
// contexto de pedido que arma `next/headers`, no de nada que pase el caller.
let ipVisitante: string | null = null;
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      name === "astra_session" && token ? { value: token } : undefined,
  }),
  headers: async () => new Headers(ipVisitante ? { "x-forwarded-for": ipVisitante } : {}),
}));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

beforeEach(() => {
  token = "un-token";
  ipVisitante = null;
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("callApi", () => {
  it("manda el token de la sesión y devuelve el cuerpo", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ deuda: 3 }));
    vi.stubGlobal("fetch", fetchMock);

    const data = await callApi<{ deuda: number }>("/api/account/");

    expect(data.deuda).toBe(3);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_URL}/api/account/`);
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer un-token");
  });

  it("no llama al backend si no hay sesión", async () => {
    token = null;
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(callApi("/api/account/")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("acepta un borrado sin cuerpo", async () => {
    // El backend responde 204 a los borrados: parsear eso haría fallar una
    // operación que salió bien, y la web mostraba un 502 sobre un éxito.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

    await expect(callApi("/api/charts/")).resolves.toBeNull();
  });

  it("guarda el motivo que da el backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ error: "generación en curso" }, 409)),
    );

    const error: unknown = await callApi("/api/charts/x/interpretation/").catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    const api = error as ApiError;
    expect(api.status).toBe(409);
    expect(api.body).toContain("generación en curso");
  });

  it("no manda el token cuando la llamada es pública", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await callApi("/api/sky/", { auth: false });

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  // C1 arregló el reenvío sólo en las dos rutas de login, copiado a mano en
  // cada una. Generalizado acá: como TODA llamada al backend pasa por
  // `callApi`, cualquier ruta nueva —exista hoy o se agregue mañana— lo hereda
  // sin que nadie tenga que acordarse de repetir el patrón.
  it("reenvía la IP del visitante a cualquier ruta, autenticada o no", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    ipVisitante = "203.0.113.7";

    await callApi("/api/geocode/", { auth: false });

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["x-forwarded-for"]).toBe("203.0.113.7");
  });

  it("no manda x-forwarded-for inventado cuando el proxy no lo mandó", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await callApi("/api/account/");

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["x-forwarded-for"]).toBeUndefined();
  });
});

describe("callApiRaw", () => {
  it("también reenvía la IP del visitante (mismo mecanismo que callApi)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Uint8Array([1, 2, 3]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    ipVisitante = "198.51.100.9";

    await callApiRaw("/api/charts/1/pdf/", { method: "POST" });

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["x-forwarded-for"]).toBe("198.51.100.9");
  });
});

describe("haySesion", () => {
  // Lo usan las páginas públicas —home, notas, ejemplo, legales— para pintar el
  // header. Antes no lo consultaban: eran estáticas y el header siempre decía
  // "Entrar", así que alguien con la sesión abierta que entraba a los Términos
  // desde su carta veía un sitio que no lo reconocía.
  //
  // No valida contra el backend a propósito (para eso está `sessionIsLive`):
  // pintar un enlace no justifica una llamada de red en cada página pública, y
  // el peor caso de una cookie vencida es un clic que termina en el login, que
  // es exactamente lo que pasaría igual.
  it("dice que sí cuando hay cookie", async () => {
    const { haySesion } = await import("@/lib/session");
    expect(await haySesion()).toBe(true);
  });

  it("dice que no cuando no hay cookie", async () => {
    token = null;
    const { haySesion } = await import("@/lib/session");
    expect(await haySesion()).toBe(false);
  });

  it("no le pregunta al backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { haySesion } = await import("@/lib/session");

    await haySesion();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

