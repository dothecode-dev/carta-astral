import { afterEach, describe, expect, it, vi } from "vitest";
import { guardarLectura, leerLectura } from "@/lib/lecturaLocal";

const L = { carta: { firma: {} } as never, texto: "t", lang: "es" as const, disclaimer: "d" };

describe("lecturaLocal", () => {
  afterEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

  it("guarda y devuelve dentro de las 24 h", () => {
    guardarLectura(L, 1000);
    expect(leerLectura(1000 + 23 * 3600 * 1000)?.texto).toBe("t");
  });

  it("vencida se borra y devuelve null", () => {
    guardarLectura(L, 1000);
    expect(leerLectura(1000 + 25 * 3600 * 1000)).toBeNull();
    expect(localStorage.getItem("astra-lectura-anonima")).toBeNull();
  });

  it("lecturaLocal no rompe sin storage", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("bloqueado"); });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("bloqueado"); });
    expect(() => guardarLectura(L)).not.toThrow();
    expect(leerLectura()).toBeNull();
  });

  it("basura en la clave devuelve null", () => {
    localStorage.setItem("astra-lectura-anonima", "{no es json");
    expect(leerLectura()).toBeNull();
  });
});
