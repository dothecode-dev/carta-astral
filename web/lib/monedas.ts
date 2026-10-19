// Las monedas que se venden y a cuál cae cada producto. Puro, sin nada del
// servidor: lo importan también los componentes de cliente. La moneda del
// visitante (cookie o IP) vive en `lib/moneda.ts`, que es sólo de servidor.

// `ars` está siempre en la lista, pero el backend sólo pone precios en pesos en
// el catálogo con `COBRO_ARS_ENABLED` prendido: apagado, `monedaPara` cae a usd
// y el selector no la ofrece. El flag vive en un solo lado.
export const MONEDAS = ["usd", "brl", "ars"] as const;
export type Moneda = (typeof MONEDAS)[number];

export function esMoneda(valor: unknown): valor is Moneda {
  return typeof valor === "string" && (MONEDAS as readonly string[]).includes(valor);
}

/** La moneda en que se vende ESTE producto a quien ve `moneda`: la misma si
 * tiene precio en ella, si no USD (EC2: el vínculo no tiene precio en reales). */
export function monedaPara(producto: { precios?: Record<string, number> } | undefined, moneda: string): Moneda {
  return esMoneda(moneda) && producto?.precios?.[moneda] !== undefined ? moneda : "usd";
}

/** Las monedas que ofrece el selector: usd siempre, y cada una de las otras si
 * algún producto del catálogo tiene precio en ella. Sin catálogo, sólo usd. */
export function monedasOfrecidas(
  productos: readonly { precios?: Record<string, number> }[] | null,
): Moneda[] {
  return MONEDAS.filter((m) => m === "usd" || (productos ?? []).some((p) => p.precios?.[m] !== undefined));
}
