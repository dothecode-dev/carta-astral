import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Ninguna ruta de `app/api/**` puede llamar al backend con `fetch` directo:
 * tiene que pasar por `callApi`/`callApiRaw` (`lib/session.ts`), que son
 * quienes reenvían la IP del visitante (C1, generalizado). Antes ese reenvío
 * era una cabecera que cada ruta copiaba a mano —y sólo dos de las nueve lo
 * hacían—; ahora es un default de `callApi`/`callApiRaw` que ninguna ruta
 * nueva puede evitar mientras no llame a `fetch` por su cuenta.
 *
 * Este test no puede probar el reenvío en sí —para eso están los tests de
 * `callApi`/`callApiRaw` en `session.test.ts`, que sí lo generalizan a
 * cualquier ruta futura—, pero sí puede detectar la única forma de saltearlo:
 * que una ruta nueva hable con el backend por su cuenta en vez de usar el
 * punto único de salida.
 */

const RUTAS_API = "app/api";

function rutas(dir: string): string[] {
  return readdirSync(dir).flatMap((entrada) => {
    const ruta = join(dir, entrada);
    if (statSync(ruta).isDirectory()) return rutas(ruta);
    return entrada === "route.ts" ? [ruta] : [];
  });
}

const TODAS = rutas(RUTAS_API);

describe("las rutas de app/api no pegan al backend con fetch directo", () => {
  it("encuentra todas las rutas", () => {
    // Si alguien agrega una y este número no se mueve, el glob dejó de andar.
    expect(TODAS.length).toBeGreaterThanOrEqual(11);
  });

  it.each(TODAS)("%s usa callApi/callApiRaw, no fetch directo", (ruta) => {
    const fuente = readFileSync(ruta, "utf8");
    expect(fuente).not.toMatch(/\bfetch\s*\(/);
  });
});
