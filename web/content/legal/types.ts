// Los documentos legales se modelan como bloques, no como HTML crudo: así se
// renderizan con los estilos del sitio y no hace falta inyectar markup.
//
// El texto admite **negrita** — la única marca inline que usan estos documentos.

export type Block =
  | { kind: "h2"; text: string }
  | { kind: "p"; text: string }
  | { kind: "ul"; items: string[] };

export type LegalDoc = {
  /** Título de la página y del <title>. */
  title: string;
  /** Encabezado dentro del documento. */
  heading: string;
  blocks: Block[];
};

export type LegalContent = {
  privacy: LegalDoc;
  terms: LegalDoc;
  /** "Última actualización", traducido. */
  updatedLabel: string;
};

/** Fecha de la última revisión legal. Cambiarla al tocar cualquier documento. */
export const LEGAL_UPDATED = "2026-08-27";

// Del mismo dominio que el sitio a propósito: Polar cruza el dominio del mail
// de soporte con el de la web y marca la diferencia como inconsistencia en la
// revisión de la cuenta. Si cambia acá, tiene que cambiar también en Polar.
export const LEGAL_CONTACT = "info@astraguia.com";

export const LEGAL_DOCS = ["privacy", "terms"] as const;
export type LegalDocKey = (typeof LEGAL_DOCS)[number];
