import { NextResponse } from "next/server";

import { ApiError, callApi, clearSessionToken, getSessionToken, setSessionToken } from "@/lib/session";

// Punto único de entrada y salida de la sesión.
//
// El navegador manda el id_token que le dio Apple o Google; este servidor lo
// canjea contra el backend y guarda el token resultante en una cookie httpOnly.
// El token de sesión nunca vuelve al navegador en el cuerpo de la respuesta.

export const dynamic = "force-dynamic";

const PROVIDERS = { google: "/api/auth/google", apple: "/api/auth/apple" } as const;
type Provider = keyof typeof PROVIDERS;

type LoginResponse = {
  token: string;
  credits_available: number;
  account_id: number;
};

function isProvider(value: unknown): value is Provider {
  return typeof value === "string" && value in PROVIDERS;
}

export async function POST(request: Request) {
  let body: { provider?: unknown; id_token?: unknown; nonce?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  if (!isProvider(body.provider) || typeof body.id_token !== "string" || !body.id_token) {
    return NextResponse.json({ error: "faltan datos del proveedor" }, { status: 400 });
  }

  try {
    const data = await callApi<LoginResponse>(PROVIDERS[body.provider], {
      auth: false,
      method: "POST",
      body: JSON.stringify({
        id_token: body.id_token,
        ...(typeof body.nonce === "string" ? { nonce: body.nonce } : {}),
      }),
    });

    await setSessionToken(data.token);

    // Sin el token: la pantalla necesita el saldo, y la analítica el id interno
    // de la cuenta —nunca el email— para poder unir el embudo de una persona.
    // Es lo que la política de privacidad declara que se manda.
    return NextResponse.json({
      credits_available: data.credits_available,
      account_id: data.account_id,
    });
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) {
        return NextResponse.json({ error: "no pudimos verificar tu identidad" }, { status: 401 });
      }
      if (error.status === 503) {
        return NextResponse.json({ error: "login no disponible" }, { status: 503 });
      }
      if (error.status === 429) {
        return NextResponse.json({ error: "demasiados intentos" }, { status: 429 });
      }
    }
    return NextResponse.json({ error: "no pudimos iniciar sesión" }, { status: 502 });
  }
}

/** Cerrar sesión: se invalida en el backend y se borra la cookie. */
export async function DELETE() {
  const token = await getSessionToken();
  if (token) {
    try {
      await callApi("/api/auth/logout", { method: "POST" });
    } catch {
      // Si el backend no responde igual se borra la cookie: quedarse con la
      // sesión abierta del lado del navegador sería peor.
    }
  }
  await clearSessionToken();
  return NextResponse.json({ ok: true });
}
