import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// El endpoint que el CMS llama al publicar una nota. Es público —lo llama otro
// servicio, no el navegador— así que lo único que lo protege es el secreto, y
// eso es lo que más se prueba acá.

const revalidatePath = vi.fn();
vi.mock("next/cache", () => ({ revalidatePath: (r: string) => revalidatePath(r) }));

const SECRETO = "un-secreto-de-prueba";

function pedido(cuerpo: unknown): Request {
  return new Request("http://localhost/api/revalidate", {
    method: "POST",
    body: typeof cuerpo === "string" ? cuerpo : JSON.stringify(cuerpo),
  });
}

async function cargar() {
  vi.resetModules();
  return await import("@/app/api/revalidate/route");
}

beforeEach(() => {
  revalidatePath.mockClear();
  vi.stubEnv("REVALIDATE_SECRET", SECRETO);
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("con el secreto correcto", () => {
  it("revalida la nota, el listado y el sitemap", async () => {
    const { POST } = await cargar();

    const res = await POST(pedido({ secret: SECRETO, slug: "carta-natal-sin-hora", locale: "es" }));

    expect(res.status).toBe(200);
    expect(revalidatePath.mock.calls.flat()).toEqual([
      "/es/notas",
      "/es/notas/carta-natal-sin-hora",
      "/sitemap.xml",
    ]);
  });

  it("usa la sección del idioma, que no es la misma palabra", async () => {
    // `/en/notas` no existe: en inglés la sección es `notes`.
    const { POST } = await cargar();

    await POST(pedido({ secret: SECRETO, slug: "birth-chart-without-time", locale: "en" }));

    expect(revalidatePath.mock.calls.flat()).toContain("/en/notes/birth-chart-without-time");
  });
});

describe("sin el secreto correcto", () => {
  it("rechaza un secreto equivocado y no revalida nada", async () => {
    const { POST } = await cargar();

    const res = await POST(pedido({ secret: "otro", slug: "x", locale: "es" }));

    expect(res.status).toBe(401);
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("rechaza cuando no hay secreto configurado, en vez de aceptar a cualquiera", async () => {
    // El caso peligroso: un despliegue sin la variable. Fail-closed.
    vi.stubEnv("REVALIDATE_SECRET", "");
    const { POST } = await cargar();

    const res = await POST(pedido({ secret: "", slug: "x", locale: "es" }));

    expect(res.status).toBe(401);
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("no distingue en la respuesta un secreto corto de uno largo", async () => {
    const { POST } = await cargar();

    const corto = await POST(pedido({ secret: "a", slug: "x", locale: "es" }));
    const largo = await POST(pedido({ secret: "a".repeat(200), slug: "x", locale: "es" }));

    expect(corto.status).toBe(largo.status);
    expect(await corto.json()).toEqual(await largo.json());
  });
});

describe("datos incompletos", () => {
  it("rechaza un idioma que no existe", async () => {
    const { POST } = await cargar();

    const res = await POST(pedido({ secret: SECRETO, slug: "x", locale: "fr" }));

    expect(res.status).toBe(400);
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("rechaza un cuerpo que no es JSON", async () => {
    const { POST } = await cargar();

    expect((await POST(pedido("no soy json"))).status).toBe(400);
  });
});

describe("GET", () => {
  it("dice si el endpoint está configurado, sin revelar el secreto", async () => {
    const { GET } = await cargar();

    const datos = await (await GET()).json();

    expect(datos).toEqual({ ok: true, configurado: true, idiomas: ["es", "en", "pt"] });
    expect(JSON.stringify(datos)).not.toContain(SECRETO);
  });
});
