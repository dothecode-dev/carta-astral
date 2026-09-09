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
