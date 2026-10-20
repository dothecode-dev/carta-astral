"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { capturarProcedencia, leerProcedencia, seccionDe } from "@/lib/procedencia";

/** Anota de dónde llegó la visita en la primera página que abre (ver
 *  `lib/procedencia`) y cuenta cada página que se abre: una por ruta, también
 *  las navegaciones internas. Al servidor van la sección (de una lista
 *  cerrada), el canal y la zona; el país lo saca él de la IP, que no guarda
 *  (backend/api/conteo_api.py). No dibuja nada. */
export function CapturaProcedencia() {
  const ruta = usePathname();
  useEffect(() => capturarProcedencia(), []);
  useEffect(() => {
    if (!ruta) return;
    try {
      void fetch("/api/conteo/visita", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ seccion: seccionDe(ruta), procedencia: leerProcedencia() }),
        keepalive: true,
      }).catch(() => {});
    } catch {
      // Sin `fetch`: esa visita no se cuenta, y nada más.
    }
  }, [ruta]);
  return null;
}
