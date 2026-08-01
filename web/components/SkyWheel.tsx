"use client";

import { useEffect, useRef } from "react";

import { BODIES, positions, type Positions } from "@/lib/ephemeris";

const RAD = Math.PI / 180;

const SIGNS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"];

// Aspectos mayores con orbe corto: la rueda tiene que leerse, no ser una madeja.
// La conjunción no se dibuja porque son dos puntos casi encimados.
const ASPECTS = [
  { angle: 60, orb: 4 },
  { angle: 90, orb: 6 },
  { angle: 120, orb: 6 },
  { angle: 180, orb: 7 },
];

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function SkyWheel({ alt, initial }: { alt: string; initial: Positions | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const posRef = useRef<Positions | null>(initial);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Con datos del servidor se usan tal cual (Swiss Ephemeris); si no llegaron,
    // se calculan acá con elementos orbitales.
    posRef.current = initial ?? positions(new Date());

    function draw() {
      const pos = posRef.current;
      if (!canvas || !ctx || !pos) return;
      const holder = canvas.parentElement;
      const size = holder?.clientWidth ?? 0;
      if (!size) return;

      const dpr = window.devicePixelRatio || 1;
      canvas.width = size * dpr;
      canvas.height = size * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size, size);

      const cx = size / 2;
      const cy = size / 2;
      const rOuter = size * 0.47;
      const rSigns = size * 0.4;
      const rBodies = size * 0.335;
      const rAspect = size * 0.285;

      const ink = token("--ink");
      const inkSoft = token("--ink-soft");
      const accent = token("--accent");
      const hairline = token("--hairline");
      const hairStrong = token("--hairline-strong");
      const dotted = token("--dotted");
      // Canvas no interpola var(): la familia hay que resolverla a mano.
      const mono = `${token("--font-mono") || "ui-monospace"}, monospace`;

      // 0° Aries a la izquierda, avanzando en sentido antihorario: la convención
      // de una carta impresa.
      const toXY = (lon: number, r: number): [number, number] => {
        const a = (180 - lon) * RAD;
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

      ring(rOuter, hairStrong, 1.25);
      ring(rSigns, hairline, 1);
      ring(rAspect, dotted, 1, [1.5, 4]);

      ctx.font = `${size * 0.042}px ${mono}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      for (let s = 0; s < 12; s++) {
        const [x1, y1] = toXY(s * 30, rSigns);
        const [x2, y2] = toXY(s * 30, rOuter);
        ctx.beginPath();
        ctx.strokeStyle = hairline;
        ctx.lineWidth = 1;
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        const [gx, gy] = toXY(s * 30 + 15, (rSigns + rOuter) / 2);
        ctx.fillStyle = inkSoft;
        ctx.fillText(SIGNS[s], gx, gy);
      }

      const keys = BODIES.map((b) => b.key);
      for (let i = 0; i < keys.length; i++) {
        for (let j = i + 1; j < keys.length; j++) {
          let diff = Math.abs(pos[keys[i]] - pos[keys[j]]);
          if (diff > 180) diff = 360 - diff;
          for (const asp of ASPECTS) {
            const delta = Math.abs(diff - asp.angle);
            if (delta > asp.orb) continue;
            const [x1, y1] = toXY(pos[keys[i]], rAspect);
            const [x2, y2] = toXY(pos[keys[j]], rAspect);
            const exact = delta < 1.5;
            ctx.beginPath();
            ctx.strokeStyle = exact ? accent : hairline;
            ctx.globalAlpha = exact ? 0.55 : 1;
            ctx.lineWidth = exact ? 1.1 : 0.75;
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.stroke();
            ctx.globalAlpha = 1;
          }
        }
      }

      ctx.font = `${size * 0.05}px ${mono}`;
      for (const body of BODIES) {
        const lon = pos[body.key];
        const [mx1, my1] = toXY(lon, rSigns);
        const [mx2, my2] = toXY(lon, rSigns - size * 0.022);
        ctx.beginPath();
        ctx.strokeStyle = accent;
        ctx.lineWidth = 1;
        ctx.moveTo(mx1, my1);
        ctx.lineTo(mx2, my2);
        ctx.stroke();

        const [bx, by] = toXY(lon, rBodies);
        ctx.fillStyle = body.key === "sun" ? accent : ink;
        ctx.fillText(body.glyph, bx, by);
      }

      // El Sol al centro: ancla del sistema y del logo.
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, size * 0.11);
      glow.addColorStop(0, accent);
      glow.addColorStop(1, "transparent");
      ctx.beginPath();
      ctx.fillStyle = glow;
      ctx.globalAlpha = 0.22;
      ctx.arc(cx, cy, size * 0.11, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.fillStyle = accent;
      ctx.arc(cx, cy, size * 0.026, 0, Math.PI * 2);
      ctx.fill();
    }

    draw();

    const onResize = () => draw();
    window.addEventListener("resize", onResize);

    // El canvas no hereda los tokens: hay que repintarlo cuando cambia el tema.
    const observer = new MutationObserver(draw);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", draw);

    // El cielo se mueve: media hora de página abierta ya corre la Luna un grado.
    // Se recalcula localmente para no pedirle nada más al backend por dejar la
    // pestaña abierta; la diferencia con el dato original no llega al píxel.
    const timer = window.setInterval(() => {
      posRef.current = positions(new Date());
      draw();
    }, 30 * 60_000);

    return () => {
      window.removeEventListener("resize", onResize);
      observer.disconnect();
      media.removeEventListener("change", draw);
      window.clearInterval(timer);
    };
  }, [initial]);

  return (
    <div className="wheelHolder">
      <canvas ref={canvasRef} className="wheel" role="img" aria-label={alt} />
    </div>
  );
}
