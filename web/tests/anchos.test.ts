import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// Los anchos del sitio (18-10-2026). Cada página tenía su propio ancho
// —1180, 1080, 960, 860, 720 y 560 px— y se centraba, así que el título de
// cada una arrancaba en otro lugar y ninguno donde el logo (medido a 1920 px:
// siete bordes distintos). Un marco de página no declara un ancho propio: usa
// el del sitio, y lo angosto se acota adentro.

const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");

/** Las reglas cuyo selector es un marco: `.navInner`, `.footInner`, `.frame`
 *  y cualquier `.<algo>Frame` sin nada después (no sus hijos). */
function reglasDeMarco(): { selector: string; cuerpo: string }[] {
  const reglas: { selector: string; cuerpo: string }[] = [];
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selector = m[1]!.trim().split("\n").pop()!.trim();
    const partes = selector.split(",").map((p) => p.trim());
    if (partes.some((p) => /^(body > )?\.(navInner|footInner|frame|[a-zA-Z]*Frame)(:[a-z-]+\([^)]*\))?$/.test(p))) {
      reglas.push({ selector, cuerpo: m[2]! });
    }
  }
  return reglas;
}

describe("anchos del sitio", () => {
  it("encuentra los marcos (si no, el test no prueba nada)", () => {
    const selectores = reglasDeMarco().map((r) => r.selector);
    expect(selectores).toEqual(expect.arrayContaining([".navInner", ".footInner", ".frame", ".docFrame", ".chartFrame"]));
  });

  it("ningún marco declara un ancho que no sea el del sitio", () => {
    const sueltos = reglasDeMarco()
      .flatMap(({ selector, cuerpo }) =>
        [...cuerpo.matchAll(/max-width:\s*([^;]+);/g)].map((m) => `${selector} → ${m[1]!.trim()}`),
      )
      .filter((d) => !d.endsWith("var(--ancho-sitio)"));
    expect(sueltos).toEqual([]);
  });

  it("el marco de página ocupa el ancho disponible y no se encoge a su contenido", () => {
    // Medido el 18-10-2026: con sólo `max-width`, el main (ítem flex del body)
    // medía lo que su contenido y quedaba centrado; el título de la privacidad
    // arrancaba a 208 px del logo.
    const docFrame = reglasDeMarco().find((r) => r.selector === ".docFrame")!;
    expect(docFrame.cuerpo).toMatch(/width:\s*100%/);
  });

  it("todos los marcos con ancho usan el mismo margen lateral", () => {
    const sinMargen = reglasDeMarco()
      .filter(({ cuerpo }) => /max-width:\s*var\(--ancho-sitio\)/.test(cuerpo))
      .filter(({ cuerpo }) => !/padding:[^;]*var\(--margen-sitio\)/.test(cuerpo))
      .map((r) => r.selector);
    expect(sinMargen).toEqual([]);
  });
});
