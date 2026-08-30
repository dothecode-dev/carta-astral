import { NextResponse } from "next/server";

import { ApiError, callApi, callApiRaw } from "@/lib/session";

// Genera la lectura de una carta. Es la única llamada de la web que gasta un
// crédito: el descuento lo hace el backend, nunca el navegador.

export const dynamic = "force-dynamic";

/**
 * La lectura ya escrita, si existe. No genera ni cobra: 404 mientras no está.
 *
 * La usa la espera del navegador cuando el backend avisa que otra petición ya
 * está escribiendo esta misma lectura.
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const lang = new URL(request.url).searchParams.get("lang") ?? "es";

  try {
    const data = await callApi(`/api/charts/${id}/interpretation/?lang=${lang}`);
    return NextResponse.json(data);
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    // 404 es el caso normal mientras se escribe: no hay nada que registrar.
    if (status !== 404) console.error(`lectura ${id}: backend ${status}`);
    return NextResponse.json({ error: "sin lectura" }, { status: status === 404 ? 404 : 502 });
  }
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  let body: { lang?: unknown; tier?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  try {
    // El backend arranca la generación en un hilo y devuelve el control con
    // 202: el informe todavía no existe. `callApi` sólo lanza si `!res.ok`, y
    // 202 lo es — usarlo acá aplastaría ese 202 a un 200 con body `null`,
    // indistinguible de un éxito síncrono, y la web nunca esperaría el
    // resultado. `callApiRaw` deja pasar el status real.
    const res = await callApiRaw(`/api/charts/${id}/interpretation/`, {
      method: "POST",
      body: JSON.stringify({ lang: body.lang, tier: body.tier }),
    });
    return new NextResponse(null, { status: res.status });
  } catch (error) {
    if (error instanceof ApiError) {
      // Sin esto, un fallo de generación llega al log como un 502 sin motivo.
      console.error(`interpretación ${id}: backend ${error.status} ${error.body}`);
      if (error.status === 401) return NextResponse.json({ error: "sin sesión" }, { status: 401 });
      // El backend responde 402 cuando no alcanzan los créditos, con
      // `code: "sin_free" | "sin_paid"` para distinguir cuál lote se quedó
      // sin crédito. Se reenvía tal cual: es la única forma en que el botón
      // sepa cuál de los dos mensajes mostrar.
      if (error.status === 402) {
        let code: string | undefined;
        try {
          code = (JSON.parse(error.body) as { code?: string }).code;
        } catch {
          // el cuerpo del backend no era JSON parseable: se sigue sin `code`.
        }
        return NextResponse.json({ error: "sin créditos", code }, { status: 402 });
      }
      if (error.status === 404) return NextResponse.json({ error: "no existe" }, { status: 404 });
      // Otra petición ya está escribiendo esta misma lectura: no es un fallo.
      if (error.status === 409) {
        return NextResponse.json({ error: "generación en curso" }, { status: 409 });
      }
      if (error.status === 429) {
        return NextResponse.json({ error: "demasiadas lecturas" }, { status: 429 });
      }
      // El tope diario y el fallo de generación: los dos se reintentan más tarde.
      if (error.status === 503) {
        return NextResponse.json({ error: "no disponible" }, { status: 503 });
      }
    } else {
      console.error(`interpretación ${id}:`, error);
    }
    return NextResponse.json({ error: "no pudimos generar la lectura" }, { status: 502 });
  }
}
