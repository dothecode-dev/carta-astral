import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";

// Los pasos de quien calculó su carta sin cuenta (`CartaPreview`), al contador
// del servidor: un número por día y evento, sin cookies ni nada de quién fue
// (backend/api/conteo_api.py). Público: no manda sesión aunque haya una. Al
// backend viajan sólo esos campos (paso, moneda mostrada y procedencia); las
// listas cerradas las valida él.

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let cuerpo: Record<string, unknown>;
  try {
    cuerpo = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }
  try {
    await callApi("/api/conteo/teaser/", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ evento: cuerpo.evento, moneda: cuerpo.moneda, procedencia: cuerpo.procedencia }),
    });
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    if (status === 400 || status === 429) return new NextResponse(null, { status });
    // Un número perdido no rompe nada, pero que no se pierdan todos callados.
    console.error(`conteo teaser: backend ${status}`);
    return new NextResponse(null, { status: 502 });
  }
}
