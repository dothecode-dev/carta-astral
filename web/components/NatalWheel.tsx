"use client";

import { useEffect, useRef } from "react";

import type { SampleChart } from "@/content/sample-chart";
import { drawWheel } from "@/lib/drawWheel";

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/**
 * La rueda natal.
 *
 * Este componente ya no calcula nada ni dibuja nada: la geometría la resuelve el
 * paquete `astra-wheel` —compartido con la app y con el PDF a través de un set de
 * casos de prueba— y el pintado vive en `lib/drawWheel`, porque la imagen para
 * redes dibuja la misma rueda en otro canvas. Acá quedan los colores del tema y
 * el redibujado cuando cambian.
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

      drawWheel(ctx, size, chart, {
        ink: token("--ink"),
        inkSoft: token("--ink-soft"),
        accent: token("--accent"),
        hairline: token("--hairline"),
        hairStrong: token("--hairline-strong"),
        dotted: token("--dotted"),
        mono: token("--font-mono"),
      });
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
