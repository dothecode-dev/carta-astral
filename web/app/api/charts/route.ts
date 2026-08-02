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
