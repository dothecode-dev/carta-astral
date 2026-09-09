import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Ninguna ruta de `app/api/**` ni función de `lib/**` puede llamar al backend
 * con `fetch` directo: tiene que pasar por `callApi`/`callApiRaw`
 * (`lib/session.ts`), que son quienes reenvían la IP del visitante (C1,
 * generalizado). Antes ese reenvío era una cabecera que cada ruta copiaba a
 * mano —y sólo dos de las nueve lo hacían—; ahora es un default de
 * `callApi`/`callApiRaw` que ninguna ruta nueva puede evitar mientras no
 * llame a `fetch` por su cuenta.
 *
 * NO es verdad que TODA llamada al backend pase por `callApi`: `lib/sky.ts`,
 * `lib/catalogo.ts` y `lib/notes.ts` son excepciones nombradas, con la razón
 * escrita en cada archivo (y repetida abajo, para que este test no pueda
 * mentir por separado). Las tres sirven datos públicos con caché de Next por
 * `next.revalidate` —una petición por revalidación, no una por visitante—, y
 * `callApi` fuerza `cache: "no-store"`, que la guía de `fetch`
 * (`node_modules/next/dist/docs/01-app/03-api-reference/04-functions/fetch.md`,
 * "Good to know") documenta como conflictivo con `next.revalidate`: Next
 * ignora las dos opciones. `lib/notes.ts` además la usa `app/sitemap.ts`, un
 * contexto de build sin pedido: se comprobó con `next build` que forzar
 * `headers()` ahí no revienta, pero convierte `/sitemap.xml` de estático
 * (revalida cada 5m) a dinámico (una consulta al CMS por pedido) — el tipo de
 * cambio que hay que frenar y avisar, no decidir en un test.
 *
 * `lib/session.ts` tampoco entra: es donde viven `callApi`/`callApiRaw`, el
 * único lugar que puede llamar a `fetch` porque es la implementación.
 *
 * Este test no puede probar el reenvío en sí —para eso están los tests de
 * `callApi`/`callApiRaw` en `session.test.ts`, que sí lo generalizan a
 * cualquier ruta futura—, pero sí puede detectar la única forma de saltearlo:
 * que una ruta o función nueva hable con el backend por su cuenta en vez de
 * usar el punto único de salida.
 */

const RUTAS_API = "app/api";
const LIB = "lib";

/** Sin caché de Next que perder (`cupon.ts`, no-store) o sin techo que
 *  proteger (`catalogo.ts`, `sky.ts`, `notes.ts`): la razón completa de cada
 *  una vive en su propio archivo, no acá. */
const EXCEPCIONES_LIB = new Set(["lib/session.ts", "lib/sky.ts", "lib/catalogo.ts", "lib/notes.ts"]);

function rutas(dir: string): string[] {
  return readdirSync(dir).flatMap((entrada) => {
    const ruta = join(dir, entrada);
    if (statSync(ruta).isDirectory()) return rutas(ruta);
    return entrada === "route.ts" ? [ruta] : [];
  });
}

function archivosLib(dir: string): string[] {
  return readdirSync(dir).flatMap((entrada) => {
    const ruta = join(dir, entrada);
    if (statSync(ruta).isDirectory()) return archivosLib(ruta);
    return entrada.endsWith(".ts") && !entrada.endsWith(".test.ts") ? [ruta] : [];
  });
}

const TODAS = rutas(RUTAS_API);
const TODO_LIB = archivosLib(LIB).filter((ruta) => !EXCEPCIONES_LIB.has(ruta));

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

describe("las funciones de lib/ no pegan al backend con fetch directo", () => {
  it("encuentra todos los archivos de lib/ (fuera de las excepciones)", () => {
    // Si alguien agrega uno y este número no se mueve, el glob dejó de andar.
    expect(TODO_LIB.length).toBeGreaterThanOrEqual(5);
  });

  it.each(TODO_LIB)("%s usa callApi/callApiRaw, no fetch directo", (ruta) => {
    const fuente = readFileSync(ruta, "utf8");
    expect(fuente).not.toMatch(/\bfetch\s*\(/);
  });

  it("las excepciones siguen existiendo y siguen siendo las únicas con fetch directo", () => {
    // Si una excepción deja de llamar a fetch (porque alguien la migró a
    // callApi), hay que sacarla de la lista: una excepción sin fetch adentro
    // es documentación mintiendo.
    for (const ruta of EXCEPCIONES_LIB) {
      if (ruta === "lib/session.ts") continue; // la implementación, no una excepción de caché
      const fuente = readFileSync(ruta, "utf8");
      expect(fuente, `${ruta} ya no usa fetch directo: sacala de EXCEPCIONES_LIB`).toMatch(
        /\bfetch\s*\(/,
      );
    }
  });
});
