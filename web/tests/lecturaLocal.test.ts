import { afterEach, describe, expect, it, vi } from "vitest";
import { borrarPedido, guardarPedido, guardarLectura, leerLectura, leerPedido } from "@/lib/lecturaLocal";

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
    ["pedido que no es un uuid", { ...L, pedido: 7 }],
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

// §11 v3: el pedido en curso, para retomar la espera si se recarga la página.
describe("pedido en curso", () => {
  const P1 = "00000000-0000-4000-8000-000000000001";
  const P2 = "00000000-0000-4000-8000-000000000002";
  const PEND = { pedido: P1, carta: { data: {}, firma: {} } as never, datos: DATOS };
  afterEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

  it("se guarda con vencimiento a los 15 min y se lee antes", () => {
    guardarPedido(PEND, 1000);
    expect(leerPedido(1000 + 14 * 60 * 1000)).toEqual({ ...PEND, vence: 1000 + 15 * 60 * 1000 });
  });

  it("vencido se borra y devuelve null", () => {
    guardarPedido(PEND, 1000);
    expect(leerPedido(1000 + 16 * 60 * 1000)).toBeNull();
    expect(localStorage.getItem("astra-lectura-pedido")).toBeNull();
  });

  it("borrar sólo borra si es el mismo pedido", () => {
    guardarPedido(PEND, 1000);
    borrarPedido(P2);
    expect(leerPedido(1000)?.pedido).toBe(P1);
    borrarPedido(P1);
    expect(leerPedido(1000)).toBeNull();
  });

  it("no rompe sin storage", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("bloqueado"); });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("bloqueado"); });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("bloqueado"); });
    expect(() => guardarPedido(PEND)).not.toThrow();
    expect(leerPedido()).toBeNull();
    expect(() => borrarPedido(P1)).not.toThrow();
  });

  it.each([
    ["pedido que no es un uuid", { ...PEND, pedido: "../x" }],
    ["sin carta", { ...PEND, carta: undefined }],
    ["sin datos", { ...PEND, datos: undefined }],
    ["vence que no es número", { ...PEND, vence: "mañana" }],
    ["idioma inválido", { ...PEND, lang: "fr" }],
  ])("una entrada corrupta (%s) devuelve null y se borra", (_n, malo) => {
    localStorage.setItem("astra-lectura-pedido", JSON.stringify({ vence: Date.now() + 1000, ...malo }));
    expect(leerPedido()).toBeNull();
    expect(localStorage.getItem("astra-lectura-pedido")).toBeNull();
  });

  it("basura en la clave devuelve null", () => {
    localStorage.setItem("astra-lectura-pedido", "{no es json");
    expect(leerPedido()).toBeNull();
  });
});
