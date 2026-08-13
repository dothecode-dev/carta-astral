import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Nav } from "@/components/Nav";
import { NOTES_SLUG, getDict } from "@/lib/i18n";

const dict = getDict("es");

// El Nav incluye el interruptor de tema, que consulta matchMedia; jsdom no lo trae.
beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }),
  );
});

/** Los tres enlaces de idioma, con su destino. */
function idiomas() {
  return ["ES", "EN", "PT"].map((code) => ({
    code,
    href: screen.getByRole("link", { name: code }).getAttribute("href"),
  }));
}

describe("Nav: cambiar de idioma", () => {
  it("se queda en la misma página, con el id de la carta incluido", () => {
    // La página de la carta pasaba "/cuenta" fijo: cambiar de idioma sacaba a
    // la persona de la carta que estaba mirando y la llevaba a la lista.
    render(<Nav locale="es" dict={dict} path="/carta/53872403-302d-4930-8aa0-5315302a44c4" signedIn />);
    expect(idiomas()).toEqual([
      { code: "ES", href: "/es/carta/53872403-302d-4930-8aa0-5315302a44c4" },
      { code: "EN", href: "/en/carta/53872403-302d-4930-8aa0-5315302a44c4" },
      { code: "PT", href: "/pt/carta/53872403-302d-4930-8aa0-5315302a44c4" },
    ]);
  });

  it("sin path, cada idioma va a su portada", () => {
    render(<Nav locale="es" dict={dict} />);
    expect(idiomas()).toEqual([
      { code: "ES", href: "/es" },
      { code: "EN", href: "/en" },
      { code: "PT", href: "/pt" },
    ]);
  });

  it("traduce el segmento cuando la ruta misma cambia de idioma", () => {
    // Las notas viven en `/notas` y en `/notes` según el idioma. Con un path
    // fijo, el enlace a inglés apuntaba a `/en/notas`, que es 404 a propósito.
    render(<Nav locale="es" dict={dict} path={(code) => `/${NOTES_SLUG[code]}`} />);
    expect(idiomas()).toEqual([
      { code: "ES", href: "/es/notas" },
      { code: "EN", href: "/en/notes" },
      { code: "PT", href: "/pt/notas" },
    ]);
  });
});
