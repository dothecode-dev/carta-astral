import { afterEach, describe, expect, it, vi } from "vitest";

import { SYNASTRY_SLUG } from "@/lib/i18n";
import { localeDelVinculo, vinculoActivo } from "@/lib/vinculo";

afterEach(() => vi.unstubAllGlobals());

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("vinculoActivo", () => {
  it("es true si el backend dice preview: true", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ preview: true })));
    await expect(vinculoActivo()).resolves.toBe(true);
  });

  it("es false si el backend responde 200 con preview: false", async () => {
    // El flag apagado es un 200 con el valor, no un 404: el caché de datos de
    // Next sólo guarda las 200, y con un 404 el «encendido» viejo no se iba.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ preview: false })));
    await expect(vinculoActivo()).resolves.toBe(false);
  });

  it("un 200 sin preview o con otro valor no cuenta como encendido", async () => {
    for (const cuerpo of [{}, { preview: "true" }, { preview: 1 }, null, []]) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(cuerpo)));
      await expect(vinculoActivo(), JSON.stringify(cuerpo)).resolves.toBe(false);
    }
  });

  it("un 200 que no es JSON es false y no tira", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>", { status: 200 })));
    await expect(vinculoActivo()).resolves.toBe(false);
  });

  it("pregunta a /api/vinculo/ del backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ preview: true }));
    vi.stubGlobal("fetch", fetchMock);
    await vinculoActivo();
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/vinculo\/$/);
  });

  it("es false si el backend responde 404 o 500", async () => {
    for (const status of [404, 500, 503]) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ preview: true }, status)));
      await expect(vinculoActivo(), String(status)).resolves.toBe(false);
    }
  });

  it("es false si el backend no contesta: la landing no puede tirar el sitio", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    await expect(vinculoActivo()).resolves.toBe(false);
  });

  it("no cuelga el render: el pedido lleva un tope de tiempo", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ preview: true }));
    vi.stubGlobal("fetch", fetchMock);
    await vinculoActivo();
    expect(fetchMock.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
  });

  it("se cachea por revalidación y no por visitante", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ preview: true }));
    vi.stubGlobal("fetch", fetchMock);
    await vinculoActivo();
    expect(fetchMock.mock.calls[0][1].next).toEqual({ revalidate: 300 });
  });
});

describe("localeDelVinculo", () => {
  it("sinastria atiende es y pt", () => {
    expect(localeDelVinculo("es", "sinastria")).toBe("es");
    expect(localeDelVinculo("pt", "sinastria")).toBe("pt");
  });

  it("synastry sólo atiende en", () => {
    expect(localeDelVinculo("en", "synastry")).toBe("en");
    expect(localeDelVinculo("en", "sinastria")).toBeNull();
    expect(localeDelVinculo("es", "synastry")).toBeNull();
  });

  it("un idioma que no existe no es una página", () => {
    expect(localeDelVinculo("fr", "sinastria")).toBeNull();
  });
});

describe("SYNASTRY_SLUG", () => {
  it("pt comparte slug con es y en tiene el suyo", () => {
    expect(SYNASTRY_SLUG).toEqual({ es: "sinastria", en: "synastry", pt: "sinastria" });
  });
});
