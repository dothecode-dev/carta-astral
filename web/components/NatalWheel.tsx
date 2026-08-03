"use client";

import { buildWheel } from "astra-wheel";
import { useEffect, useRef } from "react";

import type { SampleChart } from "@/content/sample-chart";
import { toWheelInput } from "@/lib/chart";
import { PLANET_GLYPHS } from "@/lib/i18n";

const SIGNS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"];
const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];

const ANGLE_LABEL: Record<string, string> = { Ascendant: "ASC", Medium_Coeli: "MC" };

const HARD = new Set(["square", "opposition"]);
const SOFT = new Set(["trine", "sextile"]);

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/**
 * La rueda natal.
 *
 * Este componente ya no calcula nada: la geometría —dónde va cada glifo, cuánto
 * se corren los que se pisan, dónde arranca cada línea— la resuelve el paquete
 * `astra-wheel`, que comparte con la app y con el PDF a través de un set de
 * casos de prueba. Acá sólo se pinta, que es lo propio de cada superficie:
 * colores, grosores y tipografía.
 */
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

      // El tamaño real importa: de él depende cuánto hay que separar dos glifos
      // que se pisan, y por eso viaja al paquete en vez de quedar fijo.
      const glyphPx = size * 0.046;
      const wheel = buildWheel(toWheelInput(chart), { size, glyphPx });

      // Del viewBox del paquete a los píxeles del canvas.
      const k = size / wheel.viewBox;
      const cx = wheel.center * k;

      const ink = token("--ink");
      const inkSoft = token("--ink-soft");
      const accent = token("--accent");
      const hairline = token("--hairline");
      const hairStrong = token("--hairline-strong");
      const dotted = token("--dotted");
      const mono = `${token("--font-mono") || "ui-monospace"}, monospace`;

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

      ring(wheel.rings.outer, hairStrong, 1.25);
      ring(wheel.rings.signs, hairline, 1);
      ring(wheel.rings.houses, hairline, 1);
      ring(wheel.rings.aspect, dotted, 1, [1.5, 4]);

      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      // Signos: la línea divisoria de cada uno y su glifo en el medio de la banda.
      ctx.font = `${size * 0.04}px ${mono}`;
      for (const s of wheel.signs) {
        ctx.fillStyle = inkSoft;
        ctx.fillText(SIGNS[s.index], s.at.x * k, s.at.y * k);
      }

      // Casas: los cuatro ejes van marcados más fuerte que las cúspides intermedias.
      ctx.font = `${size * 0.026}px ${mono}`;
      for (const c of wheel.cusps) {
        line(c.line, c.axis ? hairStrong : hairline, c.axis ? 1.2 : 0.75, c.axis ? [] : [2, 3]);
        ctx.fillStyle = inkSoft;
        ctx.fillText(ROMAN[c.index], c.label.x * k, c.label.y * k);
      }

      // Aspectos: el color dice si el ángulo suma o roza, no decora.
      for (const asp of wheel.aspectLines) {
        if (!HARD.has(asp.type) && !SOFT.has(asp.type)) continue;
        const duro = HARD.has(asp.type);
        ctx.globalAlpha = asp.orb < 2 ? 0.75 : 0.4;
        line(asp.line, duro ? inkSoft : accent, asp.orb < 2 ? 1.1 : 0.8, duro ? [3, 3] : []);
        ctx.globalAlpha = 1;
      }

      // Los rotulos de los ejes, por fuera del borde.
      ctx.font = `${size * 0.024}px ${mono}`;
      ctx.fillStyle = accent;
      for (const a of wheel.angles) {
        ctx.fillText(ANGLE_LABEL[a.name] ?? a.name, a.at.x * k, a.at.y * k);
      }

      ctx.font = `${glyphPx}px ${mono}`;
      for (const b of wheel.bodies) {
        line(b.tick, accent, 1);
        line(b.leader, hairline, 0.75);
        ctx.fillStyle = b.name === "Sun" ? accent : ink;
        ctx.fillText(PLANET_GLYPHS[b.name] ?? "?", b.draw.x * k, b.draw.y * k);
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
