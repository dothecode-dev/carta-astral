import { NextResponse } from "next/server";

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
  const pedido = new URL(request.url).searchParams.get("locale") ?? "";
  const locale = isLocale(pedido) ? pedido : DEFAULT_LOCALE;

  await clearSessionToken();

  return NextResponse.redirect(new URL(`/${locale}/entrar`, request.url));
}
