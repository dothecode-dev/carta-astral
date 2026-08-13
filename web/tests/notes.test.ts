import { afterEach, describe, expect, it, vi } from "vitest";

import { LOCALES, NOTES_SLUG, isNotesSection } from "@/lib/i18n";
import {
  fetchNote,
  fetchNotes,
  fetchNotesOrNone,
  fetchTranslations,
  fetchTranslationsOrNone,
  formatNoteDate,
} from "@/lib/notes";

// Las notas llegan del CMS de Wagtail. Lo que importa acá es que un CMS caído
// no se convierta en un listado vacío servido a Google, y que el segmento
// traducido de la URL no acepte el de otro idioma.

function cmsResponde(items: unknown[]) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => ({ meta: { total_count: items.length }, items }),
  });
}

const UNA_NOTA = {
  id: 4,
  meta: { slug: "hora-exacta", first_published_at: "2026-07-28T10:00:00Z" },
  title: "Por qué la hora exacta cambia toda tu carta",
  fecha: "2026-07-28",
  bajada: "Cuatro minutos mueven el ascendente un grado.",
  cuerpo: "<p>El ascendente avanza un grado cada cuatro minutos.</p>",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("segmento traducido", () => {
  it("cada idioma acepta sólo su propia palabra", () => {
    expect(isNotesSection("es", "notas")).toBe(true);
    expect(isNotesSection("en", "notes")).toBe(true);
    // La versión en inglés no se sirve en /en/notas: sería la misma nota en dos
    // URLs distintas compitiendo por la misma consulta.
    expect(isNotesSection("en", "notas")).toBe(false);
    expect(isNotesSection("es", "notes")).toBe(false);
  });

  it("ningún idioma se queda sin palabra", () => {
    for (const locale of LOCALES) {
      expect(NOTES_SLUG[locale]?.trim()).toBeTruthy();
    }
  });

  // `app/[locale]/[section]` es un segmento dinámico: si algún día se agrega una
  // ruta estática que se llame igual que la sección de notas, Next le daría
  // precedencia y el listado dejaría de existir sin que falle nada.
  it("la palabra de la sección no choca con una ruta existente", () => {
    const RUTAS_ESTATICAS = ["ejemplo", "cuenta", "nueva", "entrar", "legal", "carta"];
    for (const locale of LOCALES) {
      expect(RUTAS_ESTATICAS).not.toContain(NOTES_SLUG[locale]);
    }
  });
});

describe("formatNoteDate", () => {
  // Estaba mal y se veía en pantalla: una nota fechada el 28 salía como 27.
  // `new Date("2026-07-28")` es la medianoche UTC de ese día, y formatearla en
  // la zona del servidor la corre un día atrás en todo huso al oeste de
  // Greenwich. El CMS guarda una fecha civil, sin hora ni lugar.
  it("no corre la fecha un día atrás", () => {
    expect(formatNoteDate("es", "2026-07-28")).toBe("28 de julio de 2026");
  });

  it("escribe el mes en el idioma de la nota", () => {
    expect(formatNoteDate("en", "2026-07-28")).toContain("July");
    expect(formatNoteDate("pt", "2026-07-28")).toContain("julho");
  });

  it("acorta el mes cuando se lo piden, para la portada", () => {
    expect(formatNoteDate("es", "2026-07-28", "short")).toContain("2026");
    expect(formatNoteDate("es", "2026-07-28", "short").length).toBeLessThan(
      formatNoteDate("es", "2026-07-28").length,
    );
  });
});

describe("fetchNotes", () => {
  it("pide sólo notas del idioma, de la más nueva a la más vieja", async () => {
    const fetchMock = cmsResponde([UNA_NOTA]);
    vi.stubGlobal("fetch", fetchMock);

    await fetchNotes("es");

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain("type=cms.NotePage");
    expect(url).toContain("locale=es");
    expect(url).toContain("order=-fecha");
  });

  it("saca el slug de meta, que es donde lo pone Wagtail", async () => {
    vi.stubGlobal("fetch", cmsResponde([UNA_NOTA]));

    const [nota] = await fetchNotes("es");

    expect(nota.slug).toBe("hora-exacta");
    expect(nota.title).toBe(UNA_NOTA.title);
    expect(nota.fecha).toBe("2026-07-28");
    expect(nota.portada).toBeNull();
  });

  it("rechaza un 200 que no sea JSON, con un mensaje que se entienda", async () => {
    // Pasó en desarrollo: en el puerto del backend había otro servicio que
    // redirigía a su login, y el error era "Unexpected token '<'".
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "text/html" }),
        json: async () => {
          throw new SyntaxError("Unexpected token '<'");
        },
      }),
    );

    await expect(fetchNotes("es")).rejects.toThrow("API_URL");
  });

  it("propaga el fallo del CMS en vez de devolver una lista vacía", async () => {
    // Si esto devolviera [], el listado se regeneraría diciendo "todavía no hay
    // notas" y eso es lo que vería Google. Al lanzar, Next descarta la
    // regeneración y sigue sirviendo la última versión buena.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 502 }));

    await expect(fetchNotes("es")).rejects.toThrow("502");
  });
});

describe("fetchNotesOrNone", () => {
  it("se traga el fallo, para que el sitemap no tire abajo el build", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("sin red")));

    await expect(fetchNotesOrNone("es")).resolves.toEqual([]);
  });
});

describe("fetchTranslations", () => {
  it("devuelve idioma y slug de cada versión publicada", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        meta: { total_count: 2 },
        items: [
          { id: 16, meta: { slug: "exact-birth-time", locale: "en" }, title: "", fecha: "", bajada: "" },
          { id: 17, meta: { slug: "hora-exata-de-nascimento", locale: "pt" }, title: "", fecha: "", bajada: "" },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const traducciones = await fetchTranslations(13);

    expect(fetchMock.mock.calls[0][0]).toContain("translation_of=13");
    expect(traducciones).toEqual([
      { locale: "en", slug: "exact-birth-time" },
      { locale: "pt", slug: "hora-exata-de-nascimento" },
    ]);
  });

  it("descarta lo que no sea uno de los tres idiomas", async () => {
    // Si mañana se agrega un locale en Wagtail y no en la web, esa traducción
    // no puede convertirse en un hreflang hacia una ruta que no existe.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          meta: { total_count: 1 },
          items: [{ id: 20, meta: { slug: "x", locale: "de" }, title: "", fecha: "", bajada: "" }],
        }),
      }),
    );

    await expect(fetchTranslations(13)).resolves.toEqual([]);
  });

  it("no tumba la nota si el CMS falla al pedirlas", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("sin red")));

    await expect(fetchTranslationsOrNone(13)).resolves.toEqual([]);
  });
});

describe("fetchNote", () => {
  it("devuelve null si el idioma no tiene esa nota", async () => {
    vi.stubGlobal("fetch", cmsResponde([]));

    await expect(fetchNote("en", "hora-exacta")).resolves.toBeNull();
  });

  it("trae el cuerpo ya expandido por el backend", async () => {
    vi.stubGlobal("fetch", cmsResponde([UNA_NOTA]));

    const nota = await fetchNote("es", "hora-exacta");

    expect(nota?.cuerpo).toContain("<p>");
  });

  it("escapa el slug antes de pegarlo en la query", async () => {
    const fetchMock = cmsResponde([]);
    vi.stubGlobal("fetch", fetchMock);

    await fetchNote("es", "a b&c");

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain("slug=a%20b%26c");
  });
});
