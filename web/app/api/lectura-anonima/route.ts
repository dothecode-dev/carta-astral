import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { LECTURA_COOKIE, opcionesLectura } from "@/lib/lecturaCookie";
import { ApiError, callApi, motivoDe } from "@/lib/session";

// La lectura breve sin cuenta (spec 2026-10-08). El token vive en una cookie
// httpOnly de este dominio y viaja al backend como header: el navegador nunca
// lo ve. La cookie se pone en la respuesta, como en `checkout/anonimo`.

export const dynamic = "force-dynamic";

const MOTIVOS = new Set(["datos", "usado", "ip", "cupo", "ocupado", "mantenimiento"]);

async function token(): Promise<string | undefined> {
  return (await cookies()).get(LECTURA_COOKIE)?.value;
}

function cabeceras(t: string | undefined): Record<string, string> {
  return t ? { "X-Lectura-Token": t } : {};
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ motivo: "datos" }, { status: 400 });
  }
  try {
    const data = await callApi<{ token?: unknown; estado?: unknown }>("/api/lectura-anonima/", {
      method: "POST",
      body: JSON.stringify(body),
      auth: false,
      headers: cabeceras(await token()),
    });
    if (typeof data.token !== "string" || !data.token) {
      console.error("lectura anónima: respuesta del backend sin token");
      return NextResponse.json({ motivo: "error" }, { status: 502 });
    }
    const res = NextResponse.json({ estado: data.estado }, { status: 202 });
    res.cookies.set(LECTURA_COOKIE, data.token, opcionesLectura());
    return res;
  } catch (error) {
    const motivo = motivoDe(error);
    if (error instanceof ApiError && motivo && MOTIVOS.has(motivo)) {
      return NextResponse.json({ motivo }, { status: error.status });
    }
    // Un 400 sin `motivo` (el parser del backend rechaza un JSON que no es un
    // objeto con `{"detail": ...}`) sigue siendo un dato mal formado, no un 502.
    if (error instanceof ApiError && error.status === 400) {
      return NextResponse.json({ motivo: "datos" }, { status: 400 });
    }
    console.error(`lectura anónima: backend ${error instanceof ApiError ? error.status : "sin respuesta"}`);
    return NextResponse.json({ motivo: "error" }, { status: 502 });
  }
}

export async function GET() {
  const t = await token();
  if (!t) return NextResponse.json({ motivo: "nada" }, { status: 404 });
  try {
    return NextResponse.json(await callApi("/api/lectura-anonima/", { auth: false, headers: cabeceras(t) }));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return NextResponse.json({ motivo: "nada" }, { status: 404 });
    }
    console.error("lectura anónima: el GET al backend falló");
    return NextResponse.json({ motivo: "error" }, { status: 502 });
  }
}
