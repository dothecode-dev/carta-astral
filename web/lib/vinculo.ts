import { API_URL } from "./config";
import type { CartaDibujable } from "./chart";
import { SYNASTRY_SLUG, isLocale, type Locale } from "./i18n";

// Vínculo, fase 1: la vista previa pública. La web no tiene flag propio: le
// pregunta al backend, que es la única fuente de verdad (un flag en las dos
// puntas termina con una encendida y la otra no).
//
// EXCEPCIÓN a `rutasApiSinFetchDirecto.test.ts`: `vinculoActivo` no pasa por
// `callApi`. Mismo motivo que `catalogo.ts` y `sky.ts` —`callApi` fuerza
// `cache: "no-store"` y llama a `headers()`, y `app/sitemap.ts` también lo
// consulta, en un contexto de build sin pedido: forzar `headers()` ahí
// convertiría `/sitemap.xml` de estático a dinámico—. Y acá tampoco hay techo
// que proteger: `VinculoEstadoView` (`backend/api/vinculo.py`) no declara
// `throttle_classes`, así que reenviar `x-forwarded-for` no cambiaría nada.
//
// Consecuencia a tener presente: el resultado se cachea 5 minutos, y vale para
// encender y para apagar. Un cambio del flag en el backend tarda hasta ese
// tiempo en verse en la web, más un pedido (la caché sirve el valor viejo una
// vez mientras lo renueva).

const REVALIDATE_SECONDS = 300;
const TIMEOUT_MS = 3000;

export type TipoVinculo = "pareja" | "trabajo" | "familia" | "amistad";
export const TIPOS_VINCULO: TipoVinculo[] = ["pareja", "trabajo", "familia", "amistad"];

export type AspectoPreview = {
  p_a: string;
  p_b: string;
  aspecto: string;
  orbe: number;
  frase: string;
};

/** Las dos cartas llegan como `CartaDibujable` y no como `ApiChart`: la vista
 *  previa no guarda nada, así que no tienen id ni interpretaciones. */
export type VinculoPreview = {
  a: CartaDibujable;
  b: CartaDibujable;
  aspectos: AspectoPreview[];
};

export type MotivoFallo = "misma_persona" | "datos_invalidos" | "demasiadas" | "no_disponible";

/** ¿Está encendida la vista previa? Ante cualquier duda, no: una landing que
 *  no puede confirmar el flag no se muestra ni va al sitemap.
 *
 *  El backend responde 200 con `{"preview": true|false}` y no 404 para
 *  «apagado» (`VinculoEstadoView`). Importa: el caché de datos de Next sólo
 *  guarda las respuestas 200, así que con un 404 el «encendido» viejo seguía
 *  vigente para siempre y apagar el flag no apagaba la landing. */
export async function vinculoActivo(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/api/vinculo/`, {
      next: { revalidate: REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) return false;
    const cuerpo: unknown = await res.json();
    return (cuerpo as { preview?: unknown } | null)?.preview === true;
  } catch {
    // Sin log a propósito: el server de Next lo registra igual y esto corre en
    // cada revalidación. Lo que importa es que la página no se caiga.
    return false;
  }
}

/** El idioma de la ruta, o `null` si no corresponde a ese slug:
 *  `/en/sinastria` existe como carpeta, pero no es una página. */
export function localeDelVinculo(segmento: string, slug: string): Locale | null {
  return isLocale(segmento) && SYNASTRY_SLUG[segmento] === slug ? segmento : null;
}
