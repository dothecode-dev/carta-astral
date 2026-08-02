import { describe, expect, it } from "vitest";

import { BODIES, formatDegree, positions, signOf } from "@/lib/ephemeris";

// La rueda del cielo de la home la calcula el navegador, con los elementos
// orbitales de Schlyter, porque pedirle cada posición al backend sería absurdo
// para un adorno. Pero adorno o no, dice dónde está cada planeta: si se va de
// signo, miente.
//
// Los valores esperados salen de las efemérides Swiss del backend
// (core.ephemeris.sky_now), que es lo que se usa para las cartas de verdad.
const REALES: Record<string, Record<string, number>> = {
  "2026-01-01T12:00:00Z": {
    sun: 281.078, moon: 74.225, mercury: 269.415, venus: 279.836, mars: 283.071,
    jupiter: 111.292, saturn: 356.197, uranus: 57.936, neptune: 359.513,
  },
  "1989-07-14T23:45:00Z": {
    sun: 112.487, moon: 246.878, mercury: 108.49, venus: 139.036, mars: 137.709,
    jupiter: 86.606, saturn: 279.713, uranus: 272.549, neptune: 280.679,
  },
  "2000-06-21T06:00:00Z": {
    sun: 90.167, moon: 317.07, mercury: 109.793, venus: 92.854, mars: 93.168,
    jupiter: 58.064, saturn: 55.569, uranus: 320.539, neptune: 306.092,
  },
};

/** Diferencia angular más corta entre dos longitudes, en grados. */
function apartaBy(a: number, b: number): number {
  const d = Math.abs(a - b) % 360;
  return d > 180 ? 360 - d : d;
}

describe("positions", () => {
  for (const [iso, esperado] of Object.entries(REALES)) {
    it(`sigue a las efemérides reales en ${iso.slice(0, 10)}`, () => {
      const calculado = positions(new Date(iso));

      for (const [cuerpo, real] of Object.entries(esperado)) {
        const mio = calculado[cuerpo as keyof typeof calculado];
        // Un grado y medio: Schlyter es una aproximación, y a esta escala la
        // rueda no distingue más que eso. Pasado ese margen ya no es ruido.
        expect(apartaBy(mio, real), `${cuerpo} en ${iso}`).toBeLessThan(1.5);
      }
    });
  }

  it("nunca se sale del círculo", () => {
    for (let mes = 0; mes < 12; mes++) {
      const p = positions(new Date(Date.UTC(2026, mes, 15, 3, 0, 0)));
      for (const { key } of BODIES) {
        expect(p[key]).toBeGreaterThanOrEqual(0);
        expect(p[key]).toBeLessThan(360);
      }
    }
  });

  it("da el mismo signo que las efemérides", () => {
    const calculado = positions(new Date("1989-07-14T23:45:00Z"));
    // Sol en Cáncer, Luna en Sagitario esa noche.
    expect(signOf(calculado.sun)).toBe("♋");
    expect(signOf(calculado.moon)).toBe("♐");
  });
});

describe("formatDegree", () => {
  it("cuenta los grados dentro del signo, no desde Aries", () => {
    expect(formatDegree(0)).toBe("00°00′");
    expect(formatDegree(112.487)).toBe("22°29′");
    expect(formatDegree(359.99)).toBe("29°59′");
  });
});

describe("signOf", () => {
  it("reparte los doce signos de treinta en treinta", () => {
    expect(signOf(0)).toBe("♈");
    expect(signOf(29.99)).toBe("♈");
    expect(signOf(30)).toBe("♉");
    expect(signOf(359.9)).toBe("♓");
  });
});
