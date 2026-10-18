// Las monedas que se venden y a cuál cae cada producto. Puro, sin nada del
// servidor: lo importan también los componentes de cliente. La moneda del
// visitante (cookie o IP) vive en `lib/moneda.ts`, que es sólo de servidor.

export const MONEDAS = ["usd", "brl"] as const;
export type Moneda = (typeof MONEDAS)[number];

export function esMoneda(valor: unknown): valor is Moneda {
  return typeof valor === "string" && (MONEDAS as readonly string[]).includes(valor);
}

/** La moneda en que se vende ESTE producto a quien ve `moneda`: la misma si
 * tiene precio en ella, si no USD (EC2: el vínculo no tiene precio en reales). */
export function monedaPara(producto: { precios?: Record<string, number> } | undefined, moneda: string): Moneda {
  return esMoneda(moneda) && producto?.precios?.[moneda] !== undefined ? moneda : "usd";
}
