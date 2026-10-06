import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VinculoPagina } from "@/components/VinculoPagina";
import { getDict } from "@/lib/i18n";
import type { VinculoPreview as Datos } from "@/lib/vinculo";

// El estado de la landing: el formulario siempre está, y el resultado aparece
// debajo cuando llega. Se prueba con el formulario y el resultado reemplazados
// por dobles, que tienen sus propios tests.

const montajes = vi.hoisted(() => ({ preview: 0 }));

vi.mock("@/components/VinculoForm", () => ({
  VinculoForm: ({
    onResultado,
  }: {
    onResultado: (p: unknown, tipo: string, alias: { a: string; b: string }) => void;
  }) => (
    <div>
      <button onClick={() => onResultado(RESULTADO_1, "trabajo", { a: "Ana", b: "Beto" })}>
        calcular-1
      </button>
      <button onClick={() => onResultado(RESULTADO_2, "familia", { a: "", b: "" })}>calcular-2</button>
    </div>
  ),
}));
vi.mock("@/components/VinculoPreview", async () => {
  const { useEffect } = await import("react");
  return {
    VinculoPreview: ({
      preview,
      tipo,
      alias,
    }: {
      preview: { aspectos: { frase: string }[] };
      tipo: string;
      alias: { a: string; b: string };
    }) => {
      useEffect(() => {
        montajes.preview += 1;
      }, []);
      return (
        <div data-testid="preview" data-tipo={tipo} data-alias={`${alias.a}|${alias.b}`}>
          {preview.aspectos[0]?.frase}
        </div>
      );
    },
  };
});

const carta = { data: { placements: [], houses: null, angles: null, aspects: [], flags: {} } };
const RESULTADO_1 = { a: carta, b: carta, aspectos: [{ frase: "primera" }] } as unknown as Datos;
const RESULTADO_2 = { a: carta, b: carta, aspectos: [{ frase: "segunda" }] } as unknown as Datos;

afterEach(() => {
  montajes.preview = 0;
});

const renderPagina = () => render(<VinculoPagina locale="es" dict={getDict("es")} />);

describe("VinculoPagina", () => {
  it("al principio sólo está el formulario", () => {
    renderPagina();
    expect(screen.getByText("calcular-1")).toBeInTheDocument();
    expect(screen.queryByTestId("preview")).toBeNull();
  });

  it("al llegar el resultado aparece debajo, con el tipo y los alias, y el formulario sigue", () => {
    renderPagina();
    fireEvent.click(screen.getByText("calcular-1"));
    const preview = screen.getByTestId("preview");
    expect(preview).toHaveTextContent("primera");
    expect(preview).toHaveAttribute("data-tipo", "trabajo");
    expect(preview).toHaveAttribute("data-alias", "Ana|Beto");
    expect(screen.getByText("calcular-1")).toBeInTheDocument();
  });

  it("un segundo resultado reemplaza al primero y se cuenta como una vista nueva", () => {
    renderPagina();
    fireEvent.click(screen.getByText("calcular-1"));
    fireEvent.click(screen.getByText("calcular-2"));

    expect(screen.getAllByTestId("preview")).toHaveLength(1);
    expect(screen.getByTestId("preview")).toHaveTextContent("segunda");
    expect(screen.getByTestId("preview")).toHaveAttribute("data-tipo", "familia");
    // Montó dos veces: la `key` reinicia la vista y el aviso del CTA.
    expect(montajes.preview).toBe(2);
  });

  /** Un cuadro de animación: el scroll va dentro de `requestAnimationFrame`. */
  const unCuadro = () =>
    act(async () => {
      await new Promise((resolver) => requestAnimationFrame(() => resolver(null)));
    });

  it("donde scrollIntoView no existe (jsdom) no se rompe", async () => {
    expect(Element.prototype.scrollIntoView).toBeUndefined();
    renderPagina();
    fireEvent.click(screen.getByText("calcular-1"));
    // Si el callback del cuadro tirara, el error saldría acá.
    await unCuadro();
    expect(screen.getByTestId("preview")).toBeInTheDocument();
  });

  it("si el navegador sabe scrollear, lleva la vista al resultado", async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    try {
      renderPagina();
      fireEvent.click(screen.getByText("calcular-1"));
      await unCuadro();
      expect(scroll).toHaveBeenCalledTimes(1);
    } finally {
      // @ts-expect-error: restaurar la ausencia que tiene jsdom
      delete Element.prototype.scrollIntoView;
    }
  });
});
