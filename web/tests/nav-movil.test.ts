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

describe("los desplegables anidados", () => {
  it("el chevrón de abierto es sólo del propio summary, no de los hijos", () => {
    // DatosCarta envuelve a los de casas y aspectos: con el descendiente
    // (" ") los internos cerrados giraban al abrir el padre.
    expect(css).toMatch(/\.foldout\[open\]\s*>\s*\.foldoutHead::after/);
    expect(css).not.toMatch(/\.foldout\[open\]\s+\.foldoutHead::after/);
  });
});

describe("la barra fija de la carta", () => {
  it("se esconde mientras está el banner de consentimiento", () => {
    // Los dos son fixed abajo; el banner tiene más z-index y tapaba el botón
    // principal justo en la primera visita.
    expect(css).toMatch(/body:has\(\.consentBar\)\s+\.accionFija\s*\{[^}]*display:\s*none/);
  });
});
