import { describe, expect, it } from "vitest";

import { LECTURAS_DE_REGALO } from "@/lib/regalo";
import { LOCALES, getDict } from "@/lib/i18n";

/** Cómo tiene que nombrar un texto la cantidad de regalo: en singular si es
 *  una («una lectura breve»), con el número si son más. Lo que no puede es
 *  decir «tres» cuando el backend regala una. */
function promesaDelRegalo(locale: string): RegExp {
  if (LECTURAS_DE_REGALO === 1) {
    return { es: /(una|primera) lectura breve/i, en: /(a|first) short reading\b/i, pt: /(uma|primeira) leitura breve/i }[
      locale
    ]!;
  }
  return new RegExp(`\\b${LECTURAS_DE_REGALO}\\b`);
}

const PLURAL_DEL_REGALO = { es: /lecturas breves/i, en: /short readings/i, pt: /leituras breves/i };

describe("todo texto que nombra el regalo dice la cantidad que da el backend", () => {
  it.each(LOCALES)("%s", (locale) => {
    const dict = getDict(locale);
    const textos = [
      dict.pricing.title,
      dict.pricing.terms[0].label,
      dict.precios.gratisDetalle,
      dict.auth.lede,
    ];
    for (const texto of textos.slice(0, 2).concat(textos[3])) {
      expect(texto).toMatch(promesaDelRegalo(locale));
    }
    if (LECTURAS_DE_REGALO === 1) {
      // Con una sola, ni el detalle de /precios ni los avisos de agotado
      // pueden hablar en plural del regalo.
      expect(dict.precios.gratisDetalle).not.toMatch(/\b(tres|three|três|3)\b/i);
      for (const texto of [...textos, dict.chart.sinLeerBreve, dict.newChart.sinLeerBreve]) {
        expect(texto).not.toMatch(PLURAL_DEL_REGALO[locale as keyof typeof PLURAL_DEL_REGALO]);
      }
    }
  });
});

describe("el copy de /entrar", () => {
  it("promete las lecturas de regalo que da el backend, en los tres idiomas", () => {
    for (const locale of LOCALES) {
      expect(getDict(locale).auth.lede).toMatch(promesaDelRegalo(locale));
    }
  });

  it("no promete un archivador", () => {
    // El lede viejo hablaba de guardar cartas. Quien llega acá apretó
    // «quiero leerme»: lo que le importa es leerse, no archivar.
    expect(getDict("es").auth.lede).not.toMatch(/guardad/i);
  });

  it("el cartel de Google roto ofrece la puerta de mail", () => {
    for (const locale of LOCALES) {
      const { auth } = getDict(locale);
      expect(auth.blocked).toMatch(/mail|correo|e-mail/i);
    }
  });
});
