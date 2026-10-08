import { isLocale, type Locale } from "./i18n";

/**
 * Lo que viene del cliente y termina en una URL del backend.
 *
 * Se valida contra la lista cerrada que acepta el backend y la query se arma
 * con `URLSearchParams`, nunca concatenando: `lang=es%26tier%3Dcorto` llega a
 * la ruta decodificado como `es&tier=corto`, y pegado en la URL del backend
 * mete un parámetro que el cliente no debería poder elegir.
 *
 * Idiomas: los mismos tres de la web (`LOCALES`), que son los de
 * `_INTERPRETATION_LANGS` en `backend/api/views.py`. Tiers: `_TIERS`.
 */
export const TIERS = ["corto", "largo"] as const;
export type Tier = (typeof TIERS)[number];

export function tierValido(tier: unknown): tier is Tier {
  return typeof tier === "string" && (TIERS as readonly string[]).includes(tier);
}

export function langValido(lang: unknown): lang is Locale {
  return typeof lang === "string" && isLocale(lang);
}

/** `path` con su query, cada valor codificado. */
export function conQuery(path: string, params: Record<string, string>): string {
  return `${path}?${new URLSearchParams(params)}`;
}

/** La respuesta ante un parámetro del cliente fuera de la lista cerrada. */
export function parametrosInvalidos(): Response {
  return Response.json({ error: "parámetros inválidos" }, { status: 400 });
}

/** `lang` (por defecto `es`, como siempre) y `tier` (sin defecto: adivinarlo
 *  es leer el producto equivocado, RF20) de la query de la ruta, o `null` si
 *  alguno no es de la lista. */
export function langYTier(url: URL): { lang: Locale; tier: Tier } | null {
  const lang = url.searchParams.get("lang") ?? "es";
  const tier = url.searchParams.get("tier");
  return langValido(lang) && tierValido(tier) ? { lang, tier } : null;
}
