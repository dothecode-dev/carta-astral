import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DELETE as accountDelete } from "@/app/api/account/route";
import { DELETE as chartsDelete, POST as chartsPost } from "@/app/api/charts/route";
import { GET as readingGet, POST as readingPost } from "@/app/api/charts/[id]/interpretation/route";
import { GET as estadoGet } from "@/app/api/charts/[id]/interpretation/estado/route";
import { POST as geocodePost } from "@/app/api/geocode/route";
import { DELETE as sessionDelete, POST as sessionPost } from "@/app/api/session/route";
import { SESSION_COOKIE } from "@/lib/session";

// Las rutas de /api son el único intermediario entre el navegador y el backend:
// el token vive en una cookie httpOnly y no tiene que volver nunca en el cuerpo
// de una respuesta. Se prueban contra el almacén de cookies y el fetch reales
// del servidor, reemplazados acá por los de mentira.

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
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const post = (url: string, body: unknown) =>
  new Request(url, { method: "POST", body: JSON.stringify(body) });

const CHART = "89151d40-e263-4d34-81e0-2fb434f70243";
const params = { params: Promise.resolve({ id: CHART }) };

beforeEach(() => {
  store = new Map([[SESSION_COOKIE, { value: "un-token" }]]);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("POST /api/session", () => {
  it("guarda el token en una cookie httpOnly y no lo devuelve", async () => {
    store.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ token: "secreto", credits_available: 1, account_id: 7 })),
    );

    const res = await sessionPost(
      post("http://x/api/session", { provider: "google", id_token: "id" }),
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    // El id de cuenta sí sale: la analítica lo usa para unir el embudo de una
    // persona sin conocer su email. El token no sale nunca.
    expect(body).toEqual({ credits_available: 1, account_id: 7 });
    expect(JSON.stringify(body)).not.toContain("secreto");
    expect(store.get(SESSION_COOKIE)?.value).toBe("secreto");
    expect(store.get(SESSION_COOKIE)?.options?.httpOnly).toBe(true);
  });

  it("rechaza un proveedor que no existe sin llamar al backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const res = await sessionPost(
      post("http://x/api/session", { provider: "facebook", id_token: "id" }),
    );

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("traduce el rechazo del backend sin filtrar el detalle", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "firma inválida" }, 401)));

    const res = await sessionPost(
      post("http://x/api/session", { provider: "google", id_token: "id" }),
    );

    expect(res.status).toBe(401);
    expect(JSON.stringify(await res.json())).not.toContain("firma inválida");
  });
});

describe("DELETE /api/session", () => {
  it("borra la cookie aunque el backend no responda", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("caído")));

    const res = await sessionDelete();

    expect(res.status).toBe(200);
    expect(store.has(SESSION_COOKIE)).toBe(false);
  });
});

describe("DELETE /api/account", () => {
  it("borra la cookie después de borrar la cuenta", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

    const res = await accountDelete();

    expect(res.status).toBe(200);
    expect(store.has(SESSION_COOKIE)).toBe(false);
  });

  it("da por cumplido el borrado si la sesión ya no valía", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "inválido" }, 401)));

    const res = await accountDelete();

    expect(res.status).toBe(200);
    expect(store.has(SESSION_COOKIE)).toBe(false);
  });

  it("no borra la cookie si el backend falló de verdad", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "boom" }, 500)));

    const res = await accountDelete();

    expect(res.status).toBe(502);
    expect(store.has(SESSION_COOKIE)).toBe(true);
  });
});

