import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { nombre } from "@/lib/compraCookie";
import { destinoInternoSeguro } from "@/lib/destino";
import { ApiError, callApi, setSessionToken } from "@/lib/session";

// La vuelta del pago de quien compró sin cuenta (RF10-RF14 de «pagar es
// entrar»). Del navegador viaja sólo el `checkout_id`; el nonce sale de la
// cookie httpOnly de ESE checkout, que puso `/api/checkout/anonimo` al abrir
// el pago. Sin esa cookie no hay canje: el `checkout_id` solo —que queda en el
// historial y se puede compartir— nunca alcanza para entrar.
//
// Lo que vuelve al navegador:
// - `sesion`: el backend abrió sesión en la cuenta que creó la compra. El
//   token va a la cookie de sesión —reemplazando la que hubiera: la compra es
//   de esta persona (RF14)— y nunca al cuerpo. La cookie del nonce se borra:
//   ya se usó.
// - `codigo`: la cuenta ya existía; se le mandó un código a ese mail
//   (enmascarado acá) y hay que entrar con él.
// - `pendiente`: el webhook todavía no acreditó; la pantalla vuelve a preguntar.
// - `invalido`: el backend no reconoce el canje (404 genérico: nonce que no
//   coincide, ya canjeado, más de 24 h…). La cookie del nonce se borra: no
//   va a servir nunca más.
//
// Corre también con el cartel de mantenimiento puesto (RF14b): `/api` está
// fuera del matcher de `proxy.ts`, y el backend no le aplica el mantenimiento.

export const dynamic = "force-dynamic";

type Canje =
  | { estado: "sesion"; token?: unknown; destino?: unknown; account_id?: unknown }
  | { estado: "codigo"; email?: unknown; destino?: unknown }
  | { estado: "pendiente" };

const INVALIDO = { estado: "invalido" } as const;

export async function POST(request: Request) {
  let checkoutId: unknown;
  try {
    checkoutId = ((await request.json()) as { checkout_id?: unknown }).checkout_id;
  } catch {
    // Cuerpo ilegible: es lo mismo que no traer checkout.
  }

  const cookie = nombre(checkoutId);
  if (!cookie) return NextResponse.json(INVALIDO);

  const store = await cookies();
  const nonce = store.get(cookie)?.value;
  if (!nonce) return NextResponse.json(INVALIDO);

  let data: Canje;
  try {
    data = await callApi<Canje>("/api/checkout/anonimo/canjear/", {
      method: "POST",
      body: JSON.stringify({ checkout_id: checkoutId, nonce }),
      auth: false,
    });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    if (status === 404) {
      store.delete(cookie);
      return NextResponse.json(INVALIDO);
    }
    if (status === 429) {
      return NextResponse.json({ error: "demasiados intentos por ahora" }, { status: 429 });
    }
    // Del otro lado hay alguien que ya pagó: se registra.
    console.error(`canje de la compra: backend ${status}`);
    return NextResponse.json({ error: "no pudimos consultar la compra" }, { status: 502 });
  }

  if (data.estado === "pendiente") return NextResponse.json({ estado: "pendiente" });

  if (data.estado === "codigo") {
    return NextResponse.json({
      estado: "codigo",
      email: typeof data.email === "string" ? data.email : "",
      destino: destinoInternoSeguro(data.destino),
    });
  }

  if (data.estado === "sesion" && typeof data.token === "string" && data.token) {
    await setSessionToken(data.token);
    store.delete(cookie);
    return NextResponse.json({
      estado: "sesion",
      // El destino lo arma el backend, pero se revalida contra la misma lista
      // cerrada que `/entrar`: un destino que no está ahí no se sigue.
      destino: destinoInternoSeguro(data.destino),
      ...(typeof data.account_id === "number" ? { account_id: data.account_id } : {}),
    });
  }

  console.error(`canje de la compra: respuesta inesperada del backend (${String(data.estado)})`);
  return NextResponse.json({ error: "no pudimos consultar la compra" }, { status: 502 });
}
