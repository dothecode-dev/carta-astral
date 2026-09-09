import { NextResponse } from "next/server";

import { destinoInternoSeguro } from "@/lib/destino";
import { ApiError, callApi, clearSessionToken, getSessionToken, setSessionToken } from "@/lib/session";
import type { Derecho } from "@/lib/derechos";

// Punto único de entrada y salida de la sesión.
//
// El navegador manda lo que haga falta para probar identidad —el id_token que
// le dio Apple o Google, o el email+código de la puerta de mail—; este
// servidor lo canjea contra el backend y guarda el token resultante en una
// cookie httpOnly. El token de sesión nunca vuelve al navegador en el cuerpo
// de la respuesta.

export const dynamic = "force-dynamic";

const PROVIDERS = {
  google: "/api/auth/google",
  apple: "/api/auth/apple",
  email: "/api/auth/email",
} as const;
type Provider = keyof typeof PROVIDERS;

type LoginResponse = {
  token: string;
  derechos: Derecho[];
  account_id: number;
  /** Sólo el canje por mail lo manda (RF16): a dónde volver después de entrar. */
  destino?: string;
};

function isProvider(value: unknown): value is Provider {
  return typeof value === "string" && value in PROVIDERS;
}

type Body = {
  provider?: unknown;
  id_token?: unknown;
  nonce?: unknown;
  email?: unknown;
  codigo?: unknown;
};

export async function POST(request: Request) {
  // El scope "auth" del backend (`AUTH_RATE`) es un techo por IP: sin
  // reenviar esto, `callApi` no manda nada propio y las tres puertas —Google,
  // Apple y mail— comparten un solo balde para el sitio entero, la IP del
  // contenedor de la web. Mismo patrón que `app/rueda/[...path]/route.ts` usa
  // para PostHog. El backend decide qué hacer con el valor (ver NUM_PROXIES
  // en `backend/config/settings.py`); acá sólo se reenvía tal cual llegó.
  const ip = request.headers.get("x-forwarded-for");

  let body: Body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  if (!isProvider(body.provider)) {
    return NextResponse.json({ error: "faltan datos del proveedor" }, { status: 400 });
  }

  let apiBody: Record<string, unknown>;
  if (body.provider === "email") {
    // El camino de mail no tiene id_token: manda email + el código de 6
    // dígitos que llegó por mail.
    if (typeof body.email !== "string" || !body.email || typeof body.codigo !== "string" || !body.codigo) {
      return NextResponse.json({ error: "faltan datos del proveedor" }, { status: 400 });
    }
    apiBody = { email: body.email, codigo: body.codigo };
  } else {
    if (typeof body.id_token !== "string" || !body.id_token) {
      return NextResponse.json({ error: "faltan datos del proveedor" }, { status: 400 });
    }
    apiBody = {
      id_token: body.id_token,
      ...(typeof body.nonce === "string" ? { nonce: body.nonce } : {}),
    };
  }

  try {
    const data = await callApi<LoginResponse>(PROVIDERS[body.provider], {
      auth: false,
      method: "POST",
      headers: ip ? { "x-forwarded-for": ip } : undefined,
      body: JSON.stringify(apiBody),
    });

    await setSessionToken(data.token);
    const destino = destinoInternoSeguro(data.destino);

    // Sin el token: la pantalla necesita los derechos, y la analítica el id
    // interno de la cuenta —nunca el email— para poder unir el embudo de una
    // persona. Es lo que la política de privacidad declara que se manda.
    return NextResponse.json({
      derechos: data.derechos,
      account_id: data.account_id,
      ...(destino ? { destino } : {}),
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
