import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConsentBanner } from "@/components/ConsentBanner";
import { olvidarConsentimiento } from "@/lib/telemetry/consent";

// El banner es la puerta: mientras no se toque "Aceptar", nada se mide. Lo que
// se prueba acá es que la puerta no se abra sola y que no vuelva a preguntarle
// a quien ya dijo que no — insistir es la forma más común de convertir un
// rechazo en un consentimiento que no vale nada.

const activar = vi.fn(async () => {});
const desactivar = vi.fn();
const track = vi.fn();
const capturarPagina = vi.fn();

vi.mock("@/lib/telemetry", () => ({
  activar: (...args: unknown[]) => activar(...(args as [])),
  desactivar: () => desactivar(),
  track: (...args: unknown[]) => track(...(args as [])),
  capturarPagina: (...args: unknown[]) => capturarPagina(...(args as [])),
}));

const textos = {
  locale: "es" as const,
  text: "Nos ayuda saber cuánta gente entra.",
  accept: "Aceptar",
  reject: "No, gracias",
  more: "Cómo tratamos tus datos",
};

let guardado: Map<string, string>;

beforeEach(() => {
  activar.mockClear();
  desactivar.mockClear();
  track.mockClear();
  capturarPagina.mockClear();
  guardado = new Map();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => guardado.get(k) ?? null,
    setItem: (k: string, v: string) => void guardado.set(k, v),
    removeItem: (k: string) => void guardado.delete(k),
  });
});

afterEach(() => vi.unstubAllGlobals());

describe("ConsentBanner", () => {
  it("pregunta cuando no hay decisión guardada", () => {
    render(<ConsentBanner {...textos} />);

    expect(screen.getByText(textos.text)).toBeInTheDocument();
  });

  it("no vuelve a preguntar si ya aceptó", () => {
    guardado.set("astra-consent", "si");

    render(<ConsentBanner {...textos} />);

    expect(screen.queryByText(textos.text)).not.toBeInTheDocument();
  });

  it("no vuelve a preguntar si ya rechazó", () => {
    guardado.set("astra-consent", "no");

    render(<ConsentBanner {...textos} />);

    expect(screen.queryByText(textos.text)).not.toBeInTheDocument();
  });

  it("al aceptar guarda la decisión, arranca la medición y cuenta la visita en curso", async () => {
    render(<ConsentBanner {...textos} />);

    await userEvent.click(screen.getByRole("button", { name: textos.accept }));

    expect(guardado.get("astra-consent")).toBe("si");
    expect(activar).toHaveBeenCalledOnce();
    expect(track).toHaveBeenCalledWith("consentimiento", { decision: "si" });
    // La visita ya había ocurrido: sin esto se pierde la página de entrada de
    // todo el que acepta, que es justo la que dice de dónde viene la gente.
    expect(capturarPagina).toHaveBeenCalledOnce();
  });

  it("al rechazar guarda el no y no arranca nada", async () => {
    render(<ConsentBanner {...textos} />);

    await userEvent.click(screen.getByRole("button", { name: textos.reject }));

    expect(guardado.get("astra-consent")).toBe("no");
    expect(activar).not.toHaveBeenCalled();
    expect(desactivar).toHaveBeenCalledOnce();
    // Registrar el rechazo sería medir a quien acaba de decir que no.
    expect(track).not.toHaveBeenCalled();
  });

  it("olvidar la decisión lo vuelve a abrir, que es lo que hace el enlace del pie", async () => {
    guardado.set("astra-consent", "no");
    render(<ConsentBanner {...textos} />);
    expect(screen.queryByText(textos.text)).not.toBeInTheDocument();

    act(() => olvidarConsentimiento());

    expect(await screen.findByText(textos.text)).toBeInTheDocument();
  });
});
