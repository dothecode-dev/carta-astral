import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/** Los dos ambientes se calibran con el mismo piso de contraste, y lo chequea
 *  este test, no la prosa.
 *
 *  Hasta el 09-09-2026 el gris secundario de día tenía 5,23:1 contra el fondo y
 *  el de noche 7,41:1: el mismo token pesaba un 40% menos de un lado que del
 *  otro, y en día —texto oscuro sobre fondo claro— eso se lee como texto
 *  lavado. Nadie lo notó porque no había forma de notarlo: los valores son
 *  hexadecimales sueltos en `globals.css` y el contraste no se ve mirándolos.
 *
 *  Los pisos son más altos que el mínimo de WCAG AA (4,5:1) a propósito. 4,5 es
 *  el mínimo legal para un párrafo de 16px, y casi todo lo que usa estos tokens
 *  es más chico que eso: etiquetas de 10 a 13px, en mayúscula y con tracking.
 *  El valor viejo cumplía AA y se leía mal igual. */

const PISOS: Record<string, number> = {
  // Texto principal. Es el que sostiene la lectura larga.
  ink: 12,
  // Párrafos y bajadas secundarias, en Outfit de 15px para arriba.
  "ink-soft": 7,
  // Etiquetas y datos en Space Mono, de 10 a 13px, en mayúscula y con
  // tracking. Ese trazo fino y separado aparenta menos peso del que mide, así
  // que su piso es más alto que el del párrafo, no más bajo.
  "ink-label": 8.5,
  // El dorado. Es color de texto en enlaces, glifos y etiquetas chicas, no
  // sólo un adorno: el «EL MÁS ELEGIDO» de /precios sale de acá.
  accent: 5.5,
  // Errores de formulario, estado del cupón, el aviso de borrar la cuenta.
  // Un error que no se lee es peor que no mostrarlo.
  danger: 4.5,
};

/** Un color por token, por ambiente, tal como sale del archivo. */
type Tema = Record<string, string>;

const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");

/** Los bloques de tokens de `globals.css`, en orden de aparición.
 *
 *  Son cuatro y están duplicados a propósito: cada ambiente se declara una vez
 *  para `prefers-color-scheme` (la preferencia del sistema) y otra para
 *  `[data-theme]` (la elección explícita en el interruptor). */
function bloques(): { nombre: string; tema: Tema }[] {
  const encontrados: { nombre: string; tema: Tema }[] = [];
  const re = /(:root(?:\[data-theme="(?:dark|light)"\])?)\s*\{([^}]*)\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(css)) !== null) {
    const cuerpo = m[2];
    if (!cuerpo.includes("--ground:")) continue;
    const tema: Tema = {};
    for (const [, nombre, valor] of cuerpo.matchAll(/--([a-z-]+):\s*(#[0-9a-f]{6})\s*;/gi)) {
      tema[nombre] = valor.toLowerCase();
    }
    // Dentro del media query el selector es `:root` a secas, igual que el
    // bloque de noche por defecto: el ambiente lo dice el fondo, no el selector.
    const esDia = tema.ground === "#efeaf1";
    encontrados.push({ nombre: `${esDia ? "día" : "noche"} (${m[1]}, offset ${m.index})`, tema });
  }
  return encontrados;
}

function canal(valor: number): number {
  const c = valor / 255;
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function luminancia(hex: string): number {
  const n = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => canal(parseInt(n.slice(i, i + 2), 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** El contraste de WCAG 2.1: (L más claro + 0,05) / (L más oscuro + 0,05). */
function contraste(a: string, b: string): number {
  const [la, lb] = [luminancia(a), luminancia(b)];
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

describe("contraste de los tokens de color", () => {
  const temas = bloques();

  it("encuentra los cuatro bloques de tokens", () => {
    // Si este falla, el archivo se reorganizó y el resto del test está mirando
    // menos superficie de la que cree.
    expect(temas.map((t) => t.nombre.split(" ")[0])).toEqual(["noche", "día", "noche", "día"]);
  });

  for (const [token, piso] of Object.entries(PISOS)) {
    it(`${token} llega a ${piso}:1 sobre el fondo y sobre las tarjetas, en los dos ambientes`, () => {
      for (const { nombre, tema } of temas) {
        expect(tema[token], `${token} falta en el bloque ${nombre}`).toBeDefined();
        for (const fondo of ["ground", "surface"] as const) {
          const medido = contraste(tema[token], tema[fondo]);
          expect(
            Number(medido.toFixed(2)),
            `${token} (${tema[token]}) sobre ${fondo} (${tema[fondo]}) en ${nombre}`,
          ).toBeGreaterThanOrEqual(piso);
        }
      }
    });
  }

  it("los dos bloques de un mismo ambiente declaran los mismos valores", () => {
    // Cada ambiente está escrito dos veces —una por `prefers-color-scheme` y
    // otra por `[data-theme]`— y nada obliga a que coincidan. Si se editan por
    // separado, el sitio cambia de colores según cómo lo haya elegido cada
    // persona, que es la clase de diferencia que nadie reproduce.
    const porAmbiente = new Map<string, Tema[]>();
    for (const { nombre, tema } of temas) {
      const clave = nombre.split(" ")[0];
      porAmbiente.set(clave, [...(porAmbiente.get(clave) ?? []), tema]);
    }
    for (const [ambiente, [uno, otro]] of porAmbiente) {
      expect(uno, `los dos bloques de ${ambiente} difieren`).toEqual(otro);
    }
  });
});
