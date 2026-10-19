import { NextResponse } from "next/server";

import { ApiError, callApi, motivoDe } from "@/lib/session";

// El botón de arrepentimiento (Res. SCI 424/2020). Público: sin sesión, aunque
// el navegador tenga una. Al backend viajan sólo los tres campos del
// formulario; el código que devuelve es lo que la pantalla muestra.

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let cuerpo: Record<string, unknown>;
  try {
    cuerpo = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ motivo: "email_invalido" }, { status: 400 });
  }
  try {
    const data = await callApi<{ codigo: string }>("/api/arrepentimiento/", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ email: cuerpo.email, numero_compra: cuerpo.numero_compra, locale: cuerpo.locale }),
    });
    return NextResponse.json({ codigo: data.codigo }, { status: 201 });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    if (status === 400 && motivoDe(error) === "email_invalido") {
      return NextResponse.json({ motivo: "email_invalido" }, { status: 400 });
    }
    if (status === 429) return NextResponse.json({ motivo: "demasiados" }, { status: 429 });
    // Un pedido de revocación que no se pudo registrar: tiene que dejar rastro.
    console.error(`arrepentimiento: backend ${status}`);
    return NextResponse.json({ motivo: "fallo" }, { status: 502 });
  }
}
