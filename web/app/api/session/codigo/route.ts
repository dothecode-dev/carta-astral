import { NextResponse } from "next/server";

import { ApiError, callApi } from "@/lib/session";

// Pide (o reenvía) el código de acceso por mail — RF6/RF9.
//
// Es un pedido público: nadie probó su identidad todavía, así que va con
// `auth: false` igual que el canje de Google/Apple. El backend responde 202
// SIEMPRE que la config esté bien, sin importar si la dirección tiene cuenta
// —es la propiedad de no-enumeración— así que esta ruta no tiene nada que
// decidir: traduce el status tal cual.

export const dynamic = "force-dynamic";

type Body = {
  email?: unknown;
  lang?: unknown;
  destino?: unknown;
};

export async function POST(request: Request) {
  // Mismo scope "auth" que /api/session (Google/Apple): sin reenviar esto,
  // todos los pedidos de código —de cualquier persona— caen en el balde de
  // la IP del contenedor de la web. Ver el comentario gemelo en
  // `app/api/session/route.ts`.
  const ip = request.headers.get("x-forwarded-for");

  let body: Body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  if (typeof body.email !== "string" || !body.email) {
    return NextResponse.json({ error: "email requerido" }, { status: 400 });
  }

  const lang = typeof body.lang === "string" && body.lang ? body.lang : "es";
  // El destino se manda tal cual: el backend es quien lo valida y lo guarda
  // (sólo un path interno sobrevive esa validación), y esta ruta no lo expone
  // ni navega con él — sólo lo reenvía. La revalidación en la web importa
  // recién cuando el destino VUELVE en la respuesta del canje, en
  // `/api/session`.
  const destino = typeof body.destino === "string" ? body.destino : "";

  try {
    await callApi<Record<string, never>>("/api/auth/email/codigo", {
      auth: false,
      method: "POST",
      headers: ip ? { "x-forwarded-for": ip } : undefined,
      body: JSON.stringify({ email: body.email, lang, destino }),
    });

    return NextResponse.json({}, { status: 202 });
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 429) {
        return NextResponse.json({ error: "demasiados pedidos" }, { status: 429 });
      }
      if (error.status === 503) {
        return NextResponse.json({ error: "login no disponible" }, { status: 503 });
      }
      if (error.status === 400) {
        return NextResponse.json({ error: "email requerido" }, { status: 400 });
      }
    }
    return NextResponse.json({ error: "no pudimos enviar el código" }, { status: 502 });
  }
}
