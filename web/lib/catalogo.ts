import { API_URL } from "./config";
import { monedaPara, type Moneda } from "./monedas";

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
//
// EXCEPCIÓN a `rutasApiSinFetchDirecto.test.ts`: no pasa por `callApi`. Mismo
// motivo que `sky.ts` —`callApi` fuerza `cache: "no-store"`, que la guía de
// `fetch` (`node_modules/next/dist/docs/01-app/03-api-reference/04-functions/
// fetch.md`, "Good to know") marca como conflictivo con `next.revalidate`— y
// acá además no hay ningún techo que proteger: `CatalogoView`
// (`backend/api/catalogo_api.py`) no declara `throttle_classes`, así que
// reenviar `x-forwarded-for` no cambiaría nada.

const REVALIDATE_SECONDS = 300;
const TIMEOUT_MS = 3000;

export type ProductoCatalogo = {
  codigo: string;
  precio_centavos: number;
  moneda: string;
  /** Precio por moneda, en centavos de esa moneda: `{ usd: 500, brl: 2490 }`. */
  precios?: Record<string, number>;
  otorga: { codigo: string; cantidad: number }[];
};

/** `[centavos, moneda]` del producto para quien ve `moneda`. La moneda la
 * decide `monedaPara` —la misma que viaja al checkout—, así lo que se muestra
 * y lo que se cobra no pueden salir de dos reglas distintas. */
export function precioEn(producto: ProductoCatalogo, moneda: string): [number, Moneda] {
  const enMoneda = monedaPara(producto, moneda);
  return [producto.precios?.[enMoneda] ?? producto.precio_centavos, enMoneda];
}

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
  // Los pesos, en formato argentino en cualquier idioma (RF30): en en-US
  // «$25,000» se lee como dólares, y quien paga en pesos lee «$ 25.000».
  const enPesos = moneda.toLowerCase() === "ars";
  return new Intl.NumberFormat(enPesos ? "es-AR" : locale, {
    style: "currency",
    currency: moneda.toUpperCase(),
    // «US$» y no «$» para el dólar —en es-AR «$» es el peso—, pero «R$» y no
    // «BRL» para el real, que con `symbol` sale así en español.
    currencyDisplay: moneda.toLowerCase() === "usd" ? "symbol" : "narrowSymbol",
    // Los precios del catálogo son enteros; mostrar ",00" sólo agrega ruido.
    minimumFractionDigits: centavos % 100 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(centavos / 100);
}

/**
 * El precio de un producto, ya formateado, o `null` si el catálogo no
 * respondió o no lo vende. Es lo que llena el `{precio}` de los textos: el
 * número no se escribe en ningún diccionario, así un cambio de precio es un
 * cambio en `catalogo.py` y en Stripe, y nada más.
 */
export function precioDe(
  productos: ProductoCatalogo[] | null,
  codigo: string,
  locale: string,
  moneda = "usd",
): string | null {
  const producto = productos?.find((p) => p.codigo === codigo);
  if (!producto) return null;
  const [centavos, enMoneda] = precioEn(producto, moneda);
  return formatearPrecio(centavos, enMoneda, locale);
}

/**
 * Lo que una página ofrece de un producto: el precio ya formateado (o `null`
 * sin catálogo) y la moneda que tiene que viajar al checkout. Las dos salen de
 * `precioEn`: es la única forma de que el botón cobre en la moneda que muestra.
 */
export function ofertaDe(
  productos: ProductoCatalogo[] | null,
  codigo: string,
  locale: string,
  moneda: string,
): { precio: string | null; moneda: Moneda } {
  const producto = productos?.find((p) => p.codigo === codigo);
  if (!producto) return { precio: null, moneda: "usd" };
  const [centavos, enMoneda] = precioEn(producto, moneda);
  return { precio: formatearPrecio(centavos, enMoneda, locale), moneda: enMoneda };
}

/**
 * Completa el `{precio}` de un texto. Sin precio, lo saca junto con el
 * separador que lo sigue: «ocho secciones» se lee bien solo, y un marcador a
 * la vista o un precio inventado no.
 */
export function conPrecio(texto: string, precio: string | null): string {
  if (precio !== null) return texto.replaceAll("{precio}", precio);
  // El separador se va con el precio, esté el precio adelante («{precio} ·
  // ocho secciones») o al final («Comprar el informe · {precio}»).
  return texto
    .replace(/\{precio\}\s*·\s*/g, "")
    .replace(/\s*·\s*\{precio\}/g, "")
    .replaceAll("{precio}", "")
    .trim();
}
