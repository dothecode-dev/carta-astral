import { beforeEach, describe, expect, it, vi } from "vitest";

import robots from "@/app/robots";
import sitemap from "@/app/sitemap";
import { SYNASTRY_SLUG } from "@/lib/i18n";

// Sin CMS en el CI: el sitemap sale sin notas, que acá no importan.
vi.mock("@/lib/notes", () => ({ fetchNotesOrNone: async () => [] }));

// Sin backend en el CI —y sin pegarle a producción desde una máquina con red—:
// si Vínculo está encendido lo decide cada test.
const vinculo = vi.hoisted(() => ({ activo: false }));
vi.mock("@/lib/vinculo", async (original) => ({
  ...(await original<typeof import("@/lib/vinculo")>()),
  vinculoActivo: async () => vinculo.activo,
}));

beforeEach(() => {
  vinculo.activo = false;
});

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

  // Los dos estados del flag de Vínculo: con la vista previa encendida el
  // sitemap trae tres URLs más, y ninguna puede estar prohibida.
  it.each([false, true])("ninguna URL del sitemap está prohibida (Vínculo %s)", async (activo) => {
    vinculo.activo = activo;
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

describe("Vínculo en el sitemap", () => {
  const paths = Object.values(SYNASTRY_SLUG).map((slug) => `/${slug}`);

  it("encendido: las tres landings, cada una con sus tres idiomas y x-default", async () => {
    vinculo.activo = true;
    const entradas = await sitemap();
    const urls = entradas.map((e) => new URL(e.url).pathname);

    for (const locale of ["es", "en", "pt"] as const) {
      expect(urls).toContain(`/${locale}/${SYNASTRY_SLUG[locale]}`);
    }

    const es = entradas.find((e) => new URL(e.url).pathname === "/es/sinastria")!;
    expect(Object.keys(es.alternates?.languages ?? {}).sort()).toEqual(["en", "es", "pt", "x-default"]);
    expect(es.alternates?.languages?.en).toMatch(/\/en\/synastry$/);
    expect(es.alternates?.languages?.pt).toMatch(/\/pt\/sinastria$/);
    expect(es.alternates?.languages?.["x-default"]).toMatch(/\/es\/sinastria$/);
  });

  it("apagado: ninguna landing, para no anunciar un 404", async () => {
    vinculo.activo = false;
    const urls = (await sitemap()).map((e) => new URL(e.url).pathname);
    expect(urls.filter((u) => paths.some((p) => u.endsWith(p)))).toEqual([]);
  });
});
