import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchCupon, normalizarCupon } from "@/lib/cupon";

// `fetchCupon` pasa por `callApi` (lib/session.ts), que saca la IP del
// visitante del contexto de pedido que arma `next/headers`. Sin este mock,
// `headers()` no tiene nada que leer fuera de un render real de Next.
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => undefined }),
  headers: async () => new Headers(),
}));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("normalizarCupon", () => {
  it("acepta lo que Stripe acepta, en mayúsculas y sin espacios alrededor", () => {
    expect(normalizarCupon(" promo30 ")).toBe("PROMO30");
    expect(normalizarCupon("A1H1-Q1MG")).toBe("A1H1-Q1MG");
  });

  it("rechaza lo demás en vez de mandarlo al backend", () => {
    // Viene de la URL: cualquiera escribe lo que quiera ahí.
    for (const raro of ["promo 30", "ab", "x".repeat(41), "ñandu", "", undefined, ["a"], 12]) {
      expect(normalizarCupon(raro)).toBeNull();
    }
  });
});

describe("fetchCupon", () => {
  it("pide sin caché: los usos que quedan cambian con cada compra", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ valido: true, codigo: "PROMO30", porcentaje: 30, productos: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const r = await fetchCupon("PROMO30");

    expect(r).toEqual({ valido: true, codigo: "PROMO30", porcentaje: 30, productos: [] });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/cupones\/PROMO30\/$/);
    expect(init.cache).toBe("no-store");
  });

  it("un cupón que no sirve vuelve con su motivo", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ valido: false, motivo: "agotado" })));
    expect(await fetchCupon("PROMO30")).toEqual({ valido: false, motivo: "agotado" });
  });

  it("si el backend no responde devuelve null: precio de lista, nunca un descuento inventado", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("caído")));
    expect(await fetchCupon("PROMO30")).toBeNull();

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({}, 500)));
    expect(await fetchCupon("PROMO30")).toBeNull();
  });
});
