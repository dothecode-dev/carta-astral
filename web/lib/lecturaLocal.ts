import type { CartaDibujable } from "@/lib/chart";
import type { Locale } from "@/lib/i18n";

// La copia de la lectura breve sin cuenta que vive 24 h EN ESTE NAVEGADOR
// (spec 2026-10-08, RF5): el servidor la borra cuando la entrega. Todo en
// try/catch: Safari privado y el storage bloqueado tiran al tocarlo.
const CLAVE = "astra-lectura-anonima";
const VIDA_MS = 24 * 60 * 60 * 1000;

export type LecturaGuardada = {
  carta: CartaDibujable;
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

export function leerLectura(ahora = Date.now()): LecturaGuardada | null {
  try {
    const crudo = localStorage.getItem(CLAVE);
    if (!crudo) return null;
    const l = JSON.parse(crudo) as LecturaGuardada;
    if (typeof l?.vence !== "number" || l.vence < ahora || typeof l.texto !== "string") {
      localStorage.removeItem(CLAVE);
      return null;
    }
    return l;
  } catch {
    return null;
  }
}
