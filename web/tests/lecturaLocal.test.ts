import { afterEach, describe, expect, it, vi } from "vitest";
import { guardarLectura, leerLectura } from "@/lib/lecturaLocal";

const DATOS = {
  name: "Ana", date: "1976-05-31", time: "10:00", time_known: true,
  lat: -32.9, lng: -60.6, place_label: "Rosario, AR",
};
const L = { carta: { data: {}, firma: {} } as never, datos: DATOS, texto: "t", lang: "es" as const, disclaimer: "d" };

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

  it("devuelve los datos de la carta guardados junto con la lectura", () => {
    guardarLectura(L, 1000);
    expect(leerLectura(1000)?.datos).toEqual(DATOS);
  });

  it.each([
    ["sin datos", { ...L, datos: undefined }],
    ["datos que no son un objeto", { ...L, datos: "x" }],
    ["sin carta", { ...L, carta: undefined }],
    ["idioma inválido", { ...L, lang: "fr" }],
    ["disclaimer que no es texto", { ...L, disclaimer: 3 }],
  ])("una entrada corrupta (%s) devuelve null y se borra", (_n, malo) => {
    localStorage.setItem("astra-lectura-anonima", JSON.stringify({ ...malo, vence: Date.now() + 1000 }));
    expect(leerLectura()).toBeNull();
    expect(localStorage.getItem("astra-lectura-anonima")).toBeNull();
  });

  it("basura en la clave devuelve null", () => {
    localStorage.setItem("astra-lectura-anonima", "{no es json");
    expect(leerLectura()).toBeNull();
  });
});
