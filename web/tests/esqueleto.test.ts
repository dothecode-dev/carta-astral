import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * El esqueleto que toda página tiene que seguir:
 *
 *     <>
 *       <Nav ... />
 *       <main className="docFrame ..."> ... </main>
 *       <Footer locale={locale} dict={dict} />
 *     </>
 *
 * `Nav` y `Footer` traen su propio marco (`navInner`, `footInner`), así que van
 * sueltos y ocupan el ancho de la ventana; el contenido va en `<main>`, que es
 * quien pone la medida de esa página.
 *
 * Esto es un test y no un párrafo en CLAUDE.md porque una regla que no se
 * chequea no es una regla. El 03-09-2026 `/precios` tenía el `Footer` fuera del
 * `<main>` cuando las otras diez lo tenían adentro: como el pie no traía marco
 * propio, se estiraba hasta el borde de la ventana contra un header contenido.
 * Y dos páginas usaban `<div className="docFrame">` en vez de `<main>`, o sea
 * que no tenían landmark principal.
 *
 * Se lee el fuente en vez de renderizar: son Server Components asíncronos que
 * piden datos, y lo que se quiere fijar es la FORMA de la página, que está a la
 * vista en el archivo.
 */

const PAGINAS = "app/[locale]";

function paginas(dir: string): string[] {
  return readdirSync(dir).flatMap((entrada) => {
    const ruta = join(dir, entrada);
    if (statSync(ruta).isDirectory()) return paginas(ruta);
    return entrada === "page.tsx" ? [ruta] : [];
  });
}

/** Si la página renderiza algo. Una que sólo redirige —`carta/[id]/lectura`,
 *  que existe para no romper enlaces viejos— no tiene esqueleto que seguir.
 *
 *  El criterio es "no devuelve JSX", no "no tiene <Nav>": si fuera lo segundo,
 *  una página nueva a la que le falta el Nav se saltearía el test justamente
 *  por el defecto que este test busca. */
function renderiza(fuente: string): boolean {
  return /return\s*\(\s*</.test(fuente);
}

const TODAS = paginas(PAGINAS);
const RUTAS = TODAS.filter((ruta) => renderiza(readFileSync(ruta, "utf8")));
const REDIRECTS = TODAS.filter((ruta) => !RUTAS.includes(ruta));

describe("el esqueleto de las páginas", () => {
  it("encuentra todas las páginas", () => {
    // Si alguien agrega una y este número no se mueve, el glob dejó de andar.
    expect(RUTAS.length).toBeGreaterThanOrEqual(11);
  });

  it("las que no renderizan son sólo las que redirigen", () => {
    // A la vista, para que exceptuar una página sea una decisión y no un
    // descuido: lo único que puede no tener esqueleto es una redirección.
    for (const ruta of REDIRECTS) {
      expect(readFileSync(ruta, "utf8")).toContain("redirect(");
    }
  });

  it.each(RUTAS)("%s tiene <Nav> y <Footer>", (ruta) => {
    const fuente = readFileSync(ruta, "utf8");
    expect(fuente).toContain("<Nav");
    // Los legales se alcanzan desde cualquier página, o no se alcanzan.
    expect(fuente).toContain("<Footer");
  });

  it.each(RUTAS)("%s envuelve su contenido en <main>", (ruta) => {
    const fuente = readFileSync(ruta, "utf8");
    // El landmark principal: un lector de pantalla salta al contenido con él.
    expect(fuente).toContain("<main");
  });

  it.each(RUTAS)("%s deja el <Footer> fuera del <main>", (ruta) => {
    const fuente = readFileSync(ruta, "utf8");
    // Adentro hereda el `max-width` del marco de esa página y el pie deja de
    // estar alineado con la cabecera, que es el borde del sitio.
    expect(fuente.indexOf("<Footer")).toBeGreaterThan(fuente.indexOf("</main>"));
  });

  it.each(RUTAS)("%s abre con el <Nav>, antes que nada", (ruta) => {
    const fuente = readFileSync(ruta, "utf8");
    expect(fuente.indexOf("<Nav")).toBeLessThan(fuente.indexOf("<main"));
  });
});

describe("Nav y Footer traen su propio marco", () => {
  // Es lo que hace que el esqueleto no dependa de quién los envuelva. Si
  // alguien saca el `Inner`, el ancho del pie vuelve a decidirlo cada página y
  // el bug de /precios puede repetirse en la próxima que se agregue.
  it("el Nav tiene navInner", () => {
    expect(readFileSync("components/Nav.tsx", "utf8")).toContain('className="navInner"');
  });

  it("el Footer tiene footInner", () => {
    expect(readFileSync("components/Footer.tsx", "utf8")).toContain('className="footInner"');
  });

  it("los dos marcos usan la misma medida", () => {
    const css = readFileSync("app/globals.css", "utf8");
    const medida = (selector: string) =>
      css.match(new RegExp(`\\.${selector}\\s*\\{[^}]*max-width:\\s*([^;]+);`))?.[1].trim();

    expect(medida("navInner")).toBeDefined();
    // Alineados entre sí: son el borde del sitio, aunque el contenido de cada
    // página use una medida más angosta.
    expect(medida("footInner")).toBe(medida("navInner"));
  });
});
