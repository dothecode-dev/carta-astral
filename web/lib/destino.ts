import { normalizarCupon } from "./cupon";
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

/** Forma de un código de producto en la URL: la misma regla que `/entrar`
 *  exige en su query `comprar` (Ruling 19 no la afloja, la reusa). Vive acá
 *  porque `destinoInternoSeguro` la necesita para revalidar el extra que
 *  vuelve pegado al destino — un solo lugar define el criterio, para que
 *  `/entrar` y el canje por mail nunca puedan divergir sobre qué es válido. */
const PRODUCTO = /^[a-z0-9_]{1,40}$/;

export function productoValido(comprar: unknown): comprar is string {
  return typeof comprar === "string" && PRODUCTO.test(comprar);
}

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
 * destino nace en `/entrar`, donde `destinoSeguro` ya lo validó contra `next`
 * y `?comprar=`/`?cupon=` se validaron aparte (RF16 — quien apretó "Comprar"
 * antes de loguearse), y vuelve en la respuesta del canje porque en iOS la
 * persona sale a Mail y vuelve por otra pestaña, donde ni ese `next` ni esos
 * extras siguen en la URL. En el camino feliz el path siempre está en la
 * lista cerrada de `RUTAS` — si lo que vuelve NO está, es porque el backend
 * cambió o alguien lo manipuló, y en los dos casos toca descartarlo: aceptar
 * cualquier path con forma de interno sería aceptar más de lo que la propia
 * puerta de entrada acepta, un agujero y no una tolerancia.
 *
 * El `?` ya no descarta todo el destino (antes lo hacía, vía `destinoSeguro`
 * sobre la cadena completa): se separa el path de la query, el path se valida
 * exactamente igual que siempre, y sólo dos claves de la query sobreviven —
 * `comprar` y `cupon`, cada una con la misma forma que ya exige `/entrar`
 * (`productoValido`, `normalizarCupon`) — porque son las que arma esa misma
 * pantalla al mandar hacia acá. Cualquier otra clave, o una de estas dos con
 * forma inválida, tira todo el destino: no hay manera de saber si lo que
 * sobra es inocuo, y la respuesta ante la duda es la misma que antes, "".
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
  // Un `#` no tiene nada que hacer acá en ningún lado de la cadena — mismo
  // motivo que en `destinoSeguro`.
  if (destino.includes("#")) return "";

  // `indexOf`, no `split("?")`: sólo el primer `?` abre la query. Un segundo
  // `?` es un carácter literal de esa misma query (así lo trata una URL de
  // verdad), y `split` lo hubiera cortado aparte y descartado en silencio.
  const separador = destino.indexOf("?");
  const ruta = separador === -1 ? destino : destino.slice(0, separador);
  const query = separador === -1 ? "" : destino.slice(separador + 1);
  const locale = ruta.split("/")[1];
  if (!isLocale(locale)) return "";

  const path = destinoSeguro(ruta, locale);
  if (!path) return "";
  if (!query) return path;

  let params: URLSearchParams;
  try {
    params = new URLSearchParams(query);
  } catch {
    return "";
  }

  const claves = new Set(params.keys());
  claves.delete("comprar");
  claves.delete("cupon");
  if (claves.size > 0) return "";

  const extras: string[] = [];

  const comprar = params.get("comprar");
  if (comprar !== null) {
    if (!productoValido(comprar)) return "";
    extras.push(`comprar=${encodeURIComponent(comprar)}`);
  }

  const cupon = params.get("cupon");
  if (cupon !== null) {
    const cuponNormal = normalizarCupon(cupon);
    if (!cuponNormal) return "";
    extras.push(`cupon=${encodeURIComponent(cuponNormal)}`);
  }

  return extras.length ? `${path}?${extras.join("&")}` : path;
}
