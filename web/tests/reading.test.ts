import { describe, expect, it } from "vitest";

import { parseReading } from "@/lib/reading";

describe("parseReading", () => {
  it("convierte los títulos, sin dejar la almohadilla a la vista", () => {
    const b = parseReading("# Carta Natal\n\n## Una presencia\n\n### Detalle");
    expect(b).toEqual([
      { tipo: "titulo", nivel: 1, texto: "Carta Natal" },
      { tipo: "titulo", nivel: 2, texto: "Una presencia" },
      { tipo: "titulo", nivel: 3, texto: "Detalle" },
    ]);
  });

  it("marca las negritas y saca los asteriscos", () => {
    const [b] = parseReading("Energía en la **Casa Doce** y su desborde.");
    expect(b).toEqual({
      tipo: "parrafo",
      partes: [
        { texto: "Energía en la " },
        { texto: "Casa Doce", fuerte: true },
        { texto: " y su desborde." },
      ],
    });
  });

  it("arma las listas con guion y con asterisco", () => {
    const [b] = parseReading("- Sol en Escorpio\n- Luna en Piscis");
    expect(b).toEqual({
      tipo: "lista",
      items: [[{ texto: "Sol en Escorpio" }], [{ texto: "Luna en Piscis" }]],
    });
    expect(parseReading("* Uno\n* Dos")[0].tipo).toBe("lista");
  });

  it("junta los renglones de un mismo párrafo en una sola línea", () => {
    // El modelo corta las líneas a lo ancho; en pantalla el corte lo hace el navegador.
    const [b] = parseReading("Una frase\ncortada en dos renglones.");
    expect(b).toEqual({ tipo: "parrafo", partes: [{ texto: "Una frase cortada en dos renglones." }] });
  });

  it("no deja ningún resto de markdown en el texto final", () => {
    const crudo = `# Carta Natal — 1972

## Una presencia que no pasa desapercibida

Lo primero es la energía en la **Casa Doce** y su desborde hacia el
**Ascendente en Escorpio**.

- Con **Sol** en casa uno
- Y la Luna en doce`;
    const texto = parseReading(crudo)
      .flatMap((b) =>
        b.tipo === "titulo" ? [b.texto] : b.tipo === "parrafo" ? b.partes.map((p) => p.texto) : b.items.flat().map((p) => p.texto),
      )
      .join(" ");
    expect(texto).not.toMatch(/\*\*/);
    expect(texto).not.toMatch(/^#|\s#/);
    expect(texto).not.toMatch(/^\s*[-*]\s/);
  });

  it("aguanta texto vacío y espacios sueltos", () => {
    expect(parseReading("")).toEqual([]);
    expect(parseReading("\n\n   \n\n")).toEqual([]);
  });

  it("una negrita sin cerrar se queda como texto, no rompe", () => {
    const [b] = parseReading("Esto quedó **sin cerrar");
    expect(b.tipo).toBe("parrafo");
    expect(b.tipo === "parrafo" && b.partes[0].texto).toContain("**sin cerrar");
  });
});
