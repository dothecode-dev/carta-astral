// La cookie que prueba que este navegador es el que abrió un pago sin cuenta
// (RF2 de «pagar es entrar»).
//
// Guarda el nonce que devuelve `POST /api/checkout/anonimo/` del backend: sin
// él, el `checkout_id` de la URL de vuelta —que queda en el historial y se
// puede compartir— no alcanza para entrar. Una cookie por checkout, con el id
// en el nombre, para que un doble clic en «Comprar» no pise el nonce del
// primer pago con el del segundo.
//
// httpOnly: el nonce nunca llega al JS de la página. Lo ponen y lo leen las
// rutas del servidor (`app/api/checkout/anonimo`, `app/api/compra/canjear`).
//
// Sin imports de `next/headers` a propósito: lo usan una página, dos rutas y
// los tests, y así no arrastra nada.

const PREFIJO = "astra_compra_";

/** La forma de un id de Checkout Session de Stripe (`cs_test_…`, `cs_live_…`).
 *  El id llega por la URL, así que se valida antes de volverlo nombre de cookie:
 *  un `;` o un `=` ahí sería escribir otra cookie. */
const CHECKOUT_ID = /^cs_[A-Za-z0-9_]{1,200}$/;

/** Un día, como el canje del backend: pasadas 24 h desde la acreditación ya
 *  no responde nada, así que una cookie más larga sólo ocuparía lugar. */
const MAX_AGE_SECONDS = 24 * 60 * 60;

export function checkoutIdValido(checkoutId: unknown): checkoutId is string {
  return typeof checkoutId === "string" && CHECKOUT_ID.test(checkoutId);
}

/** El nombre de la cookie del nonce de ese checkout, o `null` si el id no
 *  tiene forma de checkout de Stripe. */
export function nombre(checkoutId: unknown): string | null {
  return checkoutIdValido(checkoutId) ? `${PREFIJO}${checkoutId}` : null;
}

export function opciones() {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    // En desarrollo el sitio va por http: con Secure el navegador la descarta.
    secure: process.env.NODE_ENV === "production",
    maxAge: MAX_AGE_SECONDS,
    path: "/",
  };
}

/** El número de compra que la persona le dicta a soporte (RF12): el final
 *  del `checkout_id`, que es lo que lo distingue —el principio es el mismo
 *  `cs_live_` para todos—. Diez caracteres alcanzan para encontrarlo y no
 *  hacen sentir que se le pide copiar un hash entero. */
export function abreviar(checkoutId: string): string {
  return checkoutId.slice(-10);
}
