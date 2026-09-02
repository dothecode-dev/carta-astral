import { cookies } from "next/headers";
import { API_URL } from "./config";
import type { Locale } from "./i18n";

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

/**
 * ¿Hay una cookie de sesión? Nada más que eso.
 *
 * Lo usan las páginas públicas —home, notas, ejemplo, legales— para pintar el
 * header. Antes no lo consultaban: eran estáticas, así que el header decía
 * "Entrar" a todo el mundo y alguien con la sesión abierta que iba de su carta
 * a los Términos se encontraba con un sitio que no lo reconocía.
 *
 * No valida contra el backend a propósito —para eso está `sessionIsLive`—: un
 * enlace en el header no justifica una llamada de red en cada página pública, y
 * el peor caso de una cookie vencida es un clic que termina en el login, que es
 * adonde esa persona iba a ir igual.
 */
export async function haySesion(): Promise<boolean> {
  return (await getSessionToken()) !== null;
}

/**
 * A dónde mandar a alguien cuya cookie el backend ya no reconoce.
 *
 * No alcanza con redirigirlo a /entrar: la cookie muerta seguiría ahí y
 * /entrar lo devolvería a la página protegida, en un rebote infinito. Un
 * Server Component puede leer cookies pero no borrarlas —sólo un Route
 * Handler puede—, así que la limpieza pasa por esta ruta.
 */
export const RUTA_SESION_EXPIRADA = (locale: Locale | string) =>
  `/api/session/expirada?locale=${encodeURIComponent(locale)}`;

/**
 * ¿El backend todavía reconoce esta sesión?
 *
 * Tener la cookie no es tener sesión: el token pudo vencer, la cuenta pudo
 * borrarse. Ante cualquier error —401, backend caído, red cortada— la
 * respuesta es "no": mostrar el login de más nunca deja a nadie trabado,
 * redirigir de más sí.
 */
export async function sessionIsLive(): Promise<boolean> {
  if (!(await getSessionToken())) return false;
  try {
    await callApi("/api/account/");
    return true;
  } catch (error) {
    // Un 401 es la respuesta esperada de una sesión muerta y no es noticia.
    // Cualquier otra cosa sí: sin este log, un backend caído se vería igual
    // que una sesión vencida y mandaría a todo el mundo a loguearse de nuevo
    // en silencio.
    if (!(error instanceof ApiError) || error.status !== 401) {
      console.error("no se pudo validar la sesión:", error);
    }
    return false;
  }
}

export async function clearSessionToken(): Promise<void> {
  const store = await cookies();
  store.delete(SESSION_COOKIE);
}

/**
 * Igual que `callApi`, pero para lo que no es JSON: devuelve la respuesta cruda.
 *
 * El PDF de la carta son bytes, y parsearlos como JSON sería romperlos. La
 * autenticación es la misma: el token sale de la cookie, nunca del cliente.
 */
export async function callApiRaw(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = await getSessionToken();
  if (!token) throw new ApiError(401, "sin sesión");

  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new ApiError(res.status, `${path} devolvió ${res.status}`, detail.slice(0, 500));
  }
  return res;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** El cuerpo crudo que devolvió el backend. Se registra, no se reenvía. */
    readonly body = "",
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
    // El cuerpo del error del backend trae el motivo. No se reenvía tal cual al
    // navegador —cada ruta lo traduce—, pero sin guardarlo acá el fallo llega a
    // los logs como un 502 pelado y no hay forma de saber qué pasó.
    const detail = await res.text().catch(() => "");
    throw new ApiError(res.status, `${path} devolvió ${res.status}`, detail.slice(0, 500));
  }

  // Los borrados responden 204 sin cuerpo: intentar parsearlo haría fallar una
  // operación que salió bien.
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return null as T;
  }

  return res.json() as Promise<T>;
}