describe("/api/charts", () => {
  it("crea la carta con el token de la cookie, no con lo que mande el navegador", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ id: CHART }, 201));
    vi.stubGlobal("fetch", fetchMock);

    const res = await chartsPost(
      post("http://x/api/charts", { name: "Ceci", account_id: 999 }),
    );

    expect(res.status).toBe(201);
    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer un-token");
  });

  it("distingue datos inválidos de una caída del backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "fecha" }, 400)));
    const invalidos = await chartsPost(post("http://x/api/charts", { date: "0000-13-45" }));
    expect(invalidos.status).toBe(400);

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({}, 500)));
    const caido = await chartsPost(post("http://x/api/charts", {}));
    expect(caido.status).toBe(502);
  });

  it("responde 401 al borrar sin sesión, sin tocar el backend", async () => {
    store.clear();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const res = await chartsDelete();

    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("/api/charts/[id]/interpretation", () => {
  it("deja pasar el 409 para que la web espere", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "en curso" }, 409)));

    const res = await readingPost(post("http://x", { lang: "es" }), params);

    expect(res.status).toBe(409);
  });

  it("distingue quedarse sin créditos de un fallo", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({}, 402)));
    expect((await readingPost(post("http://x", { lang: "es" }), params)).status).toBe(402);

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({}, 503)));
    expect((await readingPost(post("http://x", { lang: "es" }), params)).status).toBe(503);
  });

  it("manda el tier al backend, no sólo el idioma", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({}, 202));
    vi.stubGlobal("fetch", fetchMock);

    await readingPost(post("http://x", { lang: "es", tier: "corto" }), params);

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse((init as RequestInit).body as string)).toMatchObject({
      lang: "es",
      tier: "corto",
    });
  });

  // El 402 trae `code: "sin_free" | "sin_paid"` para que el botón sepa cuál
  // de los dos mensajes mostrar. Sin reenviarlo, la web no puede distinguirlos.
  it("reenvía el code del 402 para distinguir sin_free de sin_paid", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ code: "sin_free" }, 402)));

    const res = await readingPost(post("http://x", { lang: "es", tier: "corto" }), params);

    expect(res.status).toBe(402);
    expect((await res.json()).code).toBe("sin_free");
  });

  it("consulta la lectura sin generarla", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ text: "tu carta dice..." }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await readingGet(new Request(`http://x?lang=pt&tier=largo`), params);

    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("lang=pt");
    expect(init.method).toBeUndefined();
  });

  // Sin esto, un caller que se cablee después (el docstring de esta ruta ya
  // avisa que está pensada para consumirse desde el cliente) reintroduciría
  // el 400 silencioso que tapa la lectura: el backend exige `tier` desde la
  // Task 7 y, sin reenviarlo, este proxy nunca se lo manda.
  it("manda el tier al backend, no sólo el idioma", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ text: "tu carta dice..." }));
    vi.stubGlobal("fetch", fetchMock);

    await readingGet(new Request(`http://x?lang=es&tier=corto`), params);

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("tier=corto");
  });

  it("responde 404 mientras la lectura no existe", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 404 })));

    const res = await readingGet(new Request("http://x?lang=es"), params);

    expect(res.status).toBe(404);
  });
});

describe("/api/charts/[id]/interpretation/estado", () => {
  it("pega con la barra final que pide la ruta del backend", async () => {
    // El backend sumó la barra final a esta ruta (era la única sin ella): un
    // pedido sin barra sigue funcionando gracias al redirect de APPEND_SLASH,
    // pero no hay que depender de eso a propósito.
    const fetchMock = vi.fn().mockResolvedValue(json({ completa: false, hechas: 1, total: 8 }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await estadoGet(new Request("http://x?lang=en&tier=largo"), params);

    expect(res.status).toBe(200);
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/interpretation/estado/?lang=en");
  });

  it("manda el tier al backend, no sólo el idioma", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ completa: false, hechas: 0, total: 1 }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await estadoGet(new Request("http://x?lang=es&tier=corto"), params);

    expect(res.status).toBe(200);
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("tier=corto");
  });
});

describe("POST /api/geocode", () => {
  it("no consulta el padrón mientras la búsqueda es corta", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const res = await geocodePost(post("http://x/api/geocode", { q: "ro" }));

    expect(await res.json()).toEqual({ results: [] });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("devuelve los lugares que encontró el backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ results: [{ name: "Rosario", tz_name: "America/Argentina/Cordoba" }] })),
    );

    const res = await geocodePost(post("http://x/api/geocode", { q: "rosario" }));
    const body = await res.json();

    expect(body.results).toHaveLength(1);
    expect(body.results[0].tz_name).toBe("America/Argentina/Cordoba");
  });
});
