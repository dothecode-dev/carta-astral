import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";

// Borra todas las cartas de quien está navegando. La cuenta y los créditos
// quedan. El backend resuelve de quién son a partir del token de la cookie:
// nunca se acepta un identificador de cuenta que venga del navegador.

export const dynamic = "force-dynamic";

export async function DELETE() {
  try {
    await callApi("/api/charts/", { method: "DELETE" });
    return NextResponse.json({ ok: true });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return NextResponse.json({ error: "sin sesión" }, { status: 401 });
    }
    return NextResponse.json({ error: "no pudimos borrar tus cartas" }, { status: 502 });
  }
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  try {
    const chart = await callApi("/api/charts/", {
      method: "POST",
      body: JSON.stringify(body),
    });
    return NextResponse.json(chart, { status: 201 });
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) {
        return NextResponse.json({ error: "sin sesión" }, { status: 401 });
      }
      if (error.status === 400) {
        // Datos que el backend rechaza: fecha imposible, lugar sin huso, etc.
        return NextResponse.json({ error: "datos inválidos" }, { status: 400 });
      }
      if (error.status === 429) {
        return NextResponse.json({ error: "demasiadas cartas por hoy" }, { status: 429 });
      }
    }
    return NextResponse.json({ error: "no pudimos calcular la carta" }, { status: 502 });
  }
}
