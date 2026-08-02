import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";

// Genera la lectura de una carta. Es la única llamada de la web que gasta un
// crédito: el descuento lo hace el backend, nunca el navegador.

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  let body: { lang?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  try {
    const data = await callApi(`/api/charts/${id}/interpretation/`, {
      method: "POST",
      body: JSON.stringify({ lang: body.lang }),
    });
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) return NextResponse.json({ error: "sin sesión" }, { status: 401 });
      // El backend responde 402 cuando no alcanzan los créditos.
      if (error.status === 402) return NextResponse.json({ error: "sin créditos" }, { status: 402 });
      if (error.status === 404) return NextResponse.json({ error: "no existe" }, { status: 404 });
      if (error.status === 429) {
        return NextResponse.json({ error: "demasiadas lecturas" }, { status: 429 });
      }
    }
    return NextResponse.json({ error: "no pudimos generar la lectura" }, { status: 502 });
  }
}
