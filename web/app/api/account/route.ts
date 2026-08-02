import { NextResponse } from "next/server";

import { ApiError, callApi, clearSessionToken } from "@/lib/session";

// Borra la cuenta entera. Después del borrado la cookie se limpia acá mismo:
// dejarla viva apuntaría a una cuenta que ya no existe y la próxima pantalla
// fallaría con un 401 confuso.

export const dynamic = "force-dynamic";

export async function DELETE() {
  try {
    await callApi("/api/account/", { method: "DELETE" });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      // Ya no había sesión: el resultado buscado igual se cumple.
      await clearSessionToken();
      return NextResponse.json({ ok: true });
    }
    return NextResponse.json({ error: "no pudimos borrar tu cuenta" }, { status: 502 });
  }

  await clearSessionToken();
  return NextResponse.json({ ok: true });
}
