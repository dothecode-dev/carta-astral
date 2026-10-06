import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";

// La vista previa de Vínculo: dos personas, sin cuenta. Igual que el preview de
// la carta suelta, nada de lo que pasa por acá se guarda de ningún lado: las
// fechas de nacimiento vuelven dibujadas y se olvidan.
//
// No manda la sesión (`auth: false`): el cálculo no la usa, y quien mira la
// vista previa puede no tener cuenta.

export const dynamic = "force-dynamic";

const MOTIVOS = new Set(["misma_persona", "datos_invalidos"]);

function motivoDe(error: ApiError): string {
  try {
    const cuerpo = JSON.parse(error.body) as { error?: unknown };
    return typeof cuerpo.error === "string" && MOTIVOS.has(cuerpo.error)
      ? cuerpo.error
      : "datos_invalidos";
  } catch {
    return "datos_invalidos";
  }
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "datos_invalidos" }, { status: 400 });
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    return NextResponse.json({ error: "datos_invalidos" }, { status: 400 });
  }

  // Sólo lo que el backend usa: un campo de más —un alias, por ejemplo— no
  // tiene por qué salir de acá.
  const { lang, a, b } = body as Record<string, unknown>;

  try {
    const preview = await callApi("/api/vinculo/preview/", {
      method: "POST",
      body: JSON.stringify({ lang, a, b }),
      auth: false,
    });
    return NextResponse.json(preview);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 400) {
        return NextResponse.json({ error: motivoDe(error) }, { status: 400 });
      }
      if (error.status === 404) {
        return NextResponse.json({ error: "apagado" }, { status: 404 });
      }
      if (error.status === 429) {
        // El techo es por IP: acá caen todos los que salen por un mismo NAT, así
        // que el mensaje tiene que sonar a «probá más tarde» y no a «hiciste
        // algo mal».
        return NextResponse.json({ error: "demasiadas" }, { status: 429 });
      }
    }
    return NextResponse.json({ error: "no_disponible" }, { status: 502 });
  }
}
