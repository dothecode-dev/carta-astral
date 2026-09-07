import { describe, expect, it } from "vitest";

import { normalizarUsar, tierParaArrancar } from "@/lib/usar";

// `?usar=` viene de la URL: la cuenta lo pone, pero cualquiera lo escribe.
// La carta decide en el servidor si arranca algo, con lo que ya sabe.

const derecho = (codigo: string, n: number) => ({
  codigo_producto: codigo,
  cantidad_restante: n,
  vigente_hasta: null,
});

describe("normalizarUsar", () => {
  it("sólo acepta los dos productos que se leen", () => {
    expect(normalizarUsar("informe_natal")).toBe("informe_natal");
    expect(normalizarUsar("lectura_breve")).toBe("lectura_breve");
    for (const raro of ["pack_5_natal", "", undefined, ["informe_natal"], "INFORME_NATAL"]) {
      expect(normalizarUsar(raro)).toBeNull();
    }
  });
});

describe("tierParaArrancar", () => {
  const conInforme = [derecho("lectura_breve", 2), derecho("informe_natal", 1)];

  it("el informe con derecho arranca el tier largo", () => {
    expect(tierParaArrancar("informe_natal", conInforme, {}, {}, "es")).toBe("largo");
  });

  it("la lectura breve con derecho arranca el corto", () => {
    expect(tierParaArrancar("lectura_breve", conInforme, {}, {}, "es")).toBe("corto");
  });

  it("sin derecho no arranca nada: jamás un checkout automático", () => {
    const sinInforme = [derecho("lectura_breve", 2), derecho("informe_natal", 0)];
    expect(tierParaArrancar("informe_natal", sinInforme, {}, {}, "es")).toBeNull();
  });

  it("si ese tier ya está escrito en este idioma, no hay nada que arrancar", () => {
    expect(tierParaArrancar("informe_natal", conInforme, { es: ["largo"] }, {}, "es")).toBeNull();
  });

  it("si ya se está escribiendo, tampoco", () => {
    expect(tierParaArrancar("informe_natal", conInforme, {}, { es: ["largo"] }, "es")).toBeNull();
  });

  it("sin `usar`, nada", () => {
    expect(tierParaArrancar(null, conInforme, {}, {}, "es")).toBeNull();
  });
});
