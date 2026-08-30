import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";

// El índice del informe completo (RF3): título de cada sección y, si ya hay
// algo generado, el arranque de cada una. Lo pide el pie de la lectura breve
// para mostrar qué se compra, antes de que exista ninguna compra — por eso
// no exige tier ni dispara generación, sólo reenvía `lang`.

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const url = new URL(request.url);
  const lang = url.searchParams.get("lang") ?? "es";

  try {
    const data = await callApi(`/api/charts/${id}/informe/indice/?lang=${lang}`);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    // 404 es "la carta no existe o es de otra cuenta": no hay nada que
    // registrar (mismo criterio que el resto de los proxies de este directorio).
    if (status !== 404) console.error(`índice del informe ${id}: backend ${status}`);
    if (status === 401) return NextResponse.json({ error: "sin sesión" }, { status: 401 });
    if (status === 404) return NextResponse.json({ error: "no existe" }, { status: 404 });
    return NextResponse.json({ error: "no pudimos consultar el índice" }, { status: 502 });
  }
}
