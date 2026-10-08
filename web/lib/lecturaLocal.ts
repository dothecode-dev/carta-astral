import type { CartaDibujable } from "@/lib/chart";
import type { DatosCarta } from "@/lib/datosCarta";
import { isLocale, type Locale } from "@/lib/i18n";

// La copia de la lectura breve sin cuenta que vive 24 h EN ESTE NAVEGADOR
// (spec 2026-10-08, RF5): el servidor la borra cuando la entrega. Todo en
// try/catch: Safari privado y el storage bloqueado tiran al tocarlo.
//
// Junto con la lectura se guardan la carta Y los datos con que se calculó
// (`datos`, los de nacimiento): así, al reabrirla, el botón de comprar el
// informe sigue funcionando. Es decisión de producto del 08-10: queda sólo en
// este navegador, 24 h, y nunca viaja al servidor para guardarse.
const CLAVE = "astra-lectura-anonima";
const VIDA_MS = 24 * 60 * 60 * 1000;

export type LecturaGuardada = {
  carta: CartaDibujable;
  datos: DatosCarta;
  texto: string;
  lang: Locale;
  disclaimer: string;
  vence: number;
};

export function guardarLectura(l: Omit<LecturaGuardada, "vence">, ahora = Date.now()): void {
  try {
    localStorage.setItem(CLAVE, JSON.stringify({ ...l, vence: ahora + VIDA_MS }));
  } catch {
    // Sin storage se ve igual; sólo no sobrevive a recargar.
  }
}

const esObjeto = (x: unknown): x is Record<string, unknown> =>
  typeof x === "object" && x !== null && !Array.isArray(x);

/** Lo que se lee del storage es entrada no confiable (otra versión, otra
 *  pestaña, a mano): se chequea la forma antes de dejar que llegue a la UI. */
function esValida(l: unknown): l is LecturaGuardada {
  return (
    esObjeto(l) &&
    typeof l.vence === "number" &&
    typeof l.texto === "string" &&
    typeof l.disclaimer === "string" &&
    typeof l.lang === "string" &&
    isLocale(l.lang) &&
    esObjeto(l.carta) &&
    esObjeto(l.datos)
  );
}

export function leerLectura(ahora = Date.now()): LecturaGuardada | null {
  try {
    const crudo = localStorage.getItem(CLAVE);
    if (!crudo) return null;
    const l = JSON.parse(crudo) as LecturaGuardada;
    if (!esValida(l) || l.vence < ahora) {
      localStorage.removeItem(CLAVE);
      return null;
    }
    return l;
  } catch {
    return null;
  }
}
