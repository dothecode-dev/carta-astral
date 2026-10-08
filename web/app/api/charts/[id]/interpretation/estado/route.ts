import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";
import { conQuery, langYTier, parametrosInvalidos } from "@/lib/consultaBackend";
import { noExiste, uuidValido } from "@/lib/uuid";

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
  if (!uuidValido(id)) return noExiste();
  // Sin default de tier (RF20): adivinarlo es sondear el producto
  // equivocado. Fuera de la lista, 400 sin llamar al backend.
  const query = langYTier(new URL(request.url));
  if (!query) return parametrosInvalidos();

  try {
    const data = await callApi(conQuery(`/api/charts/${id}/interpretation/estado/`, query));
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
