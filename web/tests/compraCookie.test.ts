import { afterEach, describe, expect, it, vi } from "vitest";

import { abreviar, nombre, opciones } from "@/lib/compraCookie";

// La cookie que prueba que este navegador es el que abrió el pago (RF2). El
// nombre lleva el `checkout_id` para que abrir un segundo pago no pise el
// nonce del primero; y como ese id llega por la URL, se valida su forma antes
// de convertirlo en nombre de cookie.

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("nombre de la cookie del nonce", () => {
  it("lleva el checkout_id", () => {
    expect(nombre("cs_test_a1B2")).toBe("astra_compra_cs_test_a1B2");
  });

  it("acepta el id de un checkout de Mercado Pago", () => {
    // Sin esto, la compra sin cuenta en pesos no abría el pago: la ruta no
    // podía nombrar la cookie del nonce y cortaba antes de redirigir.
    const id = "mp_" + "0123456789abcdef".repeat(2);
    expect(nombre(id)).toBe(`astra_compra_${id}`);
  });

  it.each([
    ["corto", "mp_abc"],
    ["con mayúsculas", "mp_" + "A".repeat(32)],
    ["largo", "mp_" + "a".repeat(33)],
  ])("rechaza un id de Mercado Pago %s", (_motivo, id) => {
    expect(nombre(id)).toBeNull();
  });

  it("dos checkouts, dos cookies distintas", () => {
    expect(nombre("cs_test_uno")).not.toBe(nombre("cs_test_dos"));
  });

  it.each([
    ["sin prefijo de Stripe", "abc"],
    ["vacío", ""],
    ["con caracteres de cookie", "cs_test;x=1"],
    ["con espacio", "cs_test x"],
    ["con barra", "cs_test/../x"],
    ["sólo el prefijo", "cs_"],
    ["demasiado largo", "cs_" + "a".repeat(201)],
  ])("rechaza un id %s", (_motivo, id) => {
    expect(nombre(id)).toBeNull();
  });

  it("rechaza lo que no es texto", () => {
    expect(nombre(undefined)).toBeNull();
    expect(nombre(["cs_test_1"])).toBeNull();
  });
});

describe("atributos", () => {
  it("httpOnly, SameSite=Lax, un día, en todo el sitio", () => {
    expect(opciones()).toMatchObject({ httpOnly: true, sameSite: "lax", maxAge: 86400, path: "/" });
  });

  it("Secure en producción", () => {
    vi.stubEnv("NODE_ENV", "production");
    expect(opciones().secure).toBe(true);
  });

  it("sin Secure en desarrollo, que va por http", () => {
    vi.stubEnv("NODE_ENV", "development");
    expect(opciones().secure).toBe(false);
  });
});

describe("número de compra abreviado", () => {
  it("son los últimos caracteres del checkout_id", () => {
    expect(abreviar("cs_live_a1Sh1ZbUWea0ALlpcnM7qsHid0vYGjWtPNhtxZOwIt1")).toBe("NhtxZOwIt1");
  });
});
