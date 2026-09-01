import { describe, expect, it } from "vitest";

import { cantidad, puede } from "@/lib/derechos";

const derechos = [
  { codigo_producto: "lectura_breve", cantidad_restante: 2, vigente_hasta: null },
  { codigo_producto: "informe_natal", cantidad_restante: 0, vigente_hasta: null },
];

describe("derechos", () => {
  it("puede leer breve con saldo", () => {
    expect(puede(derechos, "leer_breve")).toBe(true);
  });

  it("no puede leer el informe con el derecho en cero", () => {
    expect(puede(derechos, "leer_informe")).toBe(false);
  });

  it("un derecho de lectura breve no habilita el informe", () => {
    expect(puede([derechos[0]], "leer_informe")).toBe(false);
  });

  it("cantidad devuelve 0 para un producto que la cuenta no tiene", () => {
    expect(cantidad([], "informe_natal")).toBe(0);
  });
});
