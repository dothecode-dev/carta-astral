import { describe, expect, it } from "vitest";

import { LECTURAS_DE_REGALO } from "@/lib/regalo";
import { LOCALES, getDict } from "@/lib/i18n";

// Desde el 17-10-2026 el backend no regala lecturas (LECTURA_BREVE_GRATIS_ENABLED
// apagado): lo gratis es la carta y el adelanto del informe. Ningún texto que
// se muestra puede prometer una lectura de regalo.
const PROMETE_LECTURA = /lecturas? breves?|short readings?|leituras? breves?/i;
const NO_CUESTA = /no cuesta nada|costs? nothing|n[aã]o custa nada/i;
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

// Guardián de RF11 que no depende de una lista a mano: recorre TODOS los
// strings del diccionario y falla si alguno promete una lectura gratis o de
// regalo. Un texto nuevo que lo prometa lo rompe sin que nadie lo agregue acá.
function strings(nodo: unknown, ruta = ""): [string, string][] {
  if (typeof nodo === "string") return [[ruta, nodo]];
  if (Array.isArray(nodo)) return nodo.flatMap((x, i) => strings(x, `${ruta}[${i}]`));
  if (nodo && typeof nodo === "object") {
    return Object.entries(nodo).flatMap(([k, v]) => strings(v, ruta ? `${ruta}.${k}` : k));
  }
  return [];
}

// Excepciones EXPLÍCITAS (nada más entra sin justificarse acá):
// - `interpretBreve*`: describen los derechos de lectura breve que ya existían,
//   que para quien los tiene siguen siendo verdad.
// - `lectura*` y `sinLeerBreve`: textos de la lectura breve que ya no se
//   renderizan para nadie nuevo (se conservan por quien conserva el derecho).
const EXCEPCIONES = [/(^|\.)interpretBreve[^.]*(\.|$)/, /(^|\.)lectura[^.]*(\.|$)/, /(^|\.)sinLeerBreve$/];

describe("ningún texto del diccionario promete una lectura gratis", () => {
  it.each(LOCALES)("%s", (locale) => {
    const promesas = strings(getDict(locale))
      .filter(([ruta]) => !EXCEPCIONES.some((e) => e.test(ruta)))
      .filter(([, texto]) => PROMETE_LECTURA.test(texto) && (PROMETE_REGALO.test(texto) || NO_CUESTA.test(texto)))
      .map(([ruta, texto]) => `${ruta}: ${texto}`);
    expect(promesas).toEqual([]);
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
