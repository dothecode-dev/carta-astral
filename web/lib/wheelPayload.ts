import { buildWheel } from "astra-wheel";

import type { SampleChart } from "@/content/sample-chart";
import { toWheelInput } from "@/lib/chart";
import { PLANET_GLYPHS } from "@/lib/i18n";

// Lo que el navegador le manda al backend para que dibuje la rueda del PDF.
//
// Viajan números y glifos, nunca markup: el SVG lo construye Django. Es la
// diferencia entre generar markup —una operación segura— y filtrar el que mandó
// un cliente, que es una operación que un día tiene un agujero.
//
// La geometría es la misma que ve la persona en pantalla porque sale del mismo
// `buildWheel`. Si el backend la recalculara, la rueda del PDF podría dejar de
// coincidir con la de la web sin que nadie se entere.

const SIGNS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"];
const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
const ANGLE_LABEL: Record<string, string> = { Ascendant: "ASC", Medium_Coeli: "MC" };

const HARD = new Set(["square", "opposition"]);
const SOFT = new Set(["trine", "sextile"]);

/** El tamaño con el que se calcula la geometría del PDF. Fijo: el documento no
 *  cambia de ancho según la pantalla de quien lo pide. */
const PDF_SIZE = 620;
const PDF_GLYPH_PX = 15;

export type PdfWheel = {
  view_box: number;
  center: number;
  rings: { outer: number; signs: number; houses: number; aspect: number };
  signs: { glyph: string; x: number; y: number }[];
  cusps: {
    label: string; axis: boolean;
    x1: number; y1: number; x2: number; y2: number;
    label_x: number; label_y: number;
  }[];
  aspect_lines: { tone: "soft" | "hard" | "neutral"; x1: number; y1: number; x2: number; y2: number }[];
  angles: { label: string; x: number; y: number }[];
  bodies: {
    glyph: string; accent: boolean; x: number; y: number;
    tick_x1: number; tick_y1: number; tick_x2: number; tick_y2: number;
    leader_x1: number; leader_y1: number; leader_x2: number; leader_y2: number;
  }[];
};

function tone(type: string): "soft" | "hard" | "neutral" {
  if (HARD.has(type)) return "hard";
  if (SOFT.has(type)) return "soft";
  return "neutral";
}

/**
 * La geometría de la rueda, lista para que el backend la pinte.
 *
 * Los desplazamientos verticales de los textos van aplicados acá: en SVG la `y`
 * de un `<text>` es la línea base, no el centro del glifo, y quien sabe cuánto
 * hay que correr cada cosa es quien conoce los tamaños de fuente del documento.
 */
export function toPdfWheel(chart: SampleChart): PdfWheel {
  const wheel = buildWheel(toWheelInput(chart), { size: PDF_SIZE, glyphPx: PDF_GLYPH_PX });

  return {
    view_box: wheel.viewBox,
    center: wheel.center,
    rings: {
      outer: wheel.rings.outer,
      signs: wheel.rings.signs,
      houses: wheel.rings.houses,
      aspect: wheel.rings.aspect,
    },
    signs: wheel.signs.map((s) => ({
      glyph: SIGNS[s.index],
      x: s.at.x,
      y: s.at.y + 6,
    })),
    cusps: wheel.cusps.map((c) => ({
      label: ROMAN[c.index],
      axis: c.axis,
      x1: c.line.x1, y1: c.line.y1, x2: c.line.x2, y2: c.line.y2,
      label_x: c.label.x, label_y: c.label.y + 4,
    })),
    aspect_lines: wheel.aspectLines.map((a) => ({
      tone: tone(a.type),
      x1: a.line.x1, y1: a.line.y1, x2: a.line.x2, y2: a.line.y2,
    })),
    angles: wheel.angles.map((a) => ({
      label: ANGLE_LABEL[a.name] ?? a.name,
      x: a.at.x,
      y: a.at.y + 3,
    })),
    bodies: wheel.bodies.map((b) => ({
      glyph: PLANET_GLYPHS[b.name] ?? "·",
      accent: b.name === "Sun",
      x: b.draw.x,
      y: b.draw.y + 6,
      tick_x1: b.tick.x1, tick_y1: b.tick.y1, tick_x2: b.tick.x2, tick_y2: b.tick.y2,
      leader_x1: b.leader.x1, leader_y1: b.leader.y1,
      leader_x2: b.leader.x2, leader_y2: b.leader.y2,
    })),
  };
}
