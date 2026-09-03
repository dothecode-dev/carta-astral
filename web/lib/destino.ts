import type { Locale } from "./i18n";

/**
 * A dónde volver después de entrar.
 *
 * El login siempre terminaba en /cuenta, sin importar de dónde venía la
 * persona: quien hacía clic en "Comprar" en /precios aterrizaba en una cuenta
 * vacía, sin la compra que había pedido y sin nada que se la recordara. Volver
 * al lugar de origen es lo que arregla eso, y `next` es cómo viaja ese lugar.
 *
 * Viaja por la query, así que lo escribe cualquiera. Un `next` que se usara tal
 * cual convertiría al sitio en trampolín: alguien acaba de autenticarse, confía
 * en la pantalla, y termina en un dominio ajeno. Por eso acá no se sanea la
 * cadena que llega —se la compara contra la lista de las que pueden llegar—, y
 * lo que no está en la lista no vuelve corregido, vuelve `null`.
 */
const RUTAS = ["precios", "nueva", "cuenta"] as const;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function destinoSeguro(next: unknown, locale: Locale): string | null {
  if (typeof next !== "string" || next === "") return null;
  // Un `?` o un `#` no aportan nada a un destino de esta lista y sí agrandan lo
  // que hay que razonar; el resto son las formas conocidas de escaparse del
  // sitio sin escribir un esquema.
  if (/[?#\\]/.test(next)) return null;
  if (!next.startsWith(`/${locale}/`)) return null;
  if (next.startsWith("//")) return null;

  const resto = next.slice(`/${locale}/`.length);
  if (RUTAS.includes(resto as (typeof RUTAS)[number])) return next;

  const carta = resto.match(/^carta\/(.+)$/);
  if (carta && UUID.test(carta[1])) return next;

  return null;
}
