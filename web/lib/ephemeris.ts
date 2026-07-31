// Posiciones geocéntricas de Sol, Luna y los planetas para un instante dado.
//
// Elementos orbitales de Schlyter: precisión del orden de un minuto de arco,
// suficiente para la rueda de la portada, que es una demostración y no una carta
// natal. Las cartas de verdad las calcula el backend con Swiss Ephemeris
// (backend/core/ephemeris.py), y cuando exista el endpoint público esta rueda
// va a leer de ahí.

const RAD = Math.PI / 180;

const rev = (x: number) => x - Math.floor(x / 360) * 360;
const sin = (deg: number) => Math.sin(deg * RAD);
const cos = (deg: number) => Math.cos(deg * RAD);

export type BodyKey =
  | "sun" | "moon" | "mercury" | "venus" | "mars"
  | "jupiter" | "saturn" | "uranus" | "neptune";

export type Positions = Record<BodyKey, number>;

type Elements = { N: number; i: number; w: number; a: number; e: number; M: number };

/** Días desde el epoch de Schlyter (1999-12-31 00:00 UT), con fracción. */
function dayNumber(date: Date): number {
  const y = date.getUTCFullYear();
  const m = date.getUTCMonth() + 1;
  const d = date.getUTCDate();
  const h = date.getUTCHours() + date.getUTCMinutes() / 60 + date.getUTCSeconds() / 3600;
  return (
    367 * y -
    Math.floor((7 * (y + Math.floor((m + 9) / 12))) / 4) +
    Math.floor((275 * m) / 9) +
    d -
    730530 +
    h / 24
  );
}

const ELEMENTS: Record<BodyKey, (d: number) => Elements> = {
  sun: (d) => ({ N: 0, i: 0, w: 282.9404 + 4.70935e-5 * d, a: 1, e: 0.016709 - 1.151e-9 * d, M: 356.047 + 0.9856002585 * d }),
  moon: (d) => ({ N: 125.1228 - 0.0529538083 * d, i: 5.1454, w: 318.0634 + 0.1643573223 * d, a: 60.2666, e: 0.0549, M: 115.3654 + 13.0649929509 * d }),
  mercury: (d) => ({ N: 48.3313 + 3.24587e-5 * d, i: 7.0047 + 5.0e-8 * d, w: 29.1241 + 1.01444e-5 * d, a: 0.387098, e: 0.205635 + 5.59e-10 * d, M: 168.6562 + 4.0923344368 * d }),
  venus: (d) => ({ N: 76.6799 + 2.4659e-5 * d, i: 3.3946 + 2.75e-8 * d, w: 54.891 + 1.38374e-5 * d, a: 0.72333, e: 0.006773 - 1.302e-9 * d, M: 48.0052 + 1.6021302244 * d }),
  mars: (d) => ({ N: 49.5574 + 2.11081e-5 * d, i: 1.8497 - 1.78e-8 * d, w: 286.5016 + 2.92961e-5 * d, a: 1.523688, e: 0.093405 + 2.516e-9 * d, M: 18.6021 + 0.5240207766 * d }),
  jupiter: (d) => ({ N: 100.4542 + 2.76854e-5 * d, i: 1.303 - 1.557e-7 * d, w: 273.8777 + 1.64505e-5 * d, a: 5.20256, e: 0.048498 + 4.469e-9 * d, M: 19.895 + 0.0830853001 * d }),
  saturn: (d) => ({ N: 113.6634 + 2.3898e-5 * d, i: 2.4886 - 1.081e-7 * d, w: 339.3939 + 2.97661e-5 * d, a: 9.55475, e: 0.055546 - 9.499e-9 * d, M: 316.967 + 0.0334442282 * d }),
  uranus: (d) => ({ N: 74.0005 + 1.3978e-5 * d, i: 0.7733 + 1.9e-8 * d, w: 96.6612 + 3.0565e-5 * d, a: 19.18171 - 1.55e-8 * d, e: 0.047318 + 7.45e-9 * d, M: 142.5905 + 0.011725806 * d }),
  neptune: (d) => ({ N: 131.7806 + 3.0173e-5 * d, i: 1.77 - 2.55e-7 * d, w: 272.8461 - 6.027e-6 * d, a: 30.05826 + 3.313e-8 * d, e: 0.008606 + 2.15e-9 * d, M: 260.2471 + 0.005995147 * d }),
};

