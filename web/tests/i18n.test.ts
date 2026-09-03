import { describe, expect, it } from "vitest";

import {
  ASPECT_GLYPHS,
  ASPECT_NAMES,
  LOCALES,
  PLANET_NAMES,
  PLANET_NAME_BY_KEY,
  getDict,
  isLocale,
  negociarIdioma,
} from "@/lib/i18n";

// Los tres idiomas se escriben a mano y a distinto tiempo: el hueco típico es
// agregar un texto en español y que en inglés o portugués salga `undefined` en
// medio de la pantalla, que nadie mira hasta que un lector lo reporta.

/** Todas las rutas de un objeto anidado, como "chart.columns.house". */
function rutas(value: unknown, prefijo = ""): string[] {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return [prefijo];
  return Object.entries(value as Record<string, unknown>).flatMap(([k, v]) =>
    rutas(v, prefijo ? `${prefijo}.${k}` : k),
  );
}

function valorEn(dict: unknown, ruta: string): unknown {
  return ruta.split(".").reduce<unknown>((acc, k) => (acc as Record<string, unknown>)?.[k], dict);
}

const referencia = rutas(getDict("es")).sort();

describe("diccionarios", () => {
  for (const locale of LOCALES) {
    it(`${locale} tiene los mismos textos que el español`, () => {
      expect(rutas(getDict(locale)).sort()).toEqual(referencia);
    });

    it(`${locale} no deja ningún texto vacío`, () => {
      const dict = getDict(locale);
      // Algunas entradas son listas —los pasos de la espera, las preguntas
      // frecuentes—: valen si tienen contenido y ninguna línea vacía.
      const lleno = (v: unknown): boolean => {
        if (Array.isArray(v)) return v.length > 0 && v.every(lleno);
        if (typeof v === "string") return v.trim() !== "";
        // Las listas de precios llevan banderas junto al texto ("popular").
        if (typeof v === "boolean" || typeof v === "number") return true;
        return typeof v === "object" && v !== null && Object.values(v).every(lleno);
      };

      const vacios = referencia.filter((ruta) => !lleno(valorEn(dict, ruta)));
      expect(vacios).toEqual([]);
    });

    it(`${locale} nombra los diez planetas de la rueda`, () => {
      expect(PLANET_NAMES[locale]).toHaveLength(10);
      expect(PLANET_NAMES[locale].every((n) => n.trim())).toBe(true);
    });

    it(`${locale} nombra todos los aspectos que dibuja la carta`, () => {
      // Si falta uno, la tabla muestra el nombre crudo del motor en inglés.
      for (const aspecto of Object.keys(ASPECT_GLYPHS)) {
        expect(ASPECT_NAMES[locale][aspecto], `${aspecto} en ${locale}`).toBeTruthy();
      }
    });

    it(`${locale} traduce los cuerpos que devuelve el backend`, () => {
      const delMotor = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter",
        "Saturn", "Uranus", "Neptune", "Pluto", "Chiron", "Mean_Lilith",
        "True_North_Lunar_Node", "True_South_Lunar_Node"];
      for (const key of delMotor) {
        expect(PLANET_NAME_BY_KEY[locale][key], `${key} en ${locale}`).toBeTruthy();
      }
    });
  }
});

