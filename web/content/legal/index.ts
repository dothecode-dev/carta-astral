import type { Locale } from "@/lib/i18n";

import { legalEn } from "./en";
import { legalEs } from "./es";
import { legalPt } from "./pt";
import type { LegalContent } from "./types";

export const LEGAL: Record<Locale, LegalContent> = {
  es: legalEs,
  en: legalEn,
  pt: legalPt,
};

export { LEGAL_CONTACT, LEGAL_DOCS, LEGAL_UPDATED } from "./types";
export type { Block, LegalDoc, LegalDocKey } from "./types";
