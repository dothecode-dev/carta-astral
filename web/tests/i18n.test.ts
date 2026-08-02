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

describe("isLocale", () => {
  it("acepta los tres idiomas y rechaza cualquier otra cosa", () => {
    expect(LOCALES.every(isLocale)).toBe(true);
    expect(isLocale("fr")).toBe(false);
    expect(isLocale("")).toBe(false);
    expect(isLocale("ES")).toBe(false);
  });
});
