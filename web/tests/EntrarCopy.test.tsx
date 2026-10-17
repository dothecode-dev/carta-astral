import { describe, expect, it } from "vitest";

import { LECTURAS_DE_REGALO } from "@/lib/regalo";
import { LOCALES, getDict } from "@/lib/i18n";

// Desde el 17-10-2026 el backend no regala lecturas (LECTURA_BREVE_GRATIS_ENABLED
// apagado): lo gratis es la carta y el adelanto del informe. Ningún texto que
// se muestra puede prometer una lectura de regalo.
const PROMETE_LECTURA = /lecturas? breves?|short readings?|leituras? breves?/i;
const PROMETE_REGALO = /regalo|presente|on the house|gratis|free|gr[aá]tis/i;

describe("nada promete una lectura de regalo", () => {
  it("el espejo del regalo dice cero", () => {
    expect(LECTURAS_DE_REGALO).toBe(0);
  });

  it.each(LOCALES)("%s", (locale) => {
    const dict = getDict(locale);
    const textos = [
      dict.pricing.title,
      ...dict.pricing.terms.map((t) => t.label),
      dict.precios.gratisNombre,
      dict.precios.gratisDetalle,
      dict.auth.lede,
      dict.newChart.seoGratisBody,
      dict.newChart.previewNote,
      dict.newChart.previewPrivacidad,
      dict.newChart.previewPrivacidadSinCompra,
    ];
    for (const texto of textos) {
      expect(texto).not.toMatch(PROMETE_LECTURA);
    }
    // Lo que se muestra cuando no hay lecturas no puede llamarlas gratis ni de regalo.
    for (const texto of [dict.chart.sinLeerBreve, dict.newChart.sinLeerBreve]) {
      expect(texto).not.toMatch(PROMETE_REGALO);
    }
  });
});

describe("el copy de /entrar", () => {
  it("no promete una lectura de regalo, en los tres idiomas", () => {
    for (const locale of LOCALES) {
      expect(getDict(locale).auth.lede).not.toMatch(PROMETE_LECTURA);
      expect(getDict(locale).auth.lede).not.toMatch(PROMETE_REGALO);
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
