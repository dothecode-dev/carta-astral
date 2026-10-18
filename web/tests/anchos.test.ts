import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// Los anchos de página (18-10-2026). Cada página tenía su propio ancho
// —1180, 1080, 960, 860, 720 y 560 px—, así que cada una arrancaba en otro
// lugar (medido a 1920 px: siete bordes distintos). Ahora toda página se
// centra con uno de tres: columna, sitio o angosto. Un marco no declara otro.

const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");

/** Las reglas cuyo selector es un marco: `.navInner`, `.footInner`, `.frame`
 *  y cualquier `.<algo>Frame` sin nada después (no sus hijos). */
function reglasDeMarco(): { selector: string; cuerpo: string; pos: number }[] {
  const reglas: { selector: string; cuerpo: string; pos: number }[] = [];
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selector = m[1]!.trim().split("\n").pop()!.trim();
    const partes = selector.split(",").map((p) => p.trim());
    if (partes.some((p) => /^(body > )?\.(navInner|footInner|frame|[a-zA-Z]*Frame)(:[a-z-]+\([^)]*\))?$/.test(p))) {
      reglas.push({ selector, cuerpo: m[2]!, pos: m.index! });
    }
  }
  return reglas;
}

describe("anchos del sitio", () => {
  it("encuentra los marcos (si no, el test no prueba nada)", () => {
    const selectores = reglasDeMarco().map((r) => r.selector);
    expect(selectores).toEqual(expect.arrayContaining([".navInner", ".footInner", ".frame", ".docFrame", ".chartFrame"]));
  });

  const PERMITIDOS = [
    "var(--ancho-sitio)",
    "calc(var(--ancho-columna) + 2 * var(--margen-sitio))",
    "calc(var(--ancho-angosto) + 2 * var(--margen-sitio))",
  ];

  it("ningún marco declara un ancho que no sea uno de los tres", () => {
    const sueltos = reglasDeMarco()
      .flatMap(({ selector, cuerpo }) =>
        [...cuerpo.matchAll(/max-width:\s*([^;]+);/g)].map((m) => [selector, m[1]!.trim()] as const),
      )
      .filter(([, valor]) => !PERMITIDOS.includes(valor))
      .map(([selector, valor]) => `${selector} → ${valor}`);
    expect(sueltos).toEqual([]);
  });

  it("los marcos que cambian el ancho vienen después de .docFrame (si no, .docFrame los pisa)", () => {
    // Medido el 18-10-2026: .authFrame estaba antes y /entrar salía con el
    // ancho de columna en vez del angosto.
    const reglas = reglasDeMarco().filter(({ cuerpo }) => /max-width:/.test(cuerpo));
    const docFrame = reglas.find((r) => r.selector === ".docFrame")!.pos;
    const antes = reglas
      .filter(({ selector }) => /Frame/.test(selector) && selector !== ".docFrame")
      .filter(({ pos }) => pos < docFrame)
      .map((r) => r.selector);
    expect(antes).toEqual([]);
  });

  it("el marco de página ocupa el ancho disponible y no se encoge a su contenido", () => {
    // Medido el 18-10-2026: con sólo `max-width`, el main (ítem flex del body)
    // medía lo que su contenido y quedaba centrado; el título de la privacidad
    // arrancaba a 208 px del logo.
    const docFrame = reglasDeMarco().find((r) => r.selector === ".docFrame")!;
    expect(docFrame.cuerpo).toMatch(/width:\s*100%/);
  });

  it("los marcos base usan el mismo margen lateral (los modificadores lo heredan de .docFrame)", () => {
    const base = [".navInner", ".footInner", ".frame", ".docFrame"];
    const sinMargen = reglasDeMarco()
      .filter(({ selector, cuerpo }) => base.includes(selector) && /max-width:/.test(cuerpo))
      .filter(({ cuerpo }) => !/padding:[^;]*var\(--margen-sitio\)/.test(cuerpo))
      .map((r) => r.selector);
    expect(sinMargen).toEqual([]);
  });
});
