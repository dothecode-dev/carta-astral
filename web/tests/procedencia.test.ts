import { afterEach, describe, expect, it } from "vitest";

import { _reiniciarProcedencia, capturarProcedencia, leerProcedencia, seccionDe } from "@/lib/procedencia";

// De dónde llegó la visita, guardado en memoria al entrar: sin cookies ni
// localStorage. El servidor lo reduce a canal y lugar (backend/api/conteo.py).

const lugar = (href: string) => new URL(href) as unknown as Location;

describe("procedencia", () => {
  afterEach(() => _reiniciarProcedencia());

  it("toma el utm_source y sólo el origen de la página anterior", () => {
    capturarProcedencia(lugar("https://astraguia.com/es/nueva?utm_source=google&gclid=abc"), "https://www.google.com/search?q=carta+natal");
    expect(leerProcedencia()).toMatchObject({ utm_source: "google", gclid: true, referrer: "https://www.google.com" });
  });

  it("sin gclid ni utm, gclid va en false", () => {
    capturarProcedencia(lugar("https://astraguia.com/es"), "https://www.google.com/");
    expect(leerProcedencia()).toMatchObject({ utm_source: "", gclid: false });
  });

  it("la app de Google en Android no se pierde como directo", () => {
    capturarProcedencia(lugar("https://astraguia.com/es"), "android-app://com.google.android.googlequicksearchbox/");
    expect(leerProcedencia().referrer).toBe("android-app://com.google.android.googlequicksearchbox");
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

describe("seccionDe: la parte del sitio, nunca la ruta", () => {
  it.each([
    ["/es", "inicio"],
    ["/en/", "inicio"],
    ["/es/nueva", "nueva"],
    ["/es/carta/4712beb7-b86c-44bb-90ca-2b576edbf553", "carta"],
    ["/es/carta/4712beb7/lectura", "carta"],
    ["/pt/precios", "precios"],
    ["/es/notas/las-12-casas-astrologicas", "notas"],
    ["/en/notes/the-12-astrological-houses", "notas"],
    ["/es/cielo-hoy", "cielo"],
    ["/en/sky-today", "cielo"],
    ["/pt/ceu-hoje", "cielo"],
    ["/en/synastry", "sinastria"],
    ["/es/legal/privacy", "legal"],
    ["/es/algo-que-no-existe", "otra"],
    ["/pt/sinastria", "sinastria"],
    // La palabra de otro idioma es un 404: no cuenta como esa sección.
    ["/en/notas", "otra"],
    ["/en/cielo-hoy", "otra"],
    ["/es/synastry", "otra"],
    ["/fr/precios", "otra"],
  ])("%s → %s", (ruta, seccion) => {
    expect(seccionDe(ruta)).toBe(seccion);
  });
});
