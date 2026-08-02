import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeSwitch } from "@/components/ThemeSwitch";

// El tema lo escribe un script antes de que React exista, para que la página no
// parpadee. Por eso la fuente de verdad es el atributo del <html> y no un
// estado de React: si alguien lo copiara a un useState, el botón marcado y la
// página mostrarían cosas distintas.

const labels = { night: "Noche", day: "Día", label: "Tema" };

/** jsdom no trae matchMedia; acá el sistema siempre pide modo oscuro. */
function stubMatchMedia(prefiereClaro = false) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: prefiereClaro,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
}

/** Almacenamiento de mentira: jsdom no siempre trae uno. */
let guardado: Map<string, string>;

beforeEach(() => {
  delete document.documentElement.dataset.theme;
  guardado = new Map();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => guardado.get(k) ?? null,
    setItem: (k: string, v: string) => guardado.set(k, v),
    removeItem: (k: string) => guardado.delete(k),
    clear: () => guardado.clear(),
  });
  stubMatchMedia();
});

afterEach(() => vi.unstubAllGlobals());

const boton = (nombre: string) => screen.getByRole("button", { name: new RegExp(nombre) });

describe("ThemeSwitch", () => {
  it("marca el tema que pide el sistema cuando nadie eligió", () => {
    render(<ThemeSwitch {...labels} />);

    expect(boton("Noche")).toHaveAttribute("aria-pressed", "true");
    expect(boton("Día")).toHaveAttribute("aria-pressed", "false");
  });

  it("marca el tema ya elegido en la página", () => {
    document.documentElement.dataset.theme = "light";
    render(<ThemeSwitch {...labels} />);

    expect(boton("Día")).toHaveAttribute("aria-pressed", "true");
  });

  it("cambia la página y lo recuerda para la próxima visita", () => {
    render(<ThemeSwitch {...labels} />);

    fireEvent.click(boton("Día"));

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(guardado.get("astra-theme")).toBe("light");
  });

  it("sigue andando si el navegador no deja guardar nada", () => {
    // Modo incógnito o almacenamiento bloqueado: el tema vale para esta visita
    // y no se lleva el click puesto.
    vi.stubGlobal("localStorage", {
      getItem: () => null,
      setItem: () => {
        throw new Error("bloqueado");
      },
    });
    render(<ThemeSwitch {...labels} />);

    expect(() => fireEvent.click(boton("Día"))).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
