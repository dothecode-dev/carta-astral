import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { LEGAL, LEGAL_CONTACT, LEGAL_DOCS, LEGAL_UPDATED } from "@/content/legal";
import { LOCALES } from "@/lib/i18n";

// Los documentos legales describen cómo se cobra, qué se entrega y qué pasa con
// un reembolso. Cuando el producto cambia y el texto no, el sitio le promete al
// comprador algo distinto de lo que hace el código — y la pasarela lee ese
// texto en su revisión de la cuenta.
//
// Pasó de verdad: el modelo de créditos murió el 01-09-2026 y hasta el 03-09
// los términos seguían diciendo que las lecturas consumían "1 crédito"
// comprado en Google Play y que los reembolsos los resolvía "la tienda".
// Ninguna suite lo vio: el test de `i18n` sólo mira los diccionarios, y el
// único chequeo que leía estos archivos EXIGÍA esas menciones.
//
// `scripts/check-legal.mjs` es el que audita el texto palabra por palabra (y
// corre en el mismo gate). Acá va lo que ese script no puede ver: que los
// documentos existan, estén completos en los tres idiomas y no se contradigan
// con el catálogo.

describe("documentos legales", () => {
  it("existen los dos documentos en los tres idiomas, sin bloques vacíos", () => {
    for (const locale of LOCALES) {
      const legal = LEGAL[locale];
      for (const key of LEGAL_DOCS) {
        const doc = legal[key];
        expect(doc.title.trim(), `${locale}/${key}: título vacío`).not.toBe("");
        expect(doc.heading.trim(), `${locale}/${key}: encabezado vacío`).not.toBe("");
        expect(doc.blocks.length, `${locale}/${key}: sin bloques`).toBeGreaterThan(0);

        for (const block of doc.blocks) {
          if (block.kind === "ul") {
            expect(block.items.length, `${locale}/${key}: lista vacía`).toBeGreaterThan(0);
            for (const item of block.items) {
              expect(item.trim(), `${locale}/${key}: item vacío`).not.toBe("");
            }
          } else {
            expect(block.text.trim(), `${locale}/${key}: bloque de texto vacío`).not.toBe("");
          }
        }
      }
    }
  });

  it("las negritas están cerradas", () => {
    // `**` sin cerrar deja el asterisco crudo en la página.
    for (const locale of LOCALES) {
      const textos = JSON.stringify(LEGAL[locale]);
      const asteriscos = (textos.match(/\*\*/g) ?? []).length;
      expect(asteriscos % 2, `${locale}: hay un ** sin cerrar`).toBe(0);
    }
  });

  it("el mail de contacto es del dominio del sitio", () => {
    // Las pasarelas cruzan el dominio del mail de soporte con el de la web y
    // marcan la diferencia como inconsistencia: Polar rechazaba
    // `info@dothecode.com` por eso.
    expect(LEGAL_CONTACT.endsWith("@astraguia.com")).toBe(true);
  });

  it("la fecha de revisión tiene formato de fecha", () => {
    expect(LEGAL_UPDATED).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("el chequeo de texto legal sigue existiendo y prohíbe lo que se fue", () => {
    // Este test es la red del chequeo, no del texto: si alguien borra
    // `scripts/check-legal.mjs` o su lista de prohibidos, los legales vuelven
    // a quedar sin auditar y nadie se entera hasta que un comprador lo lee.
    const script = readFileSync(join(process.cwd(), "scripts", "check-legal.mjs"), "utf8");
    expect(script).toContain("FORBIDDEN");
    for (const prohibido of ["RevenueCat", "Google Play", "App Store"]) {
      expect(script, `el chequeo dejó de prohibir "${prohibido}"`).toContain(prohibido);
    }
  });
});
