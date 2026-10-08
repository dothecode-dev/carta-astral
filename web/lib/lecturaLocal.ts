import type { CartaDibujable } from "@/lib/chart";
import type { DatosCarta } from "@/lib/datosCarta";
import { isLocale, type Locale } from "@/lib/i18n";

// La copia de la lectura breve sin cuenta que vive 24 h EN ESTE NAVEGADOR
// (spec 2026-10-08, RF5): el servidor la borra cuando la web acusa que la
// guardó (§11 v3) o a los 15 min. Todo en
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
  /** El pedido que la trajo: otra pestaña que esperaba el mismo la reconoce
   *  acá cuando el servidor ya la entregó. Falta en las guardadas antes. */
  pedido?: string;
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

// El pedido EN CURSO (spec §11 v3, RF5/RF8): al pedir se guarda acá con su
// carta y sus datos, así una recarga o una pestaña nueva retoma la espera de
// fondo y guarda la lectura con la carta con que se pidió. Vive lo mismo que la
// lectura sin acusar en el servidor (15 min) y se borra apenas termina: lista
// (guardada y acusada), fallida o corte.
const CLAVE_PEDIDO = "astra-lectura-pedido";
const VIDA_PEDIDO_MS = 15 * 60 * 1000;
const UUID = /^[0-9a-f-]{36}$/;

export type PedidoEnCurso = {
  pedido: string;
  carta: CartaDibujable;
  datos: DatosCarta;
  vence: number;
};

export function guardarPedido(p: Omit<PedidoEnCurso, "vence">, ahora = Date.now()): void {
  try {
    localStorage.setItem(CLAVE_PEDIDO, JSON.stringify({ ...p, vence: ahora + VIDA_PEDIDO_MS }));
  } catch {
    // Sin storage la espera sigue igual; sólo no sobrevive a recargar.
  }
}

function esPedidoValido(p: unknown): p is PedidoEnCurso {
  return (
    esObjeto(p) &&
    typeof p.pedido === "string" &&
    UUID.test(p.pedido) &&
    typeof p.vence === "number" &&
    esObjeto(p.carta) &&
    esObjeto(p.datos)
  );
}

function quitarPedido(): void {
  try {
    localStorage.removeItem(CLAVE_PEDIDO);
  } catch {
    // Storage bloqueado: no hay nada que borrar.
  }
}

export function leerPedido(ahora = Date.now()): PedidoEnCurso | null {
  try {
    const crudo = localStorage.getItem(CLAVE_PEDIDO);
    if (!crudo) return null;
    const p = JSON.parse(crudo) as unknown;
    if (!esPedidoValido(p) || p.vence < ahora) {
      quitarPedido();
      return null;
    }
    return p;
  } catch {
    quitarPedido();
    return null;
  }
}

/** Borra el pedido en curso sólo si es ÉSTE: el de otra carta sigue. */
export function borrarPedido(pedido: string): void {
  try {
    const crudo = localStorage.getItem(CLAVE_PEDIDO);
    if (!crudo) return;
    const p = JSON.parse(crudo) as { pedido?: unknown };
    if (p?.pedido !== pedido) return;
  } catch {
    // Ilegible: no se sabe de quién es, y leerPedido la limpia.
    return;
  }
  quitarPedido();
}
