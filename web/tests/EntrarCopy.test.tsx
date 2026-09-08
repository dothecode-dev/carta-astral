import { describe, expect, it } from "vitest";

import { LECTURAS_DE_REGALO } from "@/lib/regalo";
import { LOCALES, getDict } from "@/lib/i18n";

describe("el copy de /entrar", () => {
  it("nombra las lecturas de regalo en los tres idiomas", () => {
    for (const locale of LOCALES) {
      const { auth } = getDict(locale);
      expect(auth.lede).toContain(String(LECTURAS_DE_REGALO));
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
