import { describe, expect, it } from "vitest";

import { POST } from "@/app/api/moneda/route";

// RF24: el selector de /precios. Lista blanca, cookie de un año y vuelta a la
// página de origen sólo si es un path del sitio (sin open redirect).

const pedir = (campos: Record<string, string>) =>
  POST(
    new Request("https://astraguia.com/api/moneda", {
      method: "POST",
      body: new URLSearchParams(campos),
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    }),
  );

describe("POST /api/moneda", () => {
  it("guarda la moneda elegida y vuelve a la página", async () => {
    const res = await pedir({ moneda: "brl", volver: "/pt/precios" });

    expect(res.status).toBe(303);
    // Relativo: detrás del proxy `request.url` es la URL interna del contenedor.
    expect(res.headers.get("location")).toBe("/pt/precios");
    const cookie = res.headers.get("set-cookie")!;
    expect(cookie).toMatch(/astra_moneda=brl/);
    expect(cookie).toMatch(/Max-Age=31536000/);
    expect(cookie.toLowerCase()).toMatch(/samesite=lax/);
  });

  it.each(["eur", "", "BRL;"])("una moneda que no conocemos (%j) es 400 y no pone cookie", async (moneda) => {
    const res = await pedir({ moneda, volver: "/pt/precios" });

    expect(res.status).toBe(400);
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  it.each(["https://evil.example/x", "//evil.example/x", "/\\evil.example", "precios", ""])(
    "un destino que no es un path del sitio (%j) vuelve a /",
    async (volver) => {
      const res = await pedir({ moneda: "usd", volver });

      expect(res.status).toBe(303);
      expect(res.headers.get("location")).toBe("/");
    },
  );

  it("conserva el cupón de la página al volver", async () => {
    const res = await pedir({ moneda: "brl", volver: "/pt/precios", cupon: "amigos30" });

    expect(res.headers.get("location")).toBe("/pt/precios?cupon=AMIGOS30");
  });

  it("un cupón sin forma de cupón no viaja", async () => {
    const res = await pedir({ moneda: "brl", volver: "/pt/precios", cupon: "../x?y=1" });

    expect(res.headers.get("location")).toBe("/pt/precios");
  });
});
