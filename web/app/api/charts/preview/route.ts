import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";

// Calcula la carta de alguien que todavía no tiene cuenta: `auth: false`, así
// que no manda cookie ni la necesita. Nada de lo que llega acá se guarda —ni
// del lado del backend ni del nuestro—: la fecha, la hora y el lugar de
// nacimiento vuelven dibujados y se olvidan.

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  try {
    const carta = await callApi("/api/charts/preview/", {
      method: "POST",
      body: JSON.stringify(body),
      auth: false,
    });
    return NextResponse.json(carta);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 400) {
        return NextResponse.json({ error: "datos inválidos" }, { status: 400 });
      }
      if (error.status === 429) {
        // El techo es por IP: acá caen todos los que salen por un mismo NAT,
        // así que el mensaje tiene que sonar a "probá más tarde" y no a
        // "hiciste algo mal".
        return NextResponse.json({ error: "demasiadas cartas por ahora" }, { status: 429 });
      }
    }
    return NextResponse.json({ error: "no pudimos calcular la carta" }, { status: 502 });
  }
}
