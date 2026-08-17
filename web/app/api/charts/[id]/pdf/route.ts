import { ApiError, callApiRaw } from "@/lib/session";

// El PDF de una carta. El navegador arma la geometría de la rueda y los rótulos
// traducidos; el backend escribe el documento. Acá sólo se agrega la sesión y se
// devuelven los bytes tal cual, sin tocarlos.

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  try {
    const upstream = await callApiRaw(`/api/charts/${id}/pdf/`, {
      method: "POST",
      body: JSON.stringify(body),
    });

    // El nombre del archivo lo decide el backend, que conoce el nombre real de
    // la carta: se reenvía tal cual para no perder los acentos por el camino.
    const headers = new Headers({ "Content-Type": "application/pdf" });
    const disposition = upstream.headers.get("content-disposition");
    if (disposition) headers.set("Content-Disposition", disposition);

    return new Response(upstream.body, { headers });
  } catch (error) {
    if (error instanceof ApiError) {
      console.error(`pdf ${id}: backend ${error.status} ${error.body}`);
      if (error.status === 401) return Response.json({ error: "sin sesión" }, { status: 401 });
      if (error.status === 404) return Response.json({ error: "no existe" }, { status: 404 });
      if (error.status === 400) return Response.json({ error: "datos inválidos" }, { status: 400 });
      if (error.status === 429) {
        return Response.json({ error: "demasiados PDF" }, { status: 429 });
      }
    } else {
      console.error(`pdf ${id}:`, error);
    }
    return Response.json({ error: "no pudimos generar el PDF" }, { status: 502 });
  }
}
