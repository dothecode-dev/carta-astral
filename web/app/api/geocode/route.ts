import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";

// Búsqueda de lugares para el formulario. Pega al padrón del backend, que
// resuelve además el huso horario de cada localidad: sin eso, la hora de
// nacimiento se calcularía en el huso equivocado.
//
// Va sin sesión (`auth: false`) desde el 04-09-2026: el formulario de `/nueva`
// se usa sin cuenta, y quien no la tiene tiene que poder decir dónde nació.
// Abrir la vista del backend no alcanzaba —este proxy exigía el token por su
// cuenta y devolvía 401— y eso no lo vieron los tests de ninguno de los dos
// lados: se vio recorriendo el formulario en el navegador.

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
      auth: false,
    });
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 400) {
        return NextResponse.json({ results: [] });
      }
      if (error.status === 429) {
        // El techo del backend es por IP: acá caen todos los que comparten
        // salida. El campo lo muestra como "no encontramos nada", que es
        // mentira pero no rompe el formulario; el número está alto para que
        // esto no pase escribiendo a mano.
        return NextResponse.json({ results: [] }, { status: 429 });
      }
    }
    return NextResponse.json({ error: "no pudimos buscar el lugar" }, { status: 502 });
  }
}
