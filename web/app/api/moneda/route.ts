import { NextResponse } from "next/server";

import { normalizarCupon } from "@/lib/cupon";
import { COOKIE_MONEDA, esMoneda } from "@/lib/moneda";

// El selector de moneda de /precios (RF24). Un formulario común, sin JS: guarda
// la elección en una cookie y vuelve a la página. Las páginas con precio la leen
// (`monedaDelVisitante`) y mandan esa misma moneda al checkout.

export const dynamic = "force-dynamic";

const UN_ANIO = 60 * 60 * 24 * 365;

/** Sólo un path del sitio: empieza con una barra, no con dos, sin barra
 * invertida ni query. Cualquier otra cosa vuelve a `/` (sin open redirect). */
function destinoInterno(volver: FormDataEntryValue | null): string {
  if (typeof volver !== "string") return "/";
  return /^\/(?!\/)[A-Za-z0-9/_-]*$/.test(volver) ? volver : "/";
}

export async function POST(request: Request) {
  let datos: FormData;
  try {
    datos = await request.formData();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }
  const moneda = datos.get("moneda");
  if (!esMoneda(moneda)) {
    return NextResponse.json({ error: "moneda inválida" }, { status: 400 });
  }

  // Location relativo a propósito, como `session/expirada`: detrás del proxy
  // `request.url` es la URL interna del contenedor.
  // El cupón de la página viaja aparte y vuelve sólo con forma de cupón: sin
  // esto, cambiar de moneda en /precios?cupon=X lo perdía y se pagaba de lista.
  const cupon = normalizarCupon(datos.get("cupon"));
  const destino = destinoInterno(datos.get("volver"));
  const location = cupon ? `${destino}?cupon=${encodeURIComponent(cupon)}` : destino;
  const res = new NextResponse(null, { status: 303, headers: { Location: location } });
  res.cookies.set(COOKIE_MONEDA, moneda, {
    path: "/",
    maxAge: UN_ANIO,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
  });
  return res;
}
