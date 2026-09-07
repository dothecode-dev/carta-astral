import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";

// Abre el pago del producto elegido. Del navegador viaja QUÉ se compra y, si se
// compra desde una carta, cuál — nunca el precio: eso lo pone el catálogo del
// backend y lo vuelve a validar el webhook contra la sesión de Stripe.

export const dynamic = "force-dynamic";

function motivoDe(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  try {
    const cuerpo = JSON.parse(error.body) as { motivo?: unknown };
    return typeof cuerpo.motivo === "string" && /^[a-z_]{1,40}$/.test(cuerpo.motivo) ? cuerpo.motivo : null;
  } catch {
    return null;
  }
}

export async function POST(request: Request) {
  let cuerpo: { producto?: string; chart_id?: string; locale?: string; cupon?: string } = {};
  try {
    cuerpo = await request.json();
  } catch {
    // Cuerpo ilegible: cae en el 400 de abajo, igual que si faltara el producto.
  }

  if (!cuerpo.producto) {
    return NextResponse.json({ error: "falta el producto" }, { status: 400 });
  }

  try {
    const data = await callApi<{ url: string }>("/api/checkout/", {
      method: "POST",
      // El locale define a qué página vuelve la persona después de pagar.
      // El backend lo valida contra su lista blanca antes de armar la URL.
      body: JSON.stringify({
        producto: cuerpo.producto,
        chart_id: cuerpo.chart_id,
        locale: cuerpo.locale,
        // El backend lo valida y decide el descuento; acá sólo viaja.
        cupon: cuerpo.cupon,
      }),
    });
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    // 401 es "se venció la sesión mientras miraba la página": lo maneja la
    // pantalla, no es una falla que registrar. El resto sí, porque es plata que
    // no se pudo cobrar.
    if (status !== 401) console.error(`checkout de ${cuerpo.producto}: backend ${status}`);
    if (status === 401) return NextResponse.json({ error: "sin sesión" }, { status: 401 });
    if (status === 400) {
      // Con cupón el 400 trae un motivo (`agotado`, `ya_usado`…) que la
      // pantalla traduce: es lo único del cuerpo del backend que se reenvía.
      const motivo = motivoDe(error);
      if (motivo) return NextResponse.json({ error: "el cupón no sirve", motivo }, { status: 400 });
      return NextResponse.json({ error: "producto inválido" }, { status: 400 });
    }
    if (status === 503) {
      return NextResponse.json({ error: "el cobro no está disponible" }, { status: 503 });
    }
    return NextResponse.json({ error: "no pudimos abrir el pago" }, { status: 502 });
  }
}
