"use client";

import { useEffect, useRef } from "react";

import type { SampleChart } from "@/content/sample-chart";

const RAD = Math.PI / 180;

const SIGNS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"];
const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];

const GLYPH: Record<string, string> = {
  Sun: "☉", Moon: "☽", Mercury: "☿", Venus: "♀", Mars: "♂",
  Jupiter: "♃", Saturn: "♄", Uranus: "♅", Neptune: "♆", Pluto: "♇",
};

const HARD = new Set(["square", "opposition"]);
const SOFT = new Set(["trine", "sextile"]);

const rev = (x: number) => x - Math.floor(x / 360) * 360;

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Corre los glifos que se pisan, dejando la marca en el grado exacto.
 *  Es lo que hace una carta impresa: Sol y Luna a un grado no entran juntos. */
function spread(items: { lon: number; name: string }[], minSep: number) {
  const s = items
    .slice()
    .sort((a, b) => a.lon - b.lon)
    .map((p) => ({ ...p, draw: p.lon }));

  for (let iter = 0; iter < 80; iter++) {
    let moved = false;
    for (let i = 0; i < s.length; i++) {
      const j = (i + 1) % s.length;
      let d = s[j].draw - s[i].draw;
      if (d < 0) d += 360;
      if (d < minSep) {
        const push = (minSep - d) / 2;
        s[i].draw = rev(s[i].draw - push);
        s[j].draw = rev(s[j].draw + push);
        moved = true;
      }
    }
    if (!moved) break;
  }
  return s;
}

export function NatalWheel({ chart, alt }: { chart: SampleChart; alt: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    function draw() {
      if (!canvas || !ctx) return;
      const size = canvas.parentElement?.clientWidth ?? 0;
      if (!size) return;

      const dpr = window.devicePixelRatio || 1;
      canvas.width = size * dpr;
      canvas.height = size * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size, size);

      const cx = size / 2;
      const cy = size / 2;
      const rOuter = size * 0.475;
      const rSign = size * 0.405;
      const rHouse = size * 0.345;
      const rGlyph = size * 0.3;
      const rAspect = size * 0.255;

      const ink = token("--ink");
      const inkSoft = token("--ink-soft");
      const accent = token("--accent");
      const hairline = token("--hairline");
      const hairStrong = token("--hairline-strong");
      const dotted = token("--dotted");
      const mono = `${token("--font-mono") || "ui-monospace"}, monospace`;

      // El Ascendente va a la izquierda: la orientación de cualquier carta impresa.
      const asc = chart.angles.Ascendant;
      const toXY = (lon: number, r: number): [number, number] => {
        const a = (180 + lon - asc) * RAD;
        return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
      };

      const ring = (r: number, color: string, width: number, dash?: number[]) => {
        ctx.beginPath();
        ctx.setLineDash(dash ?? []);
        ctx.strokeStyle = color;
        ctx.lineWidth = width;
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
      };

      const line = (lon: number, r1: number, r2: number, color: string, w: number, dash?: number[]) => {
        const [x1, y1] = toXY(lon, r1);
        const [x2, y2] = toXY(lon, r2);
        ctx.beginPath();
        ctx.setLineDash(dash ?? []);
        ctx.strokeStyle = color;
        ctx.lineWidth = w;
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
        ctx.setLineDash([]);
      };

      ring(rOuter, hairStrong, 1.25);
      ring(rSign, hairline, 1);
      ring(rHouse, hairline, 1);
      ring(rAspect, dotted, 1, [1.5, 4]);

      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      ctx.font = `${size * 0.04}px ${mono}`;
      for (let s = 0; s < 12; s++) {
        line(s * 30, rSign, rOuter, hairline, 1);
        const [gx, gy] = toXY(s * 30 + 15, (rSign + rOuter) / 2);
        ctx.fillStyle = inkSoft;
        ctx.fillText(SIGNS[s], gx, gy);
      }

      // Casas: los cuatro ejes van marcados más fuerte que las cúspides intermedias.
      ctx.font = `${size * 0.026}px ${mono}`;
      for (let h = 0; h < 12; h++) {
        const cusp = chart.houses[h];
        const isAxis = h % 3 === 0;
        line(cusp, rAspect, rSign, isAxis ? hairStrong : hairline, isAxis ? 1.2 : 0.75, isAxis ? [] : [2, 3]);

        const next = chart.houses[(h + 1) % 12];
        let span = next - cusp;
        if (span <= 0) span += 360;
        const [nx, ny] = toXY(cusp + span / 2, (rHouse + rAspect) / 2);
        ctx.fillStyle = inkSoft;
        ctx.fillText(ROMAN[h], nx, ny);
      }

      // Aspectos: el color dice si el ángulo suma o roza, no decora.
      const byName = Object.fromEntries(chart.planets.map((p) => [p.name, p.lon]));
      for (const asp of chart.aspects) {
        if (!HARD.has(asp.type) && !SOFT.has(asp.type)) continue;
        const [x1, y1] = toXY(byName[asp.a], rAspect);
        const [x2, y2] = toXY(byName[asp.b], rAspect);
        ctx.beginPath();
        ctx.setLineDash(HARD.has(asp.type) ? [3, 3] : []);
        ctx.strokeStyle = HARD.has(asp.type) ? inkSoft : accent;
        ctx.globalAlpha = asp.orb < 2 ? 0.75 : 0.4;
        ctx.lineWidth = asp.orb < 2 ? 1.1 : 0.8;
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
        ctx.globalAlpha = 1;
        ctx.setLineDash([]);
      }

      const placed = spread(chart.planets.map((p) => ({ lon: p.lon, name: p.name })), 7.5);
      ctx.font = `${size * 0.046}px ${mono}`;
      for (const item of placed) {
        line(item.lon, rHouse, rHouse - size * 0.02, accent, 1);
        const [tx, ty] = toXY(item.lon, rHouse - size * 0.02);
        const [gx, gy] = toXY(item.draw, rGlyph + size * 0.018);
        ctx.beginPath();
        ctx.strokeStyle = hairline;
        ctx.lineWidth = 0.75;
        ctx.moveTo(tx, ty);
        ctx.lineTo(gx, gy);
        ctx.stroke();

        const [px, py] = toXY(item.draw, rGlyph);
        ctx.fillStyle = item.name === "Sun" ? accent : ink;
        ctx.fillText(GLYPH[item.name] ?? "?", px, py);
      }

      ctx.font = `${size * 0.024}px ${mono}`;
      ctx.fillStyle = accent;
      for (const [label, lon] of [
        ["ASC", chart.angles.Ascendant],
        ["MC", chart.angles.Medium_Coeli],
      ] as const) {
        const [lx, ly] = toXY(lon, rOuter + size * 0.018);
        ctx.fillText(label, lx, ly);
      }
    }

    draw();

    const onResize = () => draw();
    window.addEventListener("resize", onResize);
    const observer = new MutationObserver(draw);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", draw);

    return () => {
      window.removeEventListener("resize", onResize);
      observer.disconnect();
      media.removeEventListener("change", draw);
    };
  }, [chart]);

  return (
    <div className="wheelHolder wheelHolderWide">
      <canvas ref={canvasRef} className="wheel" role="img" aria-label={alt} />
    </div>
  );
}
