// La cookie de la lectura breve sin cuenta. Sin `next/headers` a propósito,
// como `compraCookie`: así la pueden importar los tests y cualquier ruta.
// Lleva el token en claro; el backend guarda sólo su hash.
export const LECTURA_COOKIE = "astra_lectura";
const MAX_AGE_SECONDS = 24 * 60 * 60;

export function opcionesLectura() {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    maxAge: MAX_AGE_SECONDS,
    path: "/",
  };
}
