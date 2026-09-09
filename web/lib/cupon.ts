import type { ProductoCatalogo } from "./catalogo";
import { normalizarCupon } from "./cuponForma";
import { callApi } from "./session";

// Un cupón en la página de precios. El descuento lo calcula el backend —la
// misma `precio_final` con la que abre el checkout y valida el pago—, así que
// acá no hay porcentaje que multiplicar: se pide y se pinta.
//
// Sin caché a propósito, al revés que el catálogo: los usos que quedan
// cambian con cada compra, y «quedan 3» congelado cinco minutos es mentir.
// Si el backend no responde, `null`: precio de lista, nunca un descuento
// inventado.
//
// Por `callApi` (público, `auth: false`), no por `fetch` directo: no hay
// caché de Next que perder acá (ya era `no-store`), la página de precios ya
// es dinámica por `searchParams` antes de llegar acá, y el endpoint tiene
// techo por IP en el backend (`throttle_scope = "cupon"`, 30/hora) — sin
// reenviar `x-forwarded-for` ese techo cuenta un solo balde para todo el
// sitio, el de la IP del contenedor de la web, en vez de uno por visitante.
//
// `normalizarCupon` no vive acá: es pura y la usa un Client Component
// (`CuponInput`), que no puede arrastrar `callApi` ni `next/headers` a su
// bundle. Vive en `cuponForma.ts` y se re-exporta para no romper a quien ya
// la importaba desde acá (`entrar/page.tsx`, `precios/page.tsx`,
// `api/session/expirada/route.ts`).
export { normalizarCupon };

const TIMEOUT_MS = 3000;

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
    return await callApi<CuponRespuesta>(`/api/cupones/${encodeURIComponent(codigo)}/${query}`, {
      auth: false,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    return null;
  }
}
