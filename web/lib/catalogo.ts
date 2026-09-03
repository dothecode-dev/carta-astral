import { API_URL } from "./config";

// Qué se vende y a cuánto. El precio lo pone el backend —`catalogo.py`, la
// misma fuente con la que el webhook valida lo que Stripe cobró—, así que la
// página no puede anunciar un número distinto del que se cobra. El pack de 5 ya
// cambió de precio una vez.
//
// El pedido sale del servidor de Next, como el del cielo: el backend recibe uno
// por revalidación en vez de uno por visitante, y los precios llegan en el HTML
// (importa: la página tiene que ser indexable).
//
// Si el backend no responde, `null`: la página muestra un aviso y sigue en pie.
// Precios en blanco es mejor que precios inventados.

const REVALIDATE_SECONDS = 300;
const TIMEOUT_MS = 3000;

export type ProductoCatalogo = {
  codigo: string;
  precio_centavos: number;
  moneda: string;
  otorga: { codigo: string; cantidad: number }[];
};

export async function fetchCatalogo(): Promise<ProductoCatalogo[] | null> {
  try {
    const res = await fetch(`${API_URL}/api/catalogo/`, {
      next: { revalidate: REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) return null;

    const data: { productos: ProductoCatalogo[] } = await res.json();
    return data.productos ?? null;
  } catch {
    // Sin log a propósito: el server de Next lo registra igual y esto corre en
    // cada revalidación. Lo que importa es que la página no se caiga.
    return null;
  }
}

/** Cuántas unidades deja el producto: 1 el suelto, 3 y 5 los packs. */
export function unidades(producto: ProductoCatalogo): number {
  return producto.otorga.reduce((total, o) => total + o.cantidad, 0);
}

/** "US$ 29" y no "$29.00": el precio es redondo y el símbolo dice la moneda. */
export function formatearPrecio(centavos: number, moneda: string, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: moneda.toUpperCase(),
    // Los precios del catálogo son enteros; mostrar ",00" sólo agrega ruido.
    minimumFractionDigits: centavos % 100 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(centavos / 100);
}
