import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InformeSecciones } from "@/components/InformeSecciones";
import { track as trackReal } from "@/lib/telemetry";

vi.mock("@/lib/telemetry", () => ({ track: vi.fn() }));
const track = vi.mocked(trackReal);

const SECCIONES = [
  { slug: "firma", titulo: "Tu firma", texto: "Primer párrafo." },
  { slug: "mente", titulo: "Cómo pensás", texto: "Segundo." },
];

/** IntersectionObserver de mentira: jsdom no lo trae. `ver(...)` simula que
 *  esos elementos entran en pantalla, todos en el mismo aviso. */
let avisar: IntersectionObserverCallback | null = null;
function ver(...els: Element[]) {
  act(() => {
    avisar?.(
      els.map((target) => ({ target, isIntersecting: true }) as IntersectionObserverEntry),
      {} as IntersectionObserver,
    );
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  track.mockClear();
  avisar = null;
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(cb: IntersectionObserverCallback) {
        avisar = cb;
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("InformeSecciones", () => {
  it("con índice: un enlace por sección y un h2 con ancla por sección", () => {
    render(<InformeSecciones secciones={SECCIONES} indice etiquetaIndice="En este informe" />);
    const nav = screen.getByRole("navigation", { name: "En este informe" });
    const enlaces = Array.from(nav.querySelectorAll("a")).map((a) => a.getAttribute("href"));
    expect(enlaces).toEqual(["#firma", "#mente"]);
    expect(screen.getByRole("heading", { name: "Tu firma", level: 2 }).id).toBe("firma");
    expect(screen.getByText("Primer párrafo.")).toBeInTheDocument();
  });

  it("sin índice: no hay nav pero sí títulos", () => {
    render(<InformeSecciones secciones={SECCIONES} indice={false} />);
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.getByRole("heading", { name: "Cómo pensás", level: 2 })).toBeInTheDocument();
  });

  it("el evento sale al llegar al final, con los segundos desde el título", () => {
    const { container } = render(<InformeSecciones secciones={SECCIONES} indice={false} />);
    ver(container.querySelector("#firma")!);
    act(() => {
      vi.advanceTimersByTime(40_000);
    });
    ver(container.querySelector('[data-fin="firma"]')!);
    expect(track).toHaveBeenCalledTimes(1);
    expect(track).toHaveBeenCalledWith("seccion_informe_leida", { slug: "firma", orden: 1, segundos: 40 });
  });

  it("pasar por el título sin llegar al final no cuenta como leída", () => {
    const { container } = render(<InformeSecciones secciones={SECCIONES} indice={false} />);
    ver(container.querySelector("#firma")!);
    expect(track).not.toHaveBeenCalled();
  });

  it("una sección se cuenta una sola vez", () => {
    const { container } = render(<InformeSecciones secciones={SECCIONES} indice={false} />);
    const fin = container.querySelector('[data-fin="firma"]')!;
    ver(container.querySelector("#firma")!);
    ver(fin);
    ver(fin);
    expect(track).toHaveBeenCalledTimes(1);
  });

  it("título y final en el mismo aviso: un evento con 0 segundos", () => {
    const { container } = render(<InformeSecciones secciones={SECCIONES} indice={false} />);
    ver(container.querySelector('[data-fin="mente"]')!, container.querySelector("#mente")!);
    expect(track).toHaveBeenCalledTimes(1);
    expect(track).toHaveBeenCalledWith("seccion_informe_leida", { slug: "mente", orden: 2, segundos: 0 });
  });

  it("sin IntersectionObserver no mide ni rompe", () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    render(<InformeSecciones secciones={SECCIONES} indice />);
    expect(track).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Tu firma", level: 2 })).toBeInTheDocument();
  });
});
