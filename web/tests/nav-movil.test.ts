import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

// La barra en un teléfono. No hay jsdom que mida CSS, así que se lee la hoja
// como texto —el mismo criterio que `esqueleto.test.ts` con las páginas—.
const css = readFileSync("app/globals.css", "utf8");

/** El primer bloque de 640px, entero (es el de la barra). */
function bloque640(): string {
  const inicio = css.indexOf("@media (max-width: 640px)");
  const fin = css.indexOf("\n}\n", inicio);
  return css.slice(inicio, fin);
}

describe("la barra en móvil", () => {
  it("no es sticky: medía un quinto de la pantalla y se la llevaba en todas las páginas", () => {
    expect(bloque640()).toMatch(/\.nav\s*\{[^}]*position:\s*static/);
  });
});
