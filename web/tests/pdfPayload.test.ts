import { describe, expect, it } from "vitest";

import { SAMPLE_CHART } from "@/content/sample-chart";
import type { ApiChart } from "@/lib/chart";
import { getDict } from "@/lib/i18n";
import { buildPdfPayload } from "@/lib/pdfPayload";
import { toPdfWheel } from "@/lib/wheelPayload";

// Lo que se le manda al backend son datos, no markup. Estos tests cuidan las dos
// mitades de esa decisión: que la geometría viaje completa (si falta algo, la
// rueda del PDF deja de ser la que se ve en pantalla) y que los rótulos vayan
// traducidos, que es lo que evita duplicar el diccionario en Python.

const HOUSES = [
  "First_House", "Second_House", "Third_House", "Fourth_House",
  "Fifth_House", "Sixth_House", "Seventh_House", "Eighth_House",
  "Ninth_House", "Tenth_House", "Eleventh_House", "Twelfth_House",
];

function apiChart(over: Partial<ApiChart["data"]> = {}): ApiChart {
  return {
    id: "89151d40-e263-4d34-81e0-2fb434f70243",
    interpretation_langs: [],
    birth: {
      name: "Camila",
      date: "1994-03-12",
      time: "07:20",
      time_known: true,
      lat: -34.6118,
      lng: -58.396,
      tz_name: "America/Argentina/Buenos_Aires",
      place_label: "Buenos Aires, Argentina",
    },
    data: {
      placements: SAMPLE_CHART.planets.map((p) => ({
        name: p.name,
        sign: "",
        abs_pos: p.lon,
        house: p.house,
        retrograde: p.retro,
      })),
      houses: HOUSES.map((name, i) => ({ name, abs_pos: SAMPLE_CHART.houses[i] })),
      angles: [
        { name: "Ascendant", abs_pos: SAMPLE_CHART.angles.Ascendant },
        { name: "Medium_Coeli", abs_pos: SAMPLE_CHART.angles.Medium_Coeli },
      ],
      aspects: SAMPLE_CHART.aspects.map((a) => ({
        p1: a.a, p2: a.b, aspect: a.type, orbit: a.orb,
      })),
      flags: {
        moon_approximate: false,
        precision_degraded: false,
        bodies_missing: false,
        house_system_fallback: false,
      },
      ...over,
    },
  } as ApiChart;
}

describe("toPdfWheel", () => {
  const wheel = toPdfWheel(SAMPLE_CHART);

  it("lleva un elemento por cada cuerpo, cúspide y aspecto dibujable", () => {
    expect(wheel.bodies).toHaveLength(SAMPLE_CHART.planets.length);
    expect(wheel.cusps).toHaveLength(12);
    expect(wheel.signs).toHaveLength(12);

    // El paquete no traza los aspectos que tocan un eje (AC, MC, DC, IC): no
    // tienen un glifo en el anillo del que salir. La carta de ejemplo tiene 62
    // aspectos y sólo 35 entre cuerpos, así que contar los de entrada daría un
    // número que la rueda nunca dibujó.
    const cuerpos = new Set(SAMPLE_CHART.planets.map((p) => p.name));
    const entreCuerpos = SAMPLE_CHART.aspects.filter(
      (a) => cuerpos.has(a.a) && cuerpos.has(a.b),
    );
    expect(wheel.aspect_lines).toHaveLength(entreCuerpos.length);
  });

  it("sólo manda números finitos: el backend los escribe como coordenadas", () => {
    const numeros = [
      wheel.view_box, wheel.center,
      ...Object.values(wheel.rings),
      ...wheel.bodies.flatMap((b) => [b.x, b.y, b.tick_x1, b.leader_y2]),
      ...wheel.cusps.flatMap((c) => [c.x1, c.label_y]),
      ...wheel.aspect_lines.flatMap((a) => [a.x1, a.y2]),
    ];
    for (const n of numeros) expect(Number.isFinite(n)).toBe(true);
  });

  it("el tono del aspecto es de una lista cerrada, no un color", () => {
    for (const linea of wheel.aspect_lines) {
      expect(["soft", "hard", "neutral"]).toContain(linea.tone);
    }
  });

  it("rotula los ejes y marca el Sol", () => {
    expect(wheel.angles.map((a) => a.label)).toContain("ASC");
    expect(wheel.bodies.filter((b) => b.accent)).toHaveLength(1);
  });
});

