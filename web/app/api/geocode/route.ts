import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";

// Búsqueda de lugares para el formulario. Pega al padrón del backend, que
// resuelve además el huso horario de cada localidad: sin eso, la hora de
// nacimiento se calcularía en el huso equivocado.

export const dynamic = "force-dynamic";

export type Place = {
  place_query: string;
  name: string;
  lat: number;
  lng: number;
  tz_name: string | null;
  country_code: string;
  admin1: string | null;
  population: number;
};

export async function POST(request: Request) {
  let body: { q?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ results: [] });
  }

  if (typeof body.q !== "string" || body.q.trim().length < 3) {
    // El backend rechaza las consultas cortas con un 400; acá se responde vacío
    // porque mientras se escribe, "aún no alcanza" no es un error.
    return NextResponse.json({ results: [] });
  }

  try {
    const data = await callApi<{ results: Place[] }>("/api/geocode/", {
      method: "POST",
      body: JSON.stringify({ q: body.q }),
    });
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) {
        return NextResponse.json({ error: "sin sesión" }, { status: 401 });
      }
      if (error.status === 400) {
        return NextResponse.json({ results: [] });
      }
    }
    return NextResponse.json({ error: "no pudimos buscar el lugar" }, { status: 502 });
  }
}
