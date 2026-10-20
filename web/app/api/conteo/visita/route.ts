import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";

// Cada página que se abre (`CapturaProcedencia`), al contador del servidor:
// visitas por día, país, sección y canal, sin cookies ni nada de quién fue
// (backend/api/conteo_api.py). El país lo saca el backend de la IP que
// `callApi` reenvía, y no la guarda. Público: no manda sesión aunque haya una.

export const dynamic = "force-dynamic";

// Los rastreadores que ejecutan JavaScript (Googlebot, el bot de anuncios de
// Google, Bing, navegadores sin pantalla) contarían cada página que recorren
// como una visita. Sin user-agent tampoco es una persona con un navegador.
// No alcanza con buscar «bot»: hay teléfonos que lo llevan en el nombre
// (CUBOT). Los bots firman con «…bot/versión», «…bot;» o una URL «+http…».
const BOT = /bot\/|bot;|bot\)|bot-|\+https?:|crawler|spider|slurp|headless|lighthouse|curl\/|wget\/|python|java\//i;

export async function POST(request: Request) {
  const agente = request.headers.get("user-agent") ?? "";
  if (!agente || BOT.test(agente)) return new NextResponse(null, { status: 204 });
  let cuerpo: Record<string, unknown>;
  try {
    cuerpo = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }
  try {
    await callApi("/api/conteo/visita/", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ seccion: cuerpo.seccion, procedencia: cuerpo.procedencia }),
    });
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    if (status === 400 || status === 429) return new NextResponse(null, { status });
    // Un número perdido no rompe nada, pero que no se pierdan todos callados.
    console.error(`conteo visita: backend ${status}`);
    return new NextResponse(null, { status: 502 });
  }
}