describe("pricing", () => {
  // Task 16: la home ya no promete "tres cartas gratis y después lo mismo
  // pago" — son dos productos distintos (lectura breve gratis vs. informe
  // completo pago). Estos tests protegen que el copy diga eso, no sólo que
  // las claves existan o tengan contenido (eso ya lo cubre "no deja ningún
  // texto vacío" y pasaría con cualquier texto).

  it("el copy de precios no promete una carta entera gratis", () => {
    // La tabla vieja decía "1 crédito" como precio de cada carta nueva: ese
    // precio por unidad ya no existe, ahora se paga el informe completo.
    for (const locale of LOCALES) {
      const dict = getDict(locale);
      expect(
        dict.pricing.terms.some((t) => /1 crédito|1 credit/i.test(t.value)),
      ).toBe(false);
    }
  });

  it("la tabla de precios nombra los dos productos, no una versión recortada del mismo", () => {
    // Tiene que haber una fila gratis (la lectura breve) Y una fila con el
    // precio real del informe completo: si sólo hubiera "Gratis" en todos
    // lados, o sólo un precio sin nada gratis, seguiría siendo un producto.
    for (const locale of LOCALES) {
      const dict = getDict(locale);
      const hayFilaGratis = dict.pricing.terms.some((t) =>
        /gratis|free|grátis/i.test(t.value),
      );
      const hayFilaInformePago = dict.pricing.terms.some(
        (t) => t.value === dict.pricing.price,
      );
      expect(hayFilaGratis, `${locale}: falta una fila gratis`).toBe(true);
      expect(hayFilaInformePago, `${locale}: falta el precio del informe`).toBe(true);
    }
  });

  it("el precio no describe una carta cualquiera, describe el informe completo de ocho secciones", () => {
    // Si priceNote sólo dijera "por carta" seguiría sonando al producto
    // viejo. Tiene que nombrar el informe completo y su tamaño real.
    for (const locale of LOCALES) {
      const dict = getDict(locale);
      expect(/ocho secciones|eight sections|oito seções/i.test(dict.pricing.priceNote)).toBe(
        true,
      );
    }
  });

  it("los tres idiomas tienen las claves de los dos derechos", () => {
    for (const locale of LOCALES) {
      const dict = getDict(locale);
      expect(dict.auth.derechosBreve).toBeTruthy();
      expect(dict.auth.derechosInforme).toBeTruthy();
    }
  });

  it("la cuenta ya no dice que se compra dentro de la app", () => {
    // La app está apagada (APP_AUTH_ENABLED=0) y la venta va por la web: el
    // texto viejo mentía sobre dónde se compra.
    for (const locale of LOCALES) {
      const dict = getDict(locale);
      expect(/dentro de la app|inside the app|dentro do app/i.test(dict.auth.comprarNota)).toBe(
        false,
      );
    }
  });

  it("ninguna pantalla dice la palabra 'crédito'", () => {
    // Task 16: el backend ya no tiene créditos, tiene derechos sobre
    // productos concretos. Este test es el que caza cualquier reaparición
    // futura de la palabra en el copy (no en identificadores de código).
    //
    // OJO: sólo mira los diccionarios. Los documentos legales viven en
    // `content/legal/` y NO pasan por acá — ahí sobrevivieron siete menciones
    // a "crédito" por idioma hasta el 03-09-2026, más las tiendas y
    // RevenueCat. Eso lo cubre `scripts/check-legal.mjs`, que corre en el
    // mismo gate; el test de abajo es el que ancla que ese chequeo exista.
    for (const locale of LOCALES) {
      const dict = getDict(locale);
      const textos = JSON.stringify(dict);
      expect(/crédit|credit/i.test(textos), `${locale}: aparece "crédito"/"credit"`).toBe(false);
    }
  });

  it("ninguna pantalla promete una app en las tiendas", () => {
    // La home anunciaba las apps con badges de App Store y Google Play y un
    // "Próximamente". La app no se está construyendo: el producto es la web, y
    // prometer una descarga que no llega manda al visitante a un callejón.
    // Si la app vuelve, este test se borra junto con el que lo decida.
    for (const locale of LOCALES) {
      const textos = JSON.stringify(getDict(locale));
      expect(
        /app store|google play|play store/i.test(textos),
        `${locale}: el copy promete una app de tienda`,
      ).toBe(false);
    }
  });

  it("ninguna pantalla manda al visitante a hacer algo 'en la app'", () => {
    // Había cuatro: borrar la cuenta, borrar una carta, el lede del login y la
    // pregunta de la FAQ. Todas mandaban a una app que no existe a hacer algo
    // que la web ya hace.
    for (const locale of LOCALES) {
      const textos = JSON.stringify(getDict(locale));
      expect(
        /(desde|en|pelo|do) la app|(from|in) the app|pelo app/i.test(textos),
        `${locale}: el copy manda a hacer algo "en la app"`,
      ).toBe(false);
    }
  });

  it("no promete un login con Apple, que en la web no existe", () => {
    // `APP_AUTH_ENABLED=0`: la web entra sólo con Google. La pantalla de
    // `/entrar` no tiene botón de Apple, pero la FAQ lo prometía.
    for (const locale of LOCALES) {
      const textos = JSON.stringify(getDict(locale));
      expect(/apple/i.test(textos), `${locale}: el copy promete login con Apple`).toBe(false);
    }
  });
});

describe("isLocale", () => {
  it("acepta los tres idiomas y rechaza cualquier otra cosa", () => {
    expect(LOCALES.every(isLocale)).toBe(true);
    expect(isLocale("fr")).toBe(false);
    expect(isLocale("")).toBe(false);
    expect(isLocale("ES")).toBe(false);
  });
});

describe("negociarIdioma", () => {
  it("toma el idioma sin importar la región", () => {
    expect(negociarIdioma("pt-BR")).toBe("pt");
    expect(negociarIdioma("en-GB")).toBe("en");
    expect(negociarIdioma("es-419")).toBe("es");
  });

  it("respeta los pesos, no el orden de aparición", () => {
    // Chrome manda la lista ya ordenada, pero el RFC no lo exige y hay clientes
    // que no lo hacen.
    expect(negociarIdioma("en;q=0.4,pt;q=0.9")).toBe("pt");
    expect(negociarIdioma("es;q=0.2,en;q=0.8")).toBe("en");
  });

  it("una entrada sin q vale 1 y le gana a las que sí lo declaran", () => {
    expect(negociarIdioma("en,pt;q=0.9")).toBe("en");
  });

  it("salta los idiomas que no tenemos", () => {
    expect(negociarIdioma("de,fr;q=0.9,pt;q=0.5")).toBe("pt");
  });

  it("q=0 significa que ese idioma NO lo quiere", () => {
    expect(negociarIdioma("es;q=0,en;q=0.5")).toBe("en");
  });

  it("cae en español ante lo que no entiende", () => {
    expect(negociarIdioma(null)).toBe("es");
    expect(negociarIdioma("")).toBe("es");
    expect(negociarIdioma("de,fr")).toBe("es");
    expect(negociarIdioma("*")).toBe("es");
    expect(negociarIdioma(";;;,,,")).toBe("es");
  });

  it("con el peso ilegible respeta igual el idioma pedido", () => {
    // El `q` roto se ignora y la entrada vale 1. Descartarla sería mandar a
    // español a alguien que pidió inglés por culpa de un carácter suelto.
    expect(negociarIdioma("en;q=basura")).toBe("en");
  });

  it("no le importan las mayúsculas ni los espacios", () => {
    expect(negociarIdioma("PT-br, EN;q=0.9")).toBe("pt");
    expect(negociarIdioma("  en ;  q=0.9 ")).toBe("en");
  });
});
