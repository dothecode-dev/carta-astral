import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchCatalogo, formatearPrecio, unidades } from "@/lib/catalogo";

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
