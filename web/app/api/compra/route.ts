import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";

// En qué quedó una compra: lo sondea la página de retorno de Stripe mientras
// espera que llegue el webhook que acredita. Sin este proxy, el fetch del
// cliente iría directo al backend, que no tiene CORS abierto (el token de
// sesión vive en una cookie httpOnly que sólo este servidor puede leer).

export const dynamic = "force-dynamic";

type Estado = {
  estado: "pendiente" | "acreditado";
  destino?: { tipo: "carta"; id: string } | { tipo: "cuenta" };
};

export async function GET(request: Request) {
  const checkoutId = new URL(request.url).searchParams.get("checkout_id");
  if (!checkoutId) {
    return NextResponse.json({ error: "falta el checkout" }, { status: 400 });
  }

  try {
    return NextResponse.json(await callApi<Estado>(`/api/checkout/${checkoutId}/`));
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    // 404 es "ese checkout no existe o es de otra cuenta": no hay nada que
    // registrar. El resto sí, porque del otro lado hay alguien que ya pagó.
    if (status !== 404) console.error(`estado de la compra: backend ${status}`);
    if (status === 401) return NextResponse.json({ error: "sin sesión" }, { status: 401 });
    if (status === 404) return NextResponse.json({ error: "no existe" }, { status: 404 });
    return NextResponse.json({ error: "no pudimos consultar la compra" }, { status: 502 });
  }
}
