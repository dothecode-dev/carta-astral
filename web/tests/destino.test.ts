import { describe, expect, it } from "vitest";

import { destinoSeguro } from "@/lib/destino";

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
