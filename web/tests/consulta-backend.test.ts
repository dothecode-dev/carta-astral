import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET as lecturaGet } from "@/app/api/charts/[id]/interpretation/route";
import { GET as estadoGet } from "@/app/api/charts/[id]/interpretation/estado/route";
import { GET as seccionesGet } from "@/app/api/charts/[id]/interpretation/secciones/route";
import { GET as indiceGet } from "@/app/api/charts/[id]/informe/indice/route";
import { GET as compraGet } from "@/app/api/compra/route";
import { conQuery, tierValido } from "@/lib/consultaBackend";
import { fetchCupon } from "@/lib/cupon";
import { SESSION_COOKIE } from "@/lib/session";

// Lo que viene del cliente (query de la ruta) y termina en la URL del backend
// se valida contra la lista cerrada que acepta el backend, y la query se arma
// con `URLSearchParams`. Concatenado, `lang=es%26tier%3Dcorto` llega
// decodificado como `es&tier=corto` y mete un parámetro que el cliente no
// debería poder elegir. Idiomas: `_INTERPRETATION_LANGS` = es/en/pt; tiers:
// `_TIERS` = corto/largo (`backend/api/views.py`).

let store: Map<string, { value: string }>;

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (name: string) => store.get(name) }),
  headers: async () => new Headers(),
}));

const ID = "89151d40-e263-4d34-81e0-2fb434f70243";
const ctx = { params: Promise.resolve({ id: ID }) };
let fetchMock: ReturnType<typeof vi.fn>;

const ok = () =>
  new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

/** La query de la URL con que se llamó al backend, como objeto. */
const queryLlamada = () => {
  const url = new URL(String(fetchMock.mock.calls[0][0]));
  return Object.fromEntries(url.searchParams.entries());
};

beforeEach(() => {
  store = new Map([[SESSION_COOKIE, { value: "tok" }]]);
  fetchMock = vi.fn().mockImplementation(async () => ok());
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("helpers", () => {
  it("tierValido acepta sólo corto y largo", () => {
    expect(tierValido("corto")).toBe(true);
    expect(tierValido("largo")).toBe(true);
    for (const malo of [null, "", "medio", "corto&lang=en", "LARGO"]) expect(tierValido(malo)).toBe(false);
  });

  it("conQuery codifica los valores y no deja meter parámetros", () => {
    const url = conQuery("/api/x/", { lang: "es&tier=corto" });
    expect(url.startsWith("/api/x/?")).toBe(true);
    expect(Object.fromEntries(new URL(url, "http://h").searchParams)).toEqual({ lang: "es&tier=corto" });
  });
});

type Handler = (req: Request, c: typeof ctx) => Promise<Response>;
const CON_TIER: [string, Handler][] = [
  ["GET /interpretation", lecturaGet],
  ["GET /interpretation/estado", estadoGet],
  ["GET /interpretation/secciones", seccionesGet],
];

describe.each(CON_TIER)("%s", (_n, handler) => {
  const pedir = (qs: string) => handler(new Request(`http://x/?${qs}`), ctx);

  it.each([
    "lang=de&tier=largo",
    "lang=es%26tier%3Dcorto&tier=largo",
    "lang=es&tier=medio",
    "lang=es&tier=largo%26lang%3Den",
    "lang=es",
  ])("%s: 400 sin llamar al backend", async (qs) => {
    const res = await pedir(qs);
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("válido: manda exactamente lang y tier", async () => {
    const res = await pedir("lang=pt&tier=corto");
    expect(res.status).toBe(200);
    expect(queryLlamada()).toEqual({ lang: "pt", tier: "corto" });
  });

  it("sin lang usa es, como antes", async () => {
    await pedir("tier=largo");
    expect(queryLlamada()).toEqual({ lang: "es", tier: "largo" });
  });
});

describe("GET /informe/indice", () => {
  it.each(["lang=de", "lang=es%26tier%3Dcorto"])("%s: 400 sin llamar al backend", async (qs) => {
    const res = await indiceGet(new Request(`http://x/?${qs}`), ctx);
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("válido: manda sólo lang", async () => {
    await indiceGet(new Request("http://x/?lang=en"), ctx);
    expect(queryLlamada()).toEqual({ lang: "en" });
  });
});

describe("GET /api/compra", () => {
  const pedir = (id: string) =>
    compraGet(new Request(`http://x/api/compra?checkout_id=${encodeURIComponent(id)}`));

  it.each(["../charts/x", "cs_test/../../account", "abc", "cupon_xyz", "cs_test_a%2F"])(
    "checkout_id %j: 400 sin llamar al backend",
    async (id) => {
      const res = await pedir(id);
      expect(res.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it.each(["cs_test_a1Sh1ZbUWea0ALlpcnM7qsHid0vYGjWtPNhtxZOwIt1", `cupon_${"a1".repeat(16)}`])(
    "checkout_id %j sigue llegando al backend",
    async (id) => {
      const res = await pedir(id);
      expect(res.status).toBe(200);
      expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe(`/api/checkout/${id}/`);
    },
  );
});

describe("fetchCupon", () => {
  it("un código sin forma de cupón no sale de la web", async () => {
    expect(await fetchCupon("../../account")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("producto va codificado en la query", async () => {
    await fetchCupon("PROMO30", "informe_natal&x=1");
    expect(queryLlamada()).toEqual({ producto: "informe_natal&x=1" });
  });
});

describe("ninguna URL del backend concatena valores en la query", () => {
  // Una ruta o función nueva que vuelva a concatenar no queda cubierta por
  // las tablas de arriba: este recorrido la encuentra.
  const archivos: string[] = [];
  const recorrer = (dir: string) => {
    for (const nombre of readdirSync(dir)) {
      const ruta = join(dir, nombre);
      if (statSync(ruta).isDirectory()) recorrer(ruta);
      else if (/\.tsx?$/.test(nombre)) archivos.push(ruta);
    }
  };
  recorrer("app");
  recorrer("lib");
  const LLAMADAS = /(?:callApi|callApiRaw|askCms)(?:<[^>]*>)?\(\s*`([^`]*)`|fetch\(\s*`\$\{API_URL\}([^`]*)`/g;

  it.each(archivos)("%s", (archivo) => {
    const fuente = readFileSync(archivo, "utf8");
    for (const m of fuente.matchAll(LLAMADAS)) {
      expect(m[1] ?? m[2], `${archivo}: ${m[0]}`).not.toMatch(/=\$\{/);
    }
  });
});
