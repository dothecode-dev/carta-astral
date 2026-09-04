import { NextResponse } from "next/server";

import { destinoSeguro } from "@/lib/destino";
import { DEFAULT_LOCALE, isLocale } from "@/lib/i18n";
import { clearSessionToken } from "@/lib/session";

// Salida de emergencia para una cookie que el backend ya no reconoce.
//
// Las páginas con sesión no pueden borrar la cookie ellas mismas (un Server
// Component lee cookies, no las escribe), así que mandan acá: se borra y se
// sigue viaje al login. Sin este paso la cookie muerta sobrevive y /entrar
// devuelve al usuario a la página protegida, que vuelve a rechazarlo.

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  // El locale sale de una lista cerrada, nunca del parámetro tal cual: armar
  // el destino con lo que venga en la URL sería un redirect abierto servido
  // desde nuestro propio dominio.
  const params = new URL(request.url).searchParams;
  const pedido = params.get("locale") ?? "";
  const locale = isLocale(pedido) ? pedido : DEFAULT_LOCALE;

  // A dónde volvía y qué estaba por comprar. Sin esto, a quien se le vence la
  // sesión mirando /precios lo mandábamos al login y ahí terminaba el camino:
  // la compra se perdía, que es el mismo agujero que `next` vino a tapar en
  // /entrar. Se valida con la misma lista cerrada, por la misma razón —este
  // Location se arma con lo que venga en la URL—.
  const destino = destinoSeguro(params.get("next"), locale);
  const producto = params.get("comprar");
  const compra = destino && producto && /^[a-z0-9_]{1,40}$/.test(producto) ? producto : null;
  const query = destino
    ? `?next=${encodeURIComponent(destino)}${compra ? `&comprar=${encodeURIComponent(compra)}` : ""}`
    : "";

  await clearSessionToken();

  // Location relativo a propósito. `NextResponse.redirect` exige una URL
  // absoluta y la única base a mano es `request.url`, que detrás del proxy es
  // la interna del contenedor: en producción eso mandaba al navegador a
  // https://0.0.0.0:3000/es/entrar, un host que no existe. El destino relativo
  // lo resuelve el navegador contra el dominio por el que entró.
  return new NextResponse(null, {
    status: 307,
    headers: { Location: `/${locale}/entrar${query}` },
  });
}
