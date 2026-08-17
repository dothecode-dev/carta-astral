import { buildWheel } from "astra-wheel";

import type { SampleChart } from "@/content/sample-chart";
import { toWheelInput } from "@/lib/chart";
import { PLANET_GLYPHS } from "@/lib/i18n";

// El pintado de la rueda en un canvas, aparte del componente que lo muestra.
//
// Vivía dentro del `useEffect` de `NatalWheel`, y ahí sólo podía usarlo ese
// componente. La imagen para redes dibuja exactamente la misma rueda en otro
// canvas: sin sacarla de ahí, habría dos rutinas de dibujo que se irían
// separando de a poco.
//
// Sigue sin decidir colores: los recibe. Los tokens del tema son cosa de quien
// está en la página; el documento y la imagen usan la paleta de marca.

const SIGNS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"];
const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
const ANGLE_LABEL: Record<string, string> = { Ascendant: "ASC", Medium_Coeli: "MC" };

const HARD = new Set(["square", "opposition"]);
const SOFT = new Set(["trine", "sextile"]);

export type WheelInk = {
  ink: string;
  inkSoft: string;
  accent: string;
  hairline: string;
  hairStrong: string;
  dotted: string;
  mono: string;
};

/**
 * Dibuja la rueda de `chart` en `ctx`, ocupando un cuadrado de `size` píxeles.
 *
 * El tamaño real importa y por eso viaja al paquete: de él depende cuánto hay
 * que separar dos glifos que se pisan.
 */
export function drawWheel(
  ctx: CanvasRenderingContext2D,
  size: number,
  chart: SampleChart,
  ink: WheelInk,
): void {
  const glyphPx = size * 0.046;
  const wheel = buildWheel(toWheelInput(chart), { size, glyphPx });

  // Del viewBox del paquete a los píxeles del canvas.
  const k = size / wheel.viewBox;
  const cx = wheel.center * k;
  const mono = `${ink.mono || "ui-monospace"}, monospace`;

  const ring = (r: number, color: string, width: number, dash?: number[]) => {
    ctx.beginPath();
    ctx.setLineDash(dash ?? []);
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.arc(cx, cx, r * k, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
  };

  const line = (
    s: { x1: number; y1: number; x2: number; y2: number },
    color: string,
    w: number,
    dash?: number[],
  ) => {
    ctx.beginPath();
    ctx.setLineDash(dash ?? []);
    ctx.strokeStyle = color;
    ctx.lineWidth = w;
    ctx.moveTo(s.x1 * k, s.y1 * k);
    ctx.lineTo(s.x2 * k, s.y2 * k);
    ctx.stroke();
    ctx.setLineDash([]);
  };

  ring(wheel.rings.outer, ink.hairStrong, 1.25);
  ring(wheel.rings.signs, ink.hairline, 1);
  ring(wheel.rings.houses, ink.hairline, 1);
  ring(wheel.rings.aspect, ink.dotted, 1, [1.5, 4]);

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  // Signos: el glifo en el medio de la banda.
  ctx.font = `${size * 0.04}px ${mono}`;
  for (const s of wheel.signs) {
    ctx.fillStyle = ink.inkSoft;
    ctx.fillText(SIGNS[s.index], s.at.x * k, s.at.y * k);
  }

  // Casas: los cuatro ejes van marcados más fuerte que las cúspides intermedias.
  ctx.font = `${size * 0.026}px ${mono}`;
  for (const c of wheel.cusps) {
    line(c.line, c.axis ? ink.hairStrong : ink.hairline, c.axis ? 1.2 : 0.75, c.axis ? [] : [2, 3]);
    ctx.fillStyle = ink.inkSoft;
    ctx.fillText(ROMAN[c.index], c.label.x * k, c.label.y * k);
  }

  // Aspectos: el color dice si el ángulo suma o roza, no decora.
  for (const asp of wheel.aspectLines) {
    if (!HARD.has(asp.type) && !SOFT.has(asp.type)) continue;
    const duro = HARD.has(asp.type);
    ctx.globalAlpha = asp.orb < 2 ? 0.75 : 0.4;
    line(asp.line, duro ? ink.inkSoft : ink.accent, asp.orb < 2 ? 1.1 : 0.8, duro ? [3, 3] : []);
    ctx.globalAlpha = 1;
  }

  // Los rótulos de los ejes, por fuera del borde.
  ctx.font = `${size * 0.024}px ${mono}`;
  ctx.fillStyle = ink.accent;
  for (const a of wheel.angles) {
    ctx.fillText(ANGLE_LABEL[a.name] ?? a.name, a.at.x * k, a.at.y * k);
  }

  ctx.font = `${glyphPx}px ${mono}`;
  for (const b of wheel.bodies) {
    line(b.tick, ink.accent, 1);
    line(b.leader, ink.hairline, 0.75);
    ctx.fillStyle = b.name === "Sun" ? ink.accent : ink.ink;
    ctx.fillText(PLANET_GLYPHS[b.name] ?? "?", b.draw.x * k, b.draw.y * k);
  }
}
