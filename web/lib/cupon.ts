import { API_URL } from "./config";

import type { ProductoCatalogo } from "./catalogo";

// Un cupón en la página de precios. El descuento lo calcula el backend —la
// misma `precio_final` con la que abre el checkout y valida el pago—, así que
// acá no hay porcentaje que multiplicar: se pide y se pinta.
//
// Sin caché a propósito, al revés que el catálogo: los usos que quedan
// cambian con cada compra, y «quedan 3» congelado cinco minutos es mentir.
// Si el backend no responde, `null`: precio de lista, nunca un descuento
// inventado.

const TIMEOUT_MS = 3000;

/** El alfabeto de Stripe: mayúsculas, dígitos y guión, de 3 a 40. */
const FORMA = /^[A-Z0-9-]{3,40}$/;

/** El código como lo guarda el backend, o null si no tiene forma de código.
 *  Viene de la URL o de un campo: cualquiera escribe lo que quiera ahí. */
export function normalizarCupon(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const codigo = raw.trim().toUpperCase();
  return FORMA.test(codigo) ? codigo : null;
}

export type ProductoConCupon = ProductoCatalogo & {
  precio_final_centavos: number;
  descuento_centavos: number;
};

export type CuponRespuesta =
  | { valido: true; codigo: string; porcentaje: number; productos: ProductoConCupon[] }
  | { valido: false; motivo: string };

export async function fetchCupon(codigo: string, producto?: string): Promise<CuponRespuesta | null> {
  const query = producto ? `?producto=${encodeURIComponent(producto)}` : "";
  try {
    const res = await fetch(`${API_URL}/api/cupones/${encodeURIComponent(codigo)}/${query}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) return null;
    return (await res.json()) as CuponRespuesta;
  } catch {
    return null;
  }
}
