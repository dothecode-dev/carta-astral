import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, callApi } from "@/lib/session";
import { API_URL } from "@/lib/config";

// El token vive en una cookie httpOnly y sólo lo lee el servidor. Acá se
// reemplaza el almacén de cookies de Next por uno de mentira.
let token: string | null = null;
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      name === "astra_session" && token ? { value: token } : undefined,
  }),
}));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

beforeEach(() => {
  token = "un-token";
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

