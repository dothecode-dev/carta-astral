import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";
import { noExiste, uuidValido } from "@/lib/uuid";

// Cambia cómo quiere la persona que le hablemos (el trato de la carta). Vale
// para lo que se escriba o traduzca de ahí en adelante: lo ya escrito no se
// toca. La sesión sale de la cookie, nunca del cuerpo.

export const dynamic = "force-dynamic";

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!uuidValido(id)) return noExiste();

  let body: { trato?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  try {
    const chart = await callApi(`/api/charts/${id}/`, {
      method: "PATCH",
      body: JSON.stringify({ trato: body.trato }),
    });
    return NextResponse.json(chart);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) return NextResponse.json({ error: "sin sesión" }, { status: 401 });
      if (error.status === 404) return NextResponse.json({ error: "no existe" }, { status: 404 });
      if (error.status === 400) return NextResponse.json({ error: "trato inválido" }, { status: 400 });
      console.error(`trato ${id}: backend ${error.status} ${error.body}`);
    } else {
      console.error(`trato ${id}:`, error);
    }
    return NextResponse.json({ error: "no pudimos guardarlo" }, { status: 502 });
  }
}
