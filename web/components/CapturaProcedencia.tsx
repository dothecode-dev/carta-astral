"use client";

import { useEffect } from "react";

import { capturarProcedencia } from "@/lib/procedencia";

/** Anota de dónde llegó la visita en la primera página que abre (ver
 *  `lib/procedencia`). No dibuja nada. */
export function CapturaProcedencia() {
  useEffect(() => capturarProcedencia(), []);
  return null;
}
