import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

/**
 * `/nueva` se mira sin cuenta, y es indexable.
 *
 * Las dos cosas se pueden deshacer con una línea —un `redirect` al login, un
 * `robots: { index: false }`— y nada más las notaría hasta ver caer el
 * tráfico. Hasta el 04-09-2026 la página redirigía al login: el CTA de la home
 * terminaba ahí, así que el visitante que llegaba de una búsqueda o de
 * Instagram chocaba con un registro antes de ver nada, mientras `/precios` le
 * prometía tres lecturas gratis.
 *
 * Se lee el fuente en vez de renderizar, como en `esqueleto.test.ts`: son
 * Server Components asíncronos y lo que se quiere fijar está a la vista.
 */

const PAGINA = readFileSync("app/[locale]/nueva/page.tsx", "utf8");

describe("/nueva es la puerta de entrada, no una puerta cerrada", () => {
  it("no manda a entrar", () => {
    expect(PAGINA).not.toMatch(/redirect\(/);
  });

  it("no se excluye de los buscadores", () => {
    expect(PAGINA).not.toMatch(/robots/);
  });

  it("se declara canónica y traducida", () => {
    expect(PAGINA).toMatch(/canonical/);
    expect(PAGINA).toMatch(/x-default/);
  });

  it("trae texto propio para quien llega sin sesión", () => {
    // Un formulario solo no es contenido indexable para nadie.
    expect(PAGINA).toMatch(/seoQueEsBody/);
    expect(PAGINA).toMatch(/seoHoraBody/);
  });

  it("está en el sitemap", () => {
    const sitemap = readFileSync("app/sitemap.ts", "utf8");
    const paths = sitemap.match(/const PATHS = \[([\s\S]*?)\]/)?.[1] ?? "";
    expect(paths).toContain('"/nueva"');
  });

  it("calcula contra un endpoint que no pide sesión", () => {
    const route = readFileSync("app/api/charts/preview/route.ts", "utf8");
    expect(route).toMatch(/auth: false/);
  });

  it("busca el lugar sin pedir sesión", () => {
    // Abrir la vista del backend no alcanzaba: este proxy exigía el token por
    // su cuenta y devolvía 401, así que el formulario anónimo no podía decir
    // dónde nació nadie. No lo vio ningún test de los dos lados —cada uno
    // pasaba— sino recorrer el formulario en el navegador (04-09-2026).
    const route = readFileSync("app/api/geocode/route.ts", "utf8");
    expect(route).toMatch(/auth: false/);
  });
});
