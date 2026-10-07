import { NextResponse } from "next/server";

import { nombre, opciones } from "@/lib/compraCookie";
import { ApiError, callApi, motivoDe } from "@/lib/session";

// Abre el pago de quien todavía no tiene cuenta (RF1, RF2 de «pagar es
// entrar»). Del navegador viajan los datos de nacimiento —los mismos que la
// vista previa—, el idioma y el cupón si hay; el precio lo pone el backend.
//
// `auth: false`: esta compra no es de ninguna sesión, aunque el navegador
// tenga una abierta. Quien tiene sesión compra por `/api/checkout`.
//
// El backend devuelve el nonce de este navegador. Va a una cookie httpOnly
// propia de este checkout y NO al cuerpo: al JS de la página sólo le hace
// falta la URL de Stripe, y un nonce legible desde la página lo podría leer
// cualquier script que corriera en ella. Sin esa cookie, la vuelta del pago
// no abre sesión (RF10, RF11).
//
// La cookie se pone en la respuesta y no con `cookies()`: así viaja en el
// `Set-Cookie` de ESTA respuesta, que es la que el navegador procesa antes de
// irse a Stripe.

export const dynamic = "force-dynamic";

type Abierto = { url?: unknown; checkout_id?: unknown; nonce?: unknown };

export async function POST(request: Request) {
  let cuerpo: unknown;
  try {
    cuerpo = await request.json();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  let data: Abierto;
  try {
    data = await callApi<Abierto>("/api/checkout/anonimo/", {
      method: "POST",
      body: JSON.stringify(cuerpo),
      auth: false,
    });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    if (status === 400) {
      // Cupón (sin cuenta no se admite ninguno: `requiere_cuenta`) o datos
      // de nacimiento inválidos: el motivo es lo único que se reenvía.
      const motivo = motivoDe(error);
      if (motivo) return NextResponse.json({ error: "el cupón no sirve", motivo }, { status: 400 });
      return NextResponse.json({ error: "datos inválidos" }, { status: 400 });
    }
    if (status === 429) {
      return NextResponse.json({ error: "demasiados intentos por ahora" }, { status: 429 });
    }
    // Plata que no se pudo cobrar: se registra. El 503 también (cobro
    // apagado o mantenimiento), pero viaja como tal para que la pantalla lo
    // diga.
    console.error(`checkout anónimo: backend ${status}`);
    if (status === 503) {
      return NextResponse.json({ error: "el cobro no está disponible" }, { status: 503 });
    }
    return NextResponse.json({ error: "no pudimos abrir el pago" }, { status: 502 });
  }

  const cookie = nombre(data.checkout_id);
  if (typeof data.url !== "string" || !cookie || typeof data.nonce !== "string" || !data.nonce) {
    // Mandarlo a pagar sin la cookie sería cobrarle y después no poder
    // dejarlo entrar: mejor no abrir el pago.
    console.error("checkout anónimo: respuesta del backend sin url, checkout_id o nonce válidos");
    return NextResponse.json({ error: "no pudimos abrir el pago" }, { status: 502 });
  }

  const res = NextResponse.json({ url: data.url });
  res.cookies.set(cookie, data.nonce, opciones());
  return res;
}
