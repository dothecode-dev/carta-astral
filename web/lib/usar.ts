import { type Derecho, puede } from "./derechos";

/**
 * «Usar en una carta nueva»: lo que la cuenta tiene disponible viaja con la
 * carta que se va a calcular (`/nueva?usar=…` → `/carta/{id}?usar=…`), y la
 * carta lo arranca sola al llegar, como si se hubiera apretado el botón.
 *
 * El parámetro viene de la URL, así que la cuenta lo pone pero cualquiera lo
 * escribe. Se valida en dos pasos: la forma (`normalizarUsar`, lista cerrada)
 * y, en el servidor de la carta, si procede (`tierParaArrancar`): con derecho,
 * sin ese tier ya escrito y sin nada escribiéndose. Sin derecho no arranca
 * nada —y menos abre un pago—: la carta se muestra con sus botones normales.
 */
export type Usar = "lectura_breve" | "informe_natal";
export type Tier = "corto" | "largo";

const TIER: Record<Usar, Tier> = { lectura_breve: "corto", informe_natal: "largo" };
const CAPACIDAD: Record<Usar, "leer_breve" | "leer_informe"> = {
  lectura_breve: "leer_breve",
  informe_natal: "leer_informe",
};

export function normalizarUsar(raw: unknown): Usar | null {
  return raw === "lectura_breve" || raw === "informe_natal" ? raw : null;
}

export function tierParaArrancar(
  usar: Usar | null,
  derechos: Derecho[],
  interpretations: Record<string, Tier[]>,
  enCurso: Record<string, Tier[]>,
  locale: string,
): Tier | null {
  if (!usar) return null;
  const tier = TIER[usar];
  if ((interpretations[locale] ?? []).includes(tier)) return null;
  if ((enCurso[locale] ?? []).length > 0) return null;
  if (!puede(derechos, CAPACIDAD[usar])) return null;
  return tier;
}
