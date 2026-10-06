import { fireEvent, render, screen, within } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VinculoPreview } from "@/components/VinculoPreview";
import { VINCULO } from "@/content/vinculo";
import { getDict } from "@/lib/i18n";
import * as telemetry from "@/lib/telemetry";
import type { VinculoPreview as Datos } from "@/lib/vinculo";

// jsdom no dibuja canvas: la rueda se reemplaza por un marcador, y lo que se
// prueba es CUÁNDO se muestra (hay hora) y cuándo en su lugar va el aviso.
vi.mock("@/components/NatalWheel", () => ({
  NatalWheel: ({ alt }: { alt: string }) => <div data-testid="rueda" role="img" aria-label={alt} />,
}));

const dict = getDict("es");
const t = VINCULO.es;

afterEach(() => vi.restoreAllMocks());

const FLAGS = {
  moon_approximate: false,
  precision_degraded: false,
  bodies_missing: false,
  house_system_fallback: false,
};

const CASAS = [
  "First_House", "Second_House", "Third_House", "Fourth_House", "Fifth_House", "Sixth_House",
  "Seventh_House", "Eighth_House", "Ninth_House", "Tenth_House", "Eleventh_House", "Twelfth_House",
].map((name, i) => ({ name, abs_pos: i * 30 }));

const sinHora = {
  data: { placements: [], houses: null, angles: null, aspects: [], flags: FLAGS },
};
const conHora = {
  data: {
    placements: [
      { name: "Sun", sign: "Gem", abs_pos: 70, house: "First_House", retrograde: false },
    ],
    houses: CASAS,
    angles: [
      { name: "Ascendant", abs_pos: 0 },
      { name: "Medium_Coeli", abs_pos: 270 },
    ],
    aspects: [],
    flags: FLAGS,
  },
};

const ASPECTO = { p_a: "Sun", p_b: "Moon", aspecto: "trine", orbe: 1.2, frase: "Se entienden fácil." };

function datos(parcial: Partial<Datos> = {}): Datos {
  return { a: sinHora, b: sinHora, aspectos: [ASPECTO], ...parcial };
}

const renderPreview = (
  preview: Datos = datos(),
  tipo: "pareja" | "trabajo" | "familia" | "amistad" = "pareja",
  alias = { a: "", b: "" },
) => render(<VinculoPreview locale="es" dict={dict} preview={preview} tipo={tipo} alias={alias} />);

describe("VinculoPreview", () => {
  it("muestra cada aspecto con su frase y los nombres traducidos", () => {
    renderPreview();
    expect(screen.getByText("Se entienden fácil.")).toBeInTheDocument();
    const item = screen.getByText("Se entienden fácil.").closest("li")!;
    expect(item).toHaveTextContent("Sol");
    expect(item).toHaveTextContent("Trígono");
    expect(item).toHaveTextContent("Luna");
  });

  it("sin alias, cada persona se llama «Primera» y «Segunda persona»", () => {
    renderPreview();
    expect(screen.getByRole("heading", { name: t.personaA })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: t.personaB })).toBeInTheDocument();
  });

  it("con alias, usa el alias en las columnas y en los aspectos", () => {
    renderPreview(datos(), "pareja", { a: "Ana", b: "Beto" });
    expect(screen.getByRole("heading", { name: "Ana" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Beto" })).toBeInTheDocument();
    expect(screen.getByText("Se entienden fácil.").closest("li")).toHaveTextContent("Ana");
    expect(screen.getByText("Se entienden fácil.").closest("li")).toHaveTextContent("Beto");
  });

  it("el alias se muestra como texto, no como HTML", () => {
    renderPreview(datos(), "pareja", { a: "<img src=x onerror=alert(1)>", b: "Beto" });
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(screen.getByRole("heading", { name: "<img src=x onerror=alert(1)>" })).toBeInTheDocument();
  });

  it("sin hora dice qué falta en lugar de dejar el hueco de la rueda", () => {
    renderPreview();
    expect(screen.queryAllByTestId("rueda")).toHaveLength(0);
    expect(screen.getAllByText(t.sinHora)).toHaveLength(2);
  });

  it("con hora dibuja la rueda de esa persona, y sólo la de esa persona", () => {
    renderPreview(datos({ a: conHora, b: sinHora }));
    expect(screen.getAllByTestId("rueda")).toHaveLength(1);
    expect(screen.getAllByText(t.sinHora)).toHaveLength(1);
    const columnaA = screen.getByRole("heading", { name: t.personaA }).closest(".vinculoColumna")!;
    expect(within(columnaA as HTMLElement).getByTestId("rueda")).toBeInTheDocument();
  });

  it("la rueda lleva un texto alternativo con el nombre de la persona", () => {
    renderPreview(datos({ a: conHora }), "pareja", { a: "Ana", b: "" });
    expect(screen.getByTestId("rueda")).toHaveAttribute("aria-label", `${t.ruedaAlt} Ana`);
  });

  it("sin aspectos muestra el texto fijo y no una lista vacía", () => {
    renderPreview(datos({ aspectos: [] }));
    expect(screen.getByText(t.sinAspectos)).toBeInTheDocument();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("registra la vista una sola vez aunque React monte dos veces (StrictMode)", () => {
    const track = vi.spyOn(telemetry, "track").mockImplementation(() => {});
    render(
      <StrictMode>
        <VinculoPreview
          locale="es"
          dict={dict}
          preview={datos()}
          tipo="familia"
          alias={{ a: "Ana", b: "Beto" }}
        />
      </StrictMode>,
    );
    const vistas = track.mock.calls.filter(([evento]) => evento === "vinculo_preview_visto");
    // El tipo sí; el alias y las fechas, nunca.
    expect(vistas).toEqual([["vinculo_preview_visto", { tipo: "familia" }]]);
  });

  it("el clic en el CTA registra el tipo y avisa que el informe sale pronto, sin ofrecer comprar", () => {
    const track = vi.spyOn(telemetry, "track").mockImplementation(() => {});
    renderPreview(datos(), "trabajo");
    expect(screen.queryByText(t.ctaPronto)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: t.cta }));

    expect(track).toHaveBeenCalledWith("vinculo_cta_click", { tipo: "trabajo" });
    expect(screen.getByText(t.ctaPronto)).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("apretar el CTA dos veces no cuenta dos intenciones", () => {
    const track = vi.spyOn(telemetry, "track").mockImplementation(() => {});
    renderPreview(datos(), "pareja");
    fireEvent.click(screen.getByRole("button", { name: t.cta }));
    fireEvent.click(screen.getByRole("button", { name: t.cta }));
    expect(track.mock.calls.filter(([e]) => e === "vinculo_cta_click")).toHaveLength(1);
  });

  it("repite la promesa de privacidad", () => {
    renderPreview();
    expect(screen.getByText(t.privacidad)).toBeInTheDocument();
  });
});