describe("buildPdfPayload", () => {
  it("manda los rótulos traducidos, que es lo que evita duplicar el diccionario", () => {
    const es = buildPdfPayload(apiChart(), "es", getDict("es"));
    const en = buildPdfPayload(apiChart(), "en", getDict("en"));

    expect(es.positions.some((p) => p.name === "Júpiter")).toBe(true);
    expect(en.positions.some((p) => p.name === "Jupiter")).toBe(true);
    expect(es.aspects.some((a) => a.name === "Trígono")).toBe(true);
    expect(en.aspects.some((a) => a.name === "Trine")).toBe(true);
    expect(en.labels.made_with).toBe(getDict("en").share.madeWith);
  });

  it("pone los ejes antes que los cuerpos, como la tabla de la web", () => {
    const p = buildPdfPayload(apiChart(), "es", getDict("es"));
    expect(p.positions[0].glyph).toBe("AC");
    expect(p.positions[1].glyph).toBe("MC");
  });

  it("los aspectos con los ejes se rotulan AC y MC, no con un punto", () => {
    const p = buildPdfPayload(apiChart(), "es", getDict("es"));

    const conEjes = p.aspects.filter((a) => a.glyph.includes("AC") || a.glyph.includes("MC"));
    expect(conEjes.length).toBeGreaterThan(0);

    // Los dos extremos son siempre un cuerpo o un eje. El símbolo del medio es
    // otra cosa: el quintil no tiene glifo en ASPECT_GLYPHS y cae al punto, que
    // es lo que ya hace la matriz de aspectos de la web.
    for (const aspecto of p.aspects) {
      const [a, , b] = aspecto.glyph.split(" ");
      expect(a).not.toBe("·");
      expect(b).not.toBe("·");
    }
  });

  it("una carta sin nombre usa el rótulo traducido", () => {
    const chart = apiChart();
    chart.birth.name = null;
    expect(buildPdfPayload(chart, "es", getDict("es")).labels.chart_name).toBe(
      getDict("es").auth.unnamedChart,
    );
  });

  it("manda la matriz triangular, con el mismo orden que la web", () => {
    const m = buildPdfPayload(apiChart(), "es", getDict("es")).aspect_matrix!;

    // Los cuerpos primero y los ejes que participan, detrás: igual que AspectMatrix.
    expect(m.labels.slice(0, 3)).toEqual(["☉", "☽", "☿"]);
    expect(m.labels).toContain("AC");

    // Triangular: la fila i trae i+1 celdas, ni una más.
    expect(m.rows).toHaveLength(m.labels.length - 1);
    m.rows.forEach((fila, i) => expect(fila.cells).toHaveLength(i + 1));

    // Y los cruces ocupados traen glifo y tono, nunca un color.
    const ocupadas = m.rows.flatMap((f) => f.cells).filter(Boolean);
    expect(ocupadas.length).toBeGreaterThan(0);
    for (const celda of ocupadas) {
      expect(["soft", "hard", "neutral"]).toContain(celda!.tone);
      expect(celda!.glyph.length).toBeLessThanOrEqual(2);
    }
  });

  it("el tono sigue la misma lectura que la matriz de la web", () => {
    const chart = apiChart({
      aspects: [
        { p1: "Sun", p2: "Moon", aspect: "square", orbit: 1 },
        { p1: "Sun", p2: "Mercury", aspect: "trine", orbit: 1 },
        { p1: "Moon", p2: "Mercury", aspect: "conjunction", orbit: 1 },
      ],
    });
    const m = buildPdfPayload(chart, "es", getDict("es")).aspect_matrix!;
    const tonos = m.rows.flatMap((f) => f.cells).filter(Boolean).map((c) => c!.tone);
    expect(tonos).toContain("hard");     // cuadratura
    expect(tonos).toContain("soft");     // trígono
    expect(tonos).toContain("neutral");  // conjunción
  });

  it("una carta sin aspectos no manda matriz", () => {
    const p = buildPdfPayload(apiChart({ aspects: [] }), "es", getDict("es"));
    expect(p.aspect_matrix).toBeNull();
  });

  it("una carta sin hora viaja sin rueda, no a medias", () => {
    const p = buildPdfPayload(apiChart({ houses: null, angles: null }), "es", getDict("es"));
    expect(p.wheel).toBeNull();
    expect(p.positions.length).toBeGreaterThan(0);
  });
});
