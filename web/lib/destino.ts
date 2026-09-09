import { isLocale, type Locale } from "./i18n";

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

/**
 * Revalida un destino que ya pasó una vez por acá.
 *
 * Lo usa el canje del código de acceso por mail (`/api/session`, RF16): el
 * destino nace en `/entrar`, donde `destinoSeguro` ya lo validó contra `next`,
 * y vuelve en la respuesta del canje porque en iOS la persona sale a Mail y
 * vuelve por otra pestaña, donde ese `next` original ya no existe. En el
 * camino feliz siempre está en la lista cerrada de `RUTAS` — si lo que vuelve
 * NO está, es porque el backend cambió o alguien lo manipuló, y en los dos
 * casos toca descartarlo: aceptar cualquier path con forma de interno sería
 * aceptar más de lo que la propia puerta de entrada acepta, un agujero y no
 * una tolerancia.
 *
 * El locale no lo tiene quien llama —no hay locale en el pedido de canje—,
 * así que se lo extrae del propio destino: `destinoSeguro` ya exige que
 * empiece con `/<locale>/`, así que el primer segmento tiene que ser uno de
 * los locales soportados o el destino no es válido de entrada.
 *
 * Devuelve string vacía en vez de `null`: quien llama a esto la usa para
 * decidir si agrega la clave `destino` a un JSON, no para bifurcar un flujo.
 */
export function destinoInternoSeguro(destino: unknown): string {
  if (typeof destino !== "string" || !destino) return "";
  const locale = destino.split("/")[1];
  if (!isLocale(locale)) return "";
  return destinoSeguro(destino, locale) ?? "";
}
