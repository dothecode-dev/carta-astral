import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PATCH as cartaPatch } from "@/app/api/charts/[id]/route";
import { GET as lecturaGet, POST as lecturaPost } from "@/app/api/charts/[id]/interpretation/route";
import { GET as estadoGet } from "@/app/api/charts/[id]/interpretation/estado/route";
import { GET as seccionesGet } from "@/app/api/charts/[id]/interpretation/secciones/route";
import { GET as indiceGet } from "@/app/api/charts/[id]/informe/indice/route";
import { POST as pdfPost } from "@/app/api/charts/[id]/pdf/route";
import { SESSION_COOKIE } from "@/lib/session";
import { uuidValido } from "@/lib/uuid";

// El `id` de estas rutas se interpola en el path del backend. Sin validarlo,
// `..%2Fcuenta` —que Next entrega decodificado como `../cuenta`— arma
// `/api/charts/../cuenta/` y le habla a otro endpoint con la sesión de quien
// pidió. El backend identifica las cartas por un uuid4 con guiones
// (`Chart.uuid`, `<uuid:uuid>` en `api/urls.py`): todo lo demás es 404 sin
// salir de la web.

let store: Map<string, { value: string }>;

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (name: string) => store.get(name) }),
  headers: async () => new Headers(),
}));

const VALIDO = "89151d40-e263-4d34-81e0-2fb434f70243";
const INVALIDOS = ["..%2Fcuenta", "../cuenta", "abc", "", `${VALIDO}/../../cuenta`, VALIDO.toUpperCase()];

const ctx = (id: string) => ({ params: Promise.resolve({ id }) });
const cuerpo = (method: string, body: unknown) =>
  new Request("http://x/?lang=es&tier=largo", { method, body: JSON.stringify(body) });
const get = () => new Request("http://x/?lang=es&tier=largo");

type Handler = (req: Request, ctx: { params: Promise<{ id: string }> }) => Promise<Response>;
const RUTAS: [string, Handler, () => Request][] = [
  ["PATCH /charts/[id]", cartaPatch, () => cuerpo("PATCH", { trato: "neutro" })],
  ["GET /interpretation", lecturaGet, get],
  ["POST /interpretation", lecturaPost, () => cuerpo("POST", { lang: "es", tier: "largo" })],
  ["GET /interpretation/estado", estadoGet, get],
  ["GET /interpretation/secciones", seccionesGet, get],
  ["GET /informe/indice", indiceGet, get],
  ["POST /pdf", pdfPost, () => cuerpo("POST", { wheel: {} })],
];

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  store = new Map([[SESSION_COOKIE, { value: "tok" }]]);
  fetchMock = vi.fn().mockImplementation(
    async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("uuidValido", () => {
  it("acepta el uuid4 en minúsculas con guiones que genera el backend", () => {
    expect(uuidValido(VALIDO)).toBe(true);
  });

  it.each(INVALIDOS)("rechaza %j", (id) => {
    expect(uuidValido(id)).toBe(false);
  });

  it("rechaza lo que no es string", () => {
    expect(uuidValido(undefined)).toBe(false);
    expect(uuidValido(123)).toBe(false);
  });
});

describe.each(RUTAS)("%s", (_nombre, handler, req) => {
  it.each(INVALIDOS)("id %j: 404 sin llamar al backend", async (id) => {
    const res = await handler(req(), ctx(id));
    expect(res.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("un uuid válido sigue llegando al backend", async () => {
    const res = await handler(req(), ctx(VALIDO));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain(`/api/charts/${VALIDO}/`);
    expect(res.status).toBe(200);
  });
});

describe("toda ruta con [id] bajo app/api valida el id", () => {
  // Una ruta nueva con `[id]` que se olvide del chequeo no queda cubierta por
  // la tabla de arriba: este recorrido la encuentra.
  const rutas: string[] = [];
  const recorrer = (dir: string, dentroDeId: boolean) => {
    for (const nombre of readdirSync(dir)) {
      const ruta = join(dir, nombre);
      if (statSync(ruta).isDirectory()) recorrer(ruta, dentroDeId || nombre === "[id]");
      else if (dentroDeId && nombre === "route.ts") rutas.push(ruta);
    }
  };
  recorrer("app/api", false);

  it("encuentra las seis rutas conocidas", () => {
    expect(rutas.length).toBeGreaterThanOrEqual(6);
  });

  it.each(rutas)("%s usa uuidValido", (ruta) => {
    expect(readFileSync(ruta, "utf8")).toMatch(/uuidValido\(id\)/);
  });
});

describe("la página de la carta valida el id antes de hablar con el backend", () => {
  // Mismo problema fuera de `app/api`: la página interpola `id` en
  // `/api/charts/${id}/` con la sesión de quien mira.
  it("app/[locale]/carta/[id]/page.tsx usa uuidValido", () => {
    const fuente = readFileSync("app/[locale]/carta/[id]/page.tsx", "utf8");
    expect(fuente).toMatch(/if \(!uuidValido\(id\)\) notFound\(\);/);
    expect(fuente.indexOf("uuidValido(id)")).toBeLessThan(fuente.indexOf("callApi<ApiChart>"));
  });
});
