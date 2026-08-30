import { describe, expect, it } from "vitest";

import {
  ASPECT_GLYPHS,
  ASPECT_NAMES,
  LOCALES,
  PLANET_NAMES,
  PLANET_NAME_BY_KEY,
  getDict,
  isLocale,
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

describe("credits", () => {
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
        dict.credits.terms.some((t) => /1 crédito|1 credit/i.test(t.value)),
      ).toBe(false);
    }
  });

  it("la tabla de créditos nombra los dos productos, no una versión recortada del mismo", () => {
    // Tiene que haber una fila gratis (la lectura breve) Y una fila con el
    // precio real del informe completo: si sólo hubiera "Gratis" en todos
    // lados, o sólo un precio sin nada gratis, seguiría siendo un producto.
    for (const locale of LOCALES) {
      const dict = getDict(locale);
      const hayFilaGratis = dict.credits.terms.some((t) =>
        /gratis|free|grátis/i.test(t.value),
      );
      const hayFilaInformePago = dict.credits.terms.some(
        (t) => t.value === dict.credits.price,
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
      expect(/ocho secciones|eight sections|oito seções/i.test(dict.credits.priceNote)).toBe(
        true,
      );
    }
  });

  it("los tres idiomas tienen las claves de los dos saldos", () => {
    for (const locale of LOCALES) {
      const dict = getDict(locale);
      expect(dict.auth.freeCredits).toBeTruthy();
      expect(dict.auth.paidCredits).toBeTruthy();
    }
  });

  it("la cuenta ya no dice que los créditos se compran dentro de la app", () => {
    // La app está apagada (APP_AUTH_ENABLED=0) y la venta va por la web: el
    // texto viejo mentía sobre dónde se compra.
    for (const locale of LOCALES) {
      const dict = getDict(locale);
      expect(/dentro de la app|inside the app|dentro do app/i.test(dict.auth.buyInApp)).toBe(
        false,
      );
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
