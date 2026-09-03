import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

// Cambiar de idioma cambia el segmento `[locale]`, que es el del layout raíz:
// React remonta el <html> con el markup del servidor, que no trae
// `data-theme`, y el script anti-parpadeo no vuelve a correr en una navegación
// de cliente. Quien había puesto día aterrizaba en noche —con este switch
// marcando día, porque el localStorage seguía diciendo "light"—.
//
// El arreglo principal es que el selector de idioma navegue con recarga
// completa (`Nav`); esto es la red de seguridad para cualquier otro remonte.
describe("cuando el DOM pierde el tema", () => {
  it("lo repone de lo guardado al montar", async () => {
    guardado.set("astra-theme", "light");
    // Sin `data-theme`, como queda el <html> recién remontado.
    expect(document.documentElement.dataset.theme).toBeUndefined();

    render(<ThemeSwitch {...labels} />);

    expect(document.documentElement.dataset.theme).toBe("light");
    // El botón se entera por el MutationObserver, que en jsdom entrega en una
    // microtarea: en el navegador el switch queda marcado en el mismo paint.
    await waitFor(() => expect(boton("Día")).toHaveAttribute("aria-pressed", "true"));
  });

  it("no pisa un tema que la página ya tiene puesto", () => {
    guardado.set("astra-theme", "light");
    document.documentElement.dataset.theme = "dark";

    render(<ThemeSwitch {...labels} />);

    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("sin nada guardado deja mandar a la preferencia del sistema", () => {
    render(<ThemeSwitch {...labels} />);

    expect(document.documentElement.dataset.theme).toBeUndefined();
  });
});
