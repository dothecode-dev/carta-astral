import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";

// Cuántas de las ocho secciones del informe ya están escritas (RF7/RF10). La
// web lo sondea desde el navegador mientras el backend genera en un hilo
// aparte: sin este proxy, el fetch del cliente iría directo al backend, que
// no tiene CORS abierto (el token de sesión vive en una cookie httpOnly que
// sólo este servidor puede leer).

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const lang = new URL(request.url).searchParams.get("lang") ?? "es";

  try {
    const data = await callApi(`/api/charts/${id}/interpretation/estado?lang=${lang}`);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    console.error(`estado del informe ${id}: backend ${status}`);
    return NextResponse.json({ error: "no pudimos consultar el estado" }, { status });
  }
}
