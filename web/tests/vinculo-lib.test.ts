import { afterEach, describe, expect, it, vi } from "vitest";

import { SYNASTRY_SLUG } from "@/lib/i18n";
import { localeDelVinculo, vinculoActivo } from "@/lib/vinculo";

afterEach(() => vi.unstubAllGlobals());

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("vinculoActivo", () => {
  it("es true si el backend responde 200", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ preview: true })));
    await expect(vinculoActivo()).resolves.toBe(true);
  });

  it("pregunta a /api/vinculo/ del backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ preview: true }));
    vi.stubGlobal("fetch", fetchMock);
    await vinculoActivo();
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/vinculo\/$/);
  });

  it("es false si el backend responde 404 (flag apagado)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({}, 404)));
    await expect(vinculoActivo()).resolves.toBe(false);
  });

  it("es false si el backend responde 500", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({}, 500)));
    await expect(vinculoActivo()).resolves.toBe(false);
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
