import { afterEach, describe, expect, it, vi } from "vitest";

import { conPrecio, fetchCatalogo, formatearPrecio, precioDe, unidades } from "@/lib/catalogo";

afterEach(() => {
  vi.restoreAllMocks();
});

const PACK = {
  codigo: "pack_5_natal",
  precio_centavos: 12500,
  moneda: "usd",
  otorga: [{ codigo: "informe_natal", cantidad: 5 }],
};

describe("catálogo", () => {
  it("dice cuántos informes deja un pack", () => {
    expect(unidades(PACK)).toBe(5);
  });

  it("muestra el precio sin centavos cuando es redondo", () => {
    // "US$ 125" y no "US$ 125,00": el ruido decimal en un precio entero sólo
    // hace más difícil comparar de un vistazo.
    expect(formatearPrecio(12500, "usd", "es-AR")).not.toMatch(/,00/);
    expect(formatearPrecio(12500, "usd", "es-AR")).toMatch(/125/);
  });

  it("si el backend no responde devuelve null en vez de romper la página", async () => {
    // Precios en blanco con un aviso es mejor que precios inventados: la
    // página anuncia lo que Stripe cobra, no lo que la web recuerda.
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("timeout")));

    expect(await fetchCatalogo()).toBeNull();
  });

  it("si el backend responde con error tampoco inventa precios", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    expect(await fetchCatalogo()).toBeNull();
  });

  it("devuelve los productos tal como los manda el backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ productos: [PACK] }),
    }));

    expect(await fetchCatalogo()).toEqual([PACK]);
  });
});

describe("el precio en los textos", () => {
  const INFORME = {
    codigo: "informe_natal",
    precio_centavos: 500,
    moneda: "usd",
    otorga: [{ codigo: "informe_natal", cantidad: 1 }],
  };

  it("lo saca del catálogo, no de un número escrito en el texto", () => {
    // Antes el precio vivía en nueve textos a mano: al cambiarlo, la web
    // anunciaba uno y Stripe cobraba otro hasta que alguien se acordara.
    expect(precioDe([INFORME], "informe_natal", "es-AR")).toMatch(/5/);
    expect(precioDe([INFORME], "informe_natal", "es-AR")).not.toMatch(/29/);
  });

  it("sin catálogo, o sin ese producto, no inventa un precio", () => {
    expect(precioDe(null, "informe_natal", "es-AR")).toBeNull();
    expect(precioDe([INFORME], "pack_5_natal", "es-AR")).toBeNull();
  });

  it("completa el marcador del texto", () => {
    expect(conPrecio("{precio} · ocho secciones", "US$ 5")).toBe("US$ 5 · ocho secciones");
  });

  it("sin precio, el texto se lee igual y no muestra el marcador", () => {
    expect(conPrecio("{precio} · ocho secciones", null)).toBe("ocho secciones");
  });
});

describe("conPrecio con el precio al final", () => {
  it("sin precio, no deja el separador colgando", () => {
    expect(conPrecio("Comprar el informe completo · {precio}", null)).toBe("Comprar el informe completo");
  });
});
