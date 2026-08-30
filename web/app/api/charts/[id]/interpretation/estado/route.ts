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
  const url = new URL(request.url);
  const lang = url.searchParams.get("lang") ?? "es";
  // Sin default (RF20): adivinar el tier es sondear el producto equivocado.
  const tier = url.searchParams.get("tier");

  try {
    const data = await callApi(
      `/api/charts/${id}/interpretation/estado/?lang=${lang}&tier=${tier}`,
    );
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    // 404 es "la carta no existe o es de otra cuenta": no hay nada que
    // registrar. El resto de los status del backend no se reenvía tal cual
    // (mismo criterio que el proxy de `interpretation/`): sólo 401 y 404 son
    // casos que el cliente puede distinguir; cualquier otra cosa es un 502.
    if (status !== 404) console.error(`estado del informe ${id}: backend ${status}`);
    if (status === 401) return NextResponse.json({ error: "sin sesión" }, { status: 401 });
    if (status === 404) return NextResponse.json({ error: "no existe" }, { status: 404 });
    return NextResponse.json({ error: "no pudimos consultar el estado" }, { status: 502 });
  }
}
