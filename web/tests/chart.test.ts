import { describe, expect, it } from "vitest";

import { type ApiChart, toWheel, toWheelInput } from "@/lib/chart";

// La rueda no se dibuja con lo que manda el backend sino con una traducción.
// Si esa traducción falla en silencio, la carta se dibuja mal y nadie se entera:
// una rueda torcida sigue pareciendo una rueda.

const HOUSE_ORDER = [
  "First_House", "Second_House", "Third_House", "Fourth_House",
  "Fifth_House", "Sixth_House", "Seventh_House", "Eighth_House",
  "Ninth_House", "Tenth_House", "Eleventh_House", "Twelfth_House",
];

function chart(over: Partial<ApiChart["data"]> = {}): ApiChart {
  return {
    id: "x",
    interpretation_langs: [],
    birth: { name: null, date: "1989-07-14", time: "23:45", time_known: true, place_label: "Rosario" },
    data: {
      placements: [
        { name: "Sun", sign: "Can", abs_pos: 112.487, house: "Fifth_House", retrograde: false },
        { name: "Moon", sign: "Sag", abs_pos: 246.878, house: "Tenth_House", retrograde: false },
        { name: "Saturn", sign: "Cap", abs_pos: 279.713, house: "Eleventh_House", retrograde: true },
        // Sale en las tablas pero no en la rueda.
        { name: "Chiron", sign: "Can", abs_pos: 100, house: "Fifth_House", retrograde: false },
      ],
      houses: HOUSE_ORDER.map((name, i) => ({ name, abs_pos: i * 30 })),
      angles: [
        { name: "Ascendant", abs_pos: 0 },
        { name: "Medium_Coeli", abs_pos: 270 },
      ],
      aspects: [
        { p1: "Sun", p2: "Moon", aspect: "trine", orbit: 1.2 },
        { p1: "Sun", p2: "Chiron", aspect: "conjunction", orbit: 0.4 },
      ],
      flags: {
        moon_approximate: false,
        precision_degraded: false,
        bodies_missing: false,
        house_system_fallback: false,
      },
      ...over,
    },
  };
}

describe("toWheel", () => {
  it("traduce planetas, casas y ángulos", () => {
    const w = toWheel(chart())!;

    expect(w.houses).toHaveLength(12);
    expect(w.houses[0]).toBe(0);
    expect(w.angles.Ascendant).toBe(0);
    expect(w.angles.Medium_Coeli).toBe(270);
    expect(w.planets.map((p) => p.name)).toEqual(["Sun", "Moon", "Saturn", "Chiron"]);
    expect(w.planets.find((p) => p.name === "Saturn")?.retro).toBe(true);
  });

  it("deduce el Descendente y el Fondo de Cielo cuando no vienen", () => {
    const w = toWheel(chart())!;
    expect(w.angles.Descendant).toBe(180);
    expect(w.angles.Imum_Coeli).toBe(90);
  });

  it("respeta los ángulos que sí manda el backend", () => {
    const w = toWheel(
      chart({
        angles: [
          { name: "Ascendant", abs_pos: 10 },
          { name: "Medium_Coeli", abs_pos: 280 },
          { name: "Descendant", abs_pos: 190 },
          { name: "Imum_Coeli", abs_pos: 100 },
        ],
      }),
    )!;
    expect(w.angles.Descendant).toBe(190);
    expect(w.angles.Imum_Coeli).toBe(100);
  });

  it("dibuja los catorce cuerpos del motor, no diez", () => {
    // Quirón, los nodos y Lilith se calculaban y se descartaban acá: la misma
    // carta se veía distinta en la web que en el PDF. Cambiado el 2026-08-03.
    const w = toWheel(chart())!;
    expect(w.planets.some((p) => p.name === "Chiron")).toBe(true);
  });

  it("deja fuera los aspectos de un cuerpo que no se dibuja", () => {
    // Si no, quedarían líneas hacia la nada.
    const w = toWheel(chart())!;
    for (const a of w.aspects) {
      expect(w.planets.some((p) => p.name === a.a)).toBe(true);
      expect(w.planets.some((p) => p.name === a.b)).toBe(true);
    }
  });

  it("no dibuja rueda sin hora de nacimiento", () => {
    // Sin hora no hay Ascendente, y sin Ascendente la rueda no se puede orientar.
    expect(toWheel(chart({ houses: null, angles: null }))).toBeNull();
  });

  it("no dibuja rueda si falta una cúspide", () => {
    expect(toWheel(chart({ houses: HOUSE_ORDER.slice(0, 11).map((name, i) => ({ name, abs_pos: i * 30 })) }))).toBeNull();
  });

  it("no dibuja rueda si falta el Ascendente", () => {
    expect(toWheel(chart({ angles: [{ name: "Medium_Coeli", abs_pos: 270 }] }))).toBeNull();
  });

  it("ubica en la casa I un planeta que vino sin casa", () => {
    const w = toWheel(
      chart({
        placements: [{ name: "Sun", sign: "Can", abs_pos: 112, house: null, retrograde: false }],
      }),
    )!;
    expect(w.planets[0].house).toBe("First_House");
  });
});

describe("toWheelInput", () => {
  it("orienta por el Ascendente, no por la primera cuspide", () => {
    // Whole Sign: la casa 1 arranca en 0 grados del signo, el Ascendente cae adentro.
    const w = toWheel(chart())!;
    const wholeSign = { ...w, houses: [330, ...w.houses.slice(1)] };
    expect(toWheelInput(wholeSign).ascendant).toBe(w.angles.Ascendant);
    expect(toWheelInput(wholeSign).ascendant).not.toBe(330);
  });

  it("pasa todos los cuerpos y aspectos que recibe", () => {
    const w = toWheel(chart())!;
    const input = toWheelInput(w);
    expect(input.bodies).toHaveLength(w.planets.length);
    expect(input.aspects).toHaveLength(w.aspects.length);
    expect(input.cusps).toHaveLength(12);
  });
});
