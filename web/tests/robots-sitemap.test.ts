import { describe, expect, it, vi } from "vitest";

import robots from "@/app/robots";
import sitemap from "@/app/sitemap";

// Sin CMS en el CI: el sitemap sale sin notas, que acá no importan.
vi.mock("@/lib/notes", () => ({ fetchNotesOrNone: async () => [] }));

/**
 * Ninguna página del sitemap puede estar prohibida en `robots.txt`.
 *
 * El 04-09-2026 `/nueva` pasó a ser indexable y entró al sitemap, pero siguió en
 * la lista de `disallow` de `robots.ts`. Google la tuvo un mes en «Discovered -
 * currently not indexed» —el calculador, que es la página que convierte— y nada
 * avisó: cada archivo, por separado, estaba bien. Esto los cruza.
 */

/** Un patrón de robots.txt (`*` comodín, `$` fin) contra una ruta. */
function bloquea(patron: string, ruta: string): boolean {
  const re = patron
    .replace(/[.+?^{}()|[\]\\]/g, "\\$&")
    .replace(/\*/g, ".*")
    .replace(/\$$/, "$");
  return new RegExp("^" + re).test(ruta);
}

function prohibidos(): string[] {
  const reglas = robots().rules;
  const una = Array.isArray(reglas) ? reglas[0] : reglas;
  const d = una.disallow ?? [];
  return Array.isArray(d) ? d : [d];
}

describe("robots.txt contra el sitemap", () => {
  it("el matcher entiende los comodines", () => {
    expect(bloquea("/*/nueva", "/es/nueva")).toBe(true);
    // Son prefijos, no rutas exactas: así lo lee Google.
    expect(bloquea("/*/nueva", "/es/notas/nueva-luna")).toBe(true);
    expect(bloquea("/*/nueva", "/es/precios")).toBe(false);
    expect(bloquea("/api/", "/api/sky/")).toBe(true);
  });

  it("ninguna URL del sitemap está prohibida", async () => {
    const entradas = await sitemap();
    const bloqueadas = entradas
      .map((e) => new URL(e.url).pathname)
      .filter((ruta) => prohibidos().some((p) => bloquea(p, ruta)));

    expect(bloqueadas).toEqual([]);
  });

  it("lo privado sigue prohibido", () => {
    for (const ruta of ["/es/cuenta", "/es/carta/3f2a1b4c", "/api/charts"]) {
      expect(prohibidos().some((p) => bloquea(p, ruta)), ruta).toBe(true);
    }
  });
});
