import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/** El piso de tamaño del texto, que es la otra mitad de la legibilidad.
 *
 *  El contraste lo mide `contraste.test.ts`; esto mide el cuerpo. Hasta el
 *  09-09-2026 había veinte reglas entre 10 y 11px —el pie entero, las
 *  cabeceras de las tablas de la carta, la leyenda de la rueda, las etiquetas
 *  de los campos, la zona horaria del lugar—, casi todas en Space Mono, en
 *  mayúscula y con tracking. A ese tamaño, con esas letras separadas, el
 *  tracking que las hace ver ordenadas es lo mismo que las hace ilegibles.
 *
 *  12px es el piso, no el objetivo: un texto que alguien tiene que leer para
 *  entender la pantalla merece más que el mínimo. */
const PISO_REM = 0.75;

const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");

/** Cada `font-size` en rem del archivo, con el selector que lo declara. */
function tamaños(): { selector: string; rem: number }[] {
  const encontrados: { selector: string; rem: number }[] = [];
  for (const [, selector, cuerpo] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const m = cuerpo.match(/font-size:\s*([0-9.]+)rem\s*;/);
    if (!m) continue;
    // El selector puede venir precedido por un comentario en la misma captura.
    const limpio = selector.replace(/\/\*[\s\S]*?\*\//g, "").trim().replace(/\s+/g, " ");
    encontrados.push({ selector: limpio, rem: Number(m[1]) });
  }
  return encontrados;
}

describe("piso de tamaño del texto", () => {
  it(`ninguna regla declara menos de ${PISO_REM}rem`, () => {
    const chicos = tamaños()
      .filter((t) => t.rem < PISO_REM)
      .map((t) => `${t.selector} → ${t.rem}rem (${t.rem * 16}px)`);
    expect(chicos).toEqual([]);
  });

  it("encuentra los tamaños del archivo", () => {
    // Si el archivo se reorganiza y este parser deja de ver los `font-size`,
    // el test de arriba pasa por vacío y no protege nada.
    expect(tamaños().length).toBeGreaterThan(30);
  });
});

/** Los caracteres del zodíaco y de los aspectos (U+2600–U+26FF) no están en
 *  Outfit ni en Fraunces. Cuando un elemento que los muestra queda en esas
 *  familias, el navegador resuelve el glifo por su cuenta y en macOS/iOS llega
 *  a la fuente de emoji: sale un cuadrito de color en medio del texto, que es
 *  una letra ajena al sistema del sitio.
 *
 *  Pasó con `.noteSign` —el signo solar de cada carta en `/cuenta`—, que hasta
 *  el 09-09-2026 no tenía NINGUNA regla y heredaba `body`. En Space Mono el
 *  fallback llega antes a una fuente de símbolos monocroma, que es como ya se
 *  ven los mismos glifos en el riel de la home y en la matriz de aspectos. */
describe("los glifos astrológicos no caen en la fuente de emoji", () => {
  const cuerpoDe = (clase: string) => {
    const m = css.match(new RegExp(`\\.${clase}\\s*\\{([^}]*)\\}`));
    return m?.[1] ?? "";
  };

  it(".noteSign declara la familia mono, no hereda body", () => {
    expect(cuerpoDe("noteSign")).toMatch(/font-family:\s*var\(--font-mono\)/);
  });

  it("no queda ninguna clase de glifo sin familia NI contenedor mono", () => {
    // `.matrixMark` y `.ephemGlyph` no declaran familia y está bien: heredan de
    // un contenedor que sí la tiene (`.matrixCell`, `.ephemRow`), verificado en
    // producción con `getComputedStyle`. Lo que no puede pasar es que ni la
    // clase ni su contenedor la declaren, que es lo que le pasaba a
    // `.noteSign`: ahí no hay de dónde heredar más que del `body`.
    expect(cuerpoDe("matrixCell") + cuerpoDe("ephemRow")).toMatch(
      /font-family:\s*var\(--font-mono\)/,
    );
  });
});
