import { describe, expect, it } from "vitest";

import { destinoInternoSeguro, destinoSeguro } from "@/lib/destino";

// `next` llega por la query, o sea desde afuera: cualquiera puede armar un
// enlace a /es/entrar?next=<lo que quiera>. Si esa cadena se usara tal cual en
// el redirect posterior al login, el sitio serviría de trampolín para mandar a
// alguien recién autenticado a un dominio ajeno con aspecto de ser el nuestro.
// Por eso la lista es cerrada: no se sanea lo que llega, se compara contra lo
// que puede llegar.

describe("destinoSeguro", () => {
  it("acepta las rutas internas de la lista, en el idioma que se está usando", () => {
    expect(destinoSeguro("/es/precios", "es")).toBe("/es/precios");
    expect(destinoSeguro("/es/nueva", "es")).toBe("/es/nueva");
    expect(destinoSeguro("/es/cuenta", "es")).toBe("/es/cuenta");
    expect(destinoSeguro("/en/precios", "en")).toBe("/en/precios");
    expect(destinoSeguro("/pt/nueva", "pt")).toBe("/pt/nueva");
  });

  it("acepta una carta concreta, que lleva uuid", () => {
    const uuid = "3f2504e0-4f89-11d3-9a0c-0305e82c3301";
    expect(destinoSeguro(`/es/carta/${uuid}`, "es")).toBe(`/es/carta/${uuid}`);
  });

  it("rechaza un uuid que no lo es", () => {
    expect(destinoSeguro("/es/carta/../../evil", "es")).toBeNull();
    expect(destinoSeguro("/es/carta/1", "es")).toBeNull();
  });

  it("rechaza cualquier cosa que salga del sitio", () => {
    expect(destinoSeguro("https://evil.com", "es")).toBeNull();
    expect(destinoSeguro("http://evil.com/es/precios", "es")).toBeNull();
    // El clásico: sin esquema, el navegador lo lee como protocolo relativo y
    // sale igual del dominio.
    expect(destinoSeguro("//evil.com", "es")).toBeNull();
    expect(destinoSeguro("//evil.com/es/precios", "es")).toBeNull();
    expect(destinoSeguro("/\\evil.com", "es")).toBeNull();
    expect(destinoSeguro("javascript:alert(1)", "es")).toBeNull();
  });

  it("rechaza un destino de otro idioma que el de la pantalla", () => {
    expect(destinoSeguro("/en/precios", "es")).toBeNull();
  });

  it("rechaza rutas que no están en la lista, aunque sean del sitio", () => {
    expect(destinoSeguro("/es/legal/terms", "es")).toBeNull();
    expect(destinoSeguro("/es", "es")).toBeNull();
    expect(destinoSeguro("/api/session", "es")).toBeNull();
  });

  it("rechaza query y fragmento, que no hacen falta y agrandan la superficie", () => {
    expect(destinoSeguro("/es/precios?comprar=x", "es")).toBeNull();
    expect(destinoSeguro("/es/precios#x", "es")).toBeNull();
  });

  it("rechaza lo vacío y lo ausente", () => {
    expect(destinoSeguro(undefined, "es")).toBeNull();
    expect(destinoSeguro("", "es")).toBeNull();
    expect(destinoSeguro(["/es/precios", "/es/cuenta"], "es")).toBeNull();
  });
});

// El destino de `destinoInternoSeguro` no llega por la query: nace en
// /entrar (donde ya pasó por `destinoSeguro`) y vuelve en la respuesta del
// canje del código de acceso por mail (RF16), cuando en iOS la persona sale a
// Mail y vuelve por otra pestaña. Como no hay locale explícito en ese pedido,
// esta función lo extrae del propio destino y reusa la MISMA lista cerrada —
// nunca una copia— para que un destino nunca sea más permisivo acá que en la
// puerta de entrada.
describe("destinoInternoSeguro", () => {
  it("acepta un path de la lista cerrada, con locale extraído del propio destino", () => {
    expect(destinoInternoSeguro("/es/precios")).toBe("/es/precios");
    expect(destinoInternoSeguro("/en/nueva")).toBe("/en/nueva");
    expect(destinoInternoSeguro("/pt/cuenta")).toBe("/pt/cuenta");
  });

  it("acepta una carta concreta, que lleva uuid", () => {
    const uuid = "3f2504e0-4f89-11d3-9a0c-0305e82c3301";
    expect(destinoInternoSeguro(`/es/carta/${uuid}`)).toBe(`/es/carta/${uuid}`);
  });

  it("rechaza un path que no está en la lista cerrada, aunque tenga forma de interno", () => {
    expect(destinoInternoSeguro("/es/otra-cosa")).toBe("");
    expect(destinoInternoSeguro("/es/legal/terms")).toBe("");
    expect(destinoInternoSeguro("/es")).toBe("");
  });

  it("rechaza un destino absoluto o protocol-relative", () => {
    expect(destinoInternoSeguro("https://malo.example")).toBe("");
    expect(destinoInternoSeguro("//malo.example")).toBe("");
    expect(destinoInternoSeguro("//malo.example/es/precios")).toBe("");
  });

  it("rechaza un primer segmento que no es un locale soportado", () => {
    expect(destinoInternoSeguro("/fr/precios")).toBe("");
    expect(destinoInternoSeguro("/api/session")).toBe("");
  });

  it("rechaza lo vacío, lo ausente y lo que no es string", () => {
    expect(destinoInternoSeguro(undefined)).toBe("");
    expect(destinoInternoSeguro("")).toBe("");
    expect(destinoInternoSeguro(["/es/precios"])).toBe("");
  });
});
