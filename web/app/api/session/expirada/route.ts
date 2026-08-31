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

  // Location relativo a propósito. `NextResponse.redirect` exige una URL
  // absoluta y la única base a mano es `request.url`, que detrás del proxy es
  // la interna del contenedor: en producción eso mandaba al navegador a
  // https://0.0.0.0:3000/es/entrar, un host que no existe. El destino relativo
  // lo resuelve el navegador contra el dominio por el que entró.
  return new NextResponse(null, { status: 307, headers: { Location: `/${locale}/entrar` } });
}
