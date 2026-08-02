import { cookies } from "next/headers";
import { API_URL } from "./config";

// El token de sesión vive en una cookie httpOnly: el navegador lo manda solo en
// cada pedido a este servidor, y ningún script de la página puede leerlo. El
// backend nunca recibe una llamada directa desde el navegador, así que tampoco
// hace falta abrirle CORS.

export const SESSION_COOKIE = "astra_session";

/** Igual que SESSION_TTL_DAYS del backend: que la cookie no sobreviva al token. */
const MAX_AGE_SECONDS = 90 * 24 * 60 * 60;


export async function getSessionToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value ?? null;
}

export async function setSessionToken(token: string): Promise<void> {
  const store = await cookies();
  store.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    // En desarrollo el sitio va por http; marcarla Secure haría que el navegador
    // la descarte y la sesión no duraría ni un click.
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  });
}

export async function clearSessionToken(): Promise<void> {
  const store = await cookies();
  store.delete(SESSION_COOKIE);
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/**
 * Llama al backend con la sesión de quien está navegando.
 *
 * El identificador de cuenta sale siempre del token, nunca de algo que mande el
 * cliente: si viniera del navegador, cualquiera podría pedir las cartas de otro.
 */
export async function callApi<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const { auth = true, headers, ...rest } = init;
  const token = auth ? await getSessionToken() : null;

  if (auth && !token) throw new ApiError(401, "sin sesión");

  const res = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    cache: "no-store",
  });

  if (!res.ok) {
    // El cuerpo del error del backend puede traer detalle útil, pero no se
    // reenvía tal cual al navegador: se traduce en cada ruta.
    throw new ApiError(res.status, `${path} devolvió ${res.status}`);
  }

  return res.json() as Promise<T>;
}
