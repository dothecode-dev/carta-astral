import type { BodyKey, Positions } from "./ephemeris";

// El cielo lo calcula el backend con Swiss Ephemeris, el mismo motor con el que
// se arman las cartas. El pedido se hace desde el servidor de Next, no desde el
// navegador: así no hace falta CORS, el backend recibe una petición por
// revalidación en vez de una por visitante, y la rueda llega en el HTML.
//
// Si el backend no responde, la portada no se cae: el cliente calcula con
// elementos orbitales (lib/ephemeris.ts), que para un dibujo de 400 píxeles es
// indistinguible.

// Sin prefijo NEXT_PUBLIC_ a propósito: este fetch sólo corre en el servidor,
// así que la variable no tiene por qué viajar en el bundle del navegador.
const API_URL = process.env.API_URL ?? "https://api.cartaastral.dothecode.com";

const REVALIDATE_SECONDS = 60;
const TIMEOUT_MS = 3000;

type ApiBody = {
  name: string;
  sign: string;
  longitude: number;
  retrograde: boolean;
};

export type Sky = {
  moment: string;
  positions: Positions;
};

/** El backend nombra los cuerpos en inglés y capitalizados. */
const KEY_BY_NAME: Record<string, BodyKey> = {
  Sun: "sun",
  Moon: "moon",
  Mercury: "mercury",
  Venus: "venus",
  Mars: "mars",
  Jupiter: "jupiter",
  Saturn: "saturn",
  Uranus: "uranus",
  Neptune: "neptune",
};

export async function fetchSky(): Promise<Sky | null> {
  try {
    const res = await fetch(`${API_URL}/api/sky/`, {
      next: { revalidate: REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) return null;

    const data: { moment: string; bodies: ApiBody[] } = await res.json();
    const positions = {} as Positions;
    for (const body of data.bodies) {
      const key = KEY_BY_NAME[body.name];
      if (key) positions[key] = body.longitude;
    }

    // Plutón no entra en la rueda; si falta cualquiera de los otros, el dibujo
    // saldría incompleto y es preferible el cálculo local.
    if (Object.keys(positions).length !== Object.keys(KEY_BY_NAME).length) return null;

    return { moment: data.moment, positions };
  } catch {
    // Backend caído, lento o mal configurado: la portada sigue funcionando.
    return null;
  }
}
