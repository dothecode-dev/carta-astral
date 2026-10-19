import { cookies } from "next/headers";

import { esMoneda, type Moneda } from "./monedas";
import { callApi } from "./session";

export { MONEDAS, esMoneda, monedaPara, monedasOfrecidas, type Moneda } from "./monedas";

// En qué moneda ve los precios —y paga— quien navega (RF23 de la spec de
// cobro en reales). Lo que se muestra y lo que se manda al checkout salen de
// acá, así que no pueden diferir: el backend cobra en la moneda que recibe, y
// sin ninguna cobra en USD.
//
// Orden: la cookie `astra_moneda` (la puso el selector de /precios), si vale
// una moneda conocida; si no, la que el backend deduce de la IP
// (`GET /api/moneda/`, con la IP del visitante que `callApi` reenvía); ante
// cualquier falla, `usd`. Sin base de países en la web: la tiene el backend.

export const COOKIE_MONEDA = "astra_moneda";
const TIMEOUT_MS = 1500;

export async function monedaDelVisitante(): Promise<Moneda> {
  const elegida = (await cookies()).get(COOKIE_MONEDA)?.value;
  if (esMoneda(elegida)) return elegida;
  try {
    const { moneda } = await callApi<{ moneda?: unknown }>("/api/moneda/", {
      auth: false,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    return esMoneda(moneda) ? moneda : "usd";
  } catch (error) {
    // Un timeout o un error de red no llegan nunca al backend: sin este log,
    // un endpoint roto mostraría USD a todo Brasil sin que nadie se entere.
    console.warn("moneda del visitante: falló /api/moneda/, se muestra usd", error);
    return "usd";
  }
}
