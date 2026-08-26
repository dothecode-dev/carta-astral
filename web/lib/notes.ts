import { API_URL } from "./config";
import { INTL_LOCALE, isLocale, type Locale } from "./i18n";

// Las notas viven en el CMS de Wagtail (`backend/cms/`) y se leen por su API
// pública. El pedido sale del servidor de Next, como el del cielo en `sky.ts`:
// el backend recibe una petición por revalidación, no una por visitante.
//
// A diferencia de `sky.ts`, acá un fallo NO se degrada en silencio. Si el CMS
// no contesta y devolviéramos una lista vacía, el listado se regeneraría
// mostrando "todavía no hay notas" y eso es lo que vería Google en ese momento.
// Se lanza el error: Next descarta la regeneración y sigue sirviendo la última
// versión buena que tenga en caché.

const REVALIDATE_SECONDS = 300;
const TIMEOUT_MS = 5000;

/** El techo existe para que un CMS con mil notas no tire abajo el build. */
const MAX_NOTES = 200;

type ApiImage = {
  /** Relativa al CMS. Inservible en la web: son dominios distintos. */
  url: string;
  full_url: string;
  width: number;
  height: number;
  alt: string;
};

/** La portada, con la URL que sí resuelve desde el navegador.
 *
 * Wagtail devuelve `url` relativa a sí mismo y `full_url` absoluta. La web vive
 * en otro dominio que el CMS, así que la relativa se resuelve contra la web y
 * da 404 —la nota sale con la imagen rota, y el `og:image` con una URL que
 * ningún scraper puede seguir—. Se normaliza acá, una vez, y el resto del
 * código usa `portada.url` sin pensar. */
function conUrlAbsoluta(img: ApiImage | null | undefined): ApiImage | null {
  if (!img) return null;
  return { ...img, url: img.full_url || img.url };
}

type ApiNote = {
  id: number;
  meta: { slug: string; locale?: string; first_published_at: string | null };
  title: string;
  fecha: string;
  bajada: string;
  portada_tarjeta?: ApiImage | null;
  portada_cabecera?: ApiImage | null;
  cuerpo?: string;
};

export type NoteSummary = {
  id: number;
  slug: string;
  title: string;
  /** ISO `YYYY-MM-DD`, tal como la guarda el CMS. */
  fecha: string;
  bajada: string;
  portada: ApiImage | null;
};

export type Note = NoteSummary & { cuerpo: string };

/** La misma nota en otro idioma: su idioma y su slug, que no se repite. */
export type NoteTranslation = { locale: Locale; slug: string };

/** La fecha de publicación, escrita en el idioma de la nota.
 *
 * En UTC a propósito: el CMS guarda un `DateField` sin hora, o sea una fecha
 * civil, y `new Date("2026-07-28")` es la medianoche UTC de ese día.
 * Formatearla en la zona del servidor —que en producción no es la del lector—
 * la corre al día anterior en cualquier huso al oeste de Greenwich. Pasaba:
 * una nota del 28 de julio se mostraba como 27 de julio.
 */
export function formatNoteDate(locale: Locale, fecha: string, month: "long" | "short" = "long") {
  return new Intl.DateTimeFormat(INTL_LOCALE[locale], {
    day: "numeric",
    month,
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(fecha));
}

async function askCms(query: string): Promise<{ items: ApiNote[] }> {
  const res = await fetch(`${API_URL}/cms/api/v2/pages/?${query}`, {
    next: { revalidate: REVALIDATE_SECONDS },
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`El CMS respondió ${res.status} a "${query}"`);
  // No basta con el status: si `API_URL` apunta a otra cosa —un proxy, un
  // portal de login, otro servicio en el mismo puerto— la respuesta puede ser
  // un 200 con HTML, y `res.json()` falla con "Unexpected token '<'", que no
  // dice nada sobre la causa.
  const tipo = res.headers.get("content-type") ?? "";
  if (!tipo.includes("json")) {
    throw new Error(`El CMS devolvió "${tipo}" en vez de JSON: revisá API_URL`);
  }
  return res.json();
}

function toSummary(note: ApiNote): NoteSummary {
  return {
    id: note.id,
    slug: note.meta.slug,
    title: note.title,
    fecha: note.fecha,
    bajada: note.bajada,
    portada: conUrlAbsoluta(note.portada_tarjeta),
  };
}

/** Las notas publicadas de un idioma, de la más nueva a la más vieja. */
export async function fetchNotes(locale: Locale, limit = MAX_NOTES): Promise<NoteSummary[]> {
  // `type` limita a las notas y la API sólo devuelve páginas publicadas, así
  // que un borrador no se filtra acá.
  const { items } = await askCms(
    `type=cms.NotePage&locale=${locale}&fields=fecha,bajada,portada_tarjeta&order=-fecha&limit=${limit}`,
  );
  return items.map(toSummary);
}

/** Una nota por su slug, o `null` si ese idioma no la tiene. */
export async function fetchNote(locale: Locale, slug: string): Promise<Note | null> {
  const { items } = await askCms(
    `type=cms.NotePage&locale=${locale}&slug=${encodeURIComponent(slug)}` +
      `&fields=fecha,bajada,cuerpo,portada_cabecera&limit=1`,
  );
  const note = items[0];
  if (!note) return null;
  return {
    ...toSummary(note),
    portada: conUrlAbsoluta(note.portada_cabecera),
    // El backend ya expande el formato interno de Wagtail a HTML usable
    // (`RichTextAPIField` en `cms/models.py`); acá llega listo para pintar.
    cuerpo: note.cuerpo ?? "",
  };
}

/** Las versiones publicadas de una nota en los otros idiomas.
 *
 * Es lo que sostiene el `hreflang` del detalle: sin esto cada traducción sería,
 * para un buscador, un artículo distinto que compite con los otros en vez de la
 * misma nota en otro idioma.
 *
 * Devuelve sólo las publicadas —la API no expone borradores—, así que una nota
 * traducida pero sin publicar no se declara, que es lo correcto: apuntar a una
 * URL que todavía da 404 es peor que no declararla.
 */
export async function fetchTranslations(id: number): Promise<NoteTranslation[]> {
  const { items } = await askCms(`type=cms.NotePage&translation_of=${id}&fields=fecha&limit=20`);
  return items
    .map((item) => ({ locale: item.meta.locale, slug: item.meta.slug }))
    .filter((t): t is NoteTranslation => !!t.locale && isLocale(t.locale));
}

/** Como `fetchTranslations`, pero sin tirar la página si el CMS falla.
 *
 * El `hreflang` es una mejora, no la página: si el CMS no contesta al pedir las
 * traducciones, es preferible servir la nota sin esa declaración que devolver
 * un error por algo accesorio. */
export async function fetchTranslationsOrNone(id: number): Promise<NoteTranslation[]> {
  try {
    return await fetchTranslations(id);
  } catch {
    return [];
  }
}

/** Como `fetchNotes`, pero un CMS caído no tira abajo el build del sitemap. */
export async function fetchNotesOrNone(locale: Locale, limit = MAX_NOTES): Promise<NoteSummary[]> {
  try {
    return await fetchNotes(locale, limit);
  } catch {
    return [];
  }
}