/** Resuelve Kepler y devuelve la posición en coordenadas eclípticas rectangulares. */
function orbital(el: Elements): { r: number; x: number; y: number } {
  const M = rev(el.M);
  let E = M + (180 / Math.PI) * el.e * sin(M) * (1 + el.e * cos(M));
  for (let k = 0; k < 3; k++) {
    E = E - (E - (180 / Math.PI) * el.e * sin(E) - M) / (1 - el.e * cos(E));
  }
  const xv = el.a * (cos(E) - el.e);
  const yv = el.a * Math.sqrt(1 - el.e * el.e) * sin(E);
  const v = rev(Math.atan2(yv, xv) / RAD);
  const r = Math.sqrt(xv * xv + yv * yv);
  const u = v + el.w;
  return {
    r,
    x: r * (cos(el.N) * cos(u) - sin(el.N) * sin(u) * cos(el.i)),
    y: r * (sin(el.N) * cos(u) + cos(el.N) * sin(u) * cos(el.i)),
  };
}

export function positions(date: Date): Positions {
  const d = dayNumber(date);

  const sunEl = ELEMENTS.sun(d);
  const sun = orbital(sunEl);
  const lonSun = rev(Math.atan2(sun.y, sun.x) / RAD);

  // La Luna sale ya geocéntrica; se le aplican las tres perturbaciones mayores,
  // que valen más de un grado y se notan a simple vista en la rueda.
  const moonEl = ELEMENTS.moon(d);
  const moon = orbital(moonEl);
  const meanSun = rev(sunEl.M + sunEl.w);
  const meanMoon = rev(moonEl.N + moonEl.w + moonEl.M);
  const elongation = rev(meanMoon - meanSun);
  const lonMoon = rev(
    rev(Math.atan2(moon.y, moon.x) / RAD) -
      1.274 * sin(rev(moonEl.M) - 2 * elongation) +
      0.658 * sin(2 * elongation) -
      0.186 * sin(rev(sunEl.M)),
  );

  const out = { sun: lonSun, moon: lonMoon } as Positions;

  const planets: BodyKey[] = ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"];
  for (const key of planets) {
    const p = orbital(ELEMENTS[key](d));
    // Heliocéntrico → geocéntrico: se suma el vector Tierra→Sol.
    const xg = p.x + sun.r * cos(lonSun);
    const yg = p.y + sun.r * sin(lonSun);
    out[key] = rev(Math.atan2(yg, xg) / RAD);
  }

  return out;
}

export const BODIES: { key: BodyKey; glyph: string }[] = [
  { key: "sun", glyph: "☉" },
  { key: "moon", glyph: "☽" },
  { key: "mercury", glyph: "☿" },
  { key: "venus", glyph: "♀" },
  { key: "mars", glyph: "♂" },
  { key: "jupiter", glyph: "♃" },
  { key: "saturn", glyph: "♄" },
  { key: "uranus", glyph: "♅" },
  { key: "neptune", glyph: "♆" },
];

export const SIGNS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"];

/** Grados y minutos dentro del signo, con cero a la izquierda. */
export function formatDegree(lon: number): string {
  const inSign = lon % 30;
  const deg = Math.floor(inSign);
  const min = Math.floor((inSign - deg) * 60);
  return `${String(deg).padStart(2, "0")}°${String(min).padStart(2, "0")}′`;
}

export function signOf(lon: number): string {
  return SIGNS[Math.floor(lon / 30)];
}
