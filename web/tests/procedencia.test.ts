import { afterEach, describe, expect, it } from "vitest";

import { _reiniciarProcedencia, capturarProcedencia, leerProcedencia } from "@/lib/procedencia";

// De dónde llegó la visita, guardado en memoria al entrar: sin cookies ni
// localStorage. El servidor lo reduce a canal y lugar (backend/api/conteo.py).

const lugar = (href: string) => new URL(href) as unknown as Location;

describe("procedencia", () => {
  afterEach(() => _reiniciarProcedencia());

  it("toma el utm_source y sólo el origen de la página anterior", () => {
    capturarProcedencia(lugar("https://astraguia.com/es/nueva?utm_source=google&gclid=abc"), "https://www.google.com/search?q=carta+natal");
    expect(leerProcedencia()).toMatchObject({ utm_source: "google", referrer: "https://www.google.com" });
  });

  it("una navegación interna no pisa de dónde llegó", () => {
    capturarProcedencia(lugar("https://astraguia.com/es"), "https://www.bing.com/");
    capturarProcedencia(lugar("https://astraguia.com/es/nueva"), "https://astraguia.com/es");
    expect(leerProcedencia().referrer).toBe("https://www.bing.com");
  });

  it("el referrer del propio sitio no cuenta como otro sitio", () => {
    capturarProcedencia(lugar("https://astraguia.com/es/nueva"), "https://astraguia.com/es");
    expect(leerProcedencia().referrer).toBe("");
  });

  it("manda la zona horaria del navegador", () => {
    capturarProcedencia(lugar("https://astraguia.com/es"), "");
    expect(leerProcedencia().zona).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
  });
});
