import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CieloHoy } from "@/components/CieloHoy";
import { HoraLocal } from "@/components/HoraLocal";
import { Nav } from "@/components/Nav";
import { CIELO } from "@/content/cielo";
import { cieloMetadata, localeDelCielo } from "@/lib/cielo";
import { instanteUtc } from "@/lib/instante";
import { LOCALES, SKY_SLUG, getDict } from "@/lib/i18n";
import { fetchMoon, type Moon, type Sky } from "@/lib/sky";

vi.mock("@/lib/notes", () => ({ fetchNotesOrNone: async () => [] }));
// El sitemap pregunta si Vínculo está encendido: sin esto pegaría al backend real.
vi.mock("@/lib/vinculo", async (original) => ({
  ...(await original<typeof import("@/lib/vinculo")>()),
  vinculoActivo: async () => false,
}));

// La rueda es un canvas: jsdom no lo dibuja, y acá lo que importa es el texto.
vi.mock("@/components/SkyWheel", () => ({ SkyWheel: () => null }));

beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// La Luna a 132°04′ es Leo 12°04′. Mercurio a 215° (Escorpio), retrógrado.
const SKY: Sky = {
  moment: "2026-10-05T15:00:00+00:00",
  positions: {
    sun: 192, moon: 132.07, mercury: 215, venus: 230, mars: 120,
    jupiter: 115, saturn: 5, uranus: 60, neptune: 1,
  },
  bodies: [
    { name: "Sun", longitude: 192, retrograde: false },
    { name: "Moon", longitude: 132.07, retrograde: false },
    { name: "Mercury", longitude: 215, retrograde: true },
    { name: "Venus", longitude: 230, retrograde: false },
    { name: "Mars", longitude: 120, retrograde: false },
    { name: "Jupiter", longitude: 115, retrograde: false },
    { name: "Saturn", longitude: 5, retrograde: true },
    { name: "Uranus", longitude: 60, retrograde: true },
    { name: "Neptune", longitude: 1, retrograde: true },
    { name: "Pluto", longitude: 303, retrograde: false },
  ],
};

const MOON: Moon = {
  moment: "2026-10-05T15:00:00+00:00",
  phase: "waning_crescent",
  illumination: 34,
  waxing: false,
  nextPhases: [
    { phase: "new_moon", moment: "2026-10-10T15:50:00+00:00" },
    { phase: "first_quarter", moment: "2026-10-18T16:12:00+00:00" },
    { phase: "full_moon", moment: "2026-10-26T04:12:00+00:00" },
    { phase: "last_quarter", moment: "2026-11-01T20:28:00+00:00" },
  ],
  nextSignIndex: 5,
  nextSignMoment: "2026-10-06T02:10:00+00:00",
};

const AHORA = new Date("2026-10-05T15:00:00Z");

describe("el slug traducido", () => {
  it("cada idioma tiene el suyo y no acepta el de otro", () => {
    expect(localeDelCielo("es", "cielo-hoy")).toBe("es");
    expect(localeDelCielo("en", "sky-today")).toBe("en");
    expect(localeDelCielo("pt", "ceu-hoje")).toBe("pt");
    // La carpeta existe para todos los idiomas, la página no.
    expect(localeDelCielo("en", "cielo-hoy")).toBeNull();
    expect(localeDelCielo("es", "sky-today")).toBeNull();
    expect(localeDelCielo("xx", "cielo-hoy")).toBeNull();
  });

  it("la metadata declara el canonical y los tres idiomas", () => {
    const meta = cieloMetadata("en", "sky-today");

    expect(meta.alternates?.canonical).toBe("/en/sky-today");
    expect(meta.alternates?.languages).toEqual({
      es: "/es/cielo-hoy",
      en: "/en/sky-today",
      pt: "/pt/ceu-hoje",
      "x-default": "/es/cielo-hoy",
    });
    expect(String(meta.title)).toContain(CIELO.en.metaTitle);
  });

  it("con el slug de otro idioma no hay metadata que servir", () => {
    expect(cieloMetadata("en", "cielo-hoy")).toEqual({});
  });
});

describe("CieloHoy: lo que lee un buscador", () => {
  it("dice en qué signo y grado está la Luna, su fase y cuándo cambia de signo", () => {
    render(<CieloHoy locale="es" sky={SKY} moon={MOON} ahora={AHORA} />);

    expect(screen.getByText(/La Luna está en Leo, a 12°04′\./)).toBeTruthy();
    // La fase y el porcentaje en una sola frase, sin repetir que mengua.
    const frase = screen.getByText((_, el) => el?.tagName === "P" && /La Luna está en/.test(el.textContent ?? ""));
    expect(frase.textContent).toMatch(/Luna menguante, con el 34\s% del disco iluminado\./);
    expect(screen.queryByText(/Menguando/)).toBeNull();
    expect(screen.getByText(/Entra en Virgo el/)).toBeTruthy();
    // El párrafo del signo en el que está la Luna, y no otro.
    expect(screen.getByText(CIELO.es.moonSigns[4])).toBeTruthy();
    expect(screen.queryByText(CIELO.es.moonSigns[5])).toBeNull();
  });

  it("lista las cuatro próximas fases", () => {
    render(<CieloHoy locale="es" sky={SKY} moon={MOON} ahora={AHORA} />);

    for (const fase of ["Luna nueva", "Cuarto creciente", "Luna llena", "Cuarto menguante"]) {
      expect(screen.getByText(fase)).toBeTruthy();
    }
  });

  it("nombra los retrógrados con su signo e incluye a Plutón en la tabla", () => {
    render(<CieloHoy locale="es" sky={SKY} moon={MOON} ahora={AHORA} />);

    expect(screen.getByText(/Mercurio \(Escorpio\)/)).toBeTruthy();
    expect(screen.getByText("Plutón")).toBeTruthy();
    expect(screen.getAllByTitle("retrógrado")).toHaveLength(4);
  });

  it("sin retrógrados lo dice en vez de dejar la lista vacía", () => {
    const directos = { ...SKY, bodies: SKY.bodies.map((b) => ({ ...b, retrograde: false })) };
    render(<CieloHoy locale="es" sky={directos} moon={MOON} ahora={AHORA} />);

    expect(screen.getByText(CIELO.es.retroNone)).toBeTruthy();
  });

  it("termina en el calculador de cartas", () => {
    render(<CieloHoy locale="en" sky={SKY} moon={MOON} ahora={AHORA} />);

    const cta = screen.getByRole("link", { name: CIELO.en.closing.cta });
    expect(cta.getAttribute("href")).toBe("/en/nueva");
  });

  it("sin la Luna del backend sale igual, sin el bloque de fases", () => {
    render(<CieloHoy locale="es" sky={SKY} moon={null} ahora={AHORA} />);

    expect(screen.getByText(/La Luna está en Leo/)).toBeTruthy();
    expect(screen.queryByText(CIELO.es.nextPhasesHeading)).toBeNull();
  });

  it("sin backend calcula en local y no inventa retrógrados", () => {
    render(<CieloHoy locale="es" sky={null} moon={null} ahora={AHORA} />);

    expect(screen.getByText(/La Luna está en /)).toBeTruthy();
    // El cálculo local no sabe cuáles están retrógrados: no se afirma nada.
    expect(screen.queryByText(CIELO.es.retroHeading)).toBeNull();
    expect(screen.queryAllByTitle("retrógrado")).toHaveLength(0);
  });
});

describe("los textos", () => {
  it("el porcentaje nunca queda separado de su número al final de una línea", () => {
    // En español va con espacio («28 %»), y con uno común el navegador cortaba
    // la línea ahí: el 28 arriba y el % solo abajo (05-10-2026).
    for (const locale of LOCALES) {
      expect(CIELO[locale].illumination(28)).not.toMatch(/28 %/);
    }
  });
});

describe("HoraLocal", () => {
  const ISO = "2026-10-10T15:50:00+00:00";

  it("el HTML del servidor trae, tal cual, el texto UTC que le pasó el servidor", () => {
    // Tal cual y no recalculado: el ICU del navegador no da el mismo string
    // que el de Node, y recalcularlo rompía la hidratación (05-10-2026).
    const utc = instanteUtc(ISO, "es");
    const html = renderToString(<HoraLocal iso={ISO} utc={utc} locale="es" />);

    expect(html).toContain(`dateTime="${ISO}"`);
    expect(html).toContain(utc);
    expect(utc).toContain("UTC");
  });

  it("en el navegador deja de decir UTC", () => {
    render(<HoraLocal iso={ISO} utc={instanteUtc(ISO, "es")} locale="es" />);

    expect(screen.getByText((_, el) => el?.tagName === "TIME").textContent).not.toContain("UTC");
  });
});

describe("enlaces a la página", () => {
  it("el nav la ofrece con el slug de cada idioma y la marca cuando estás ahí", () => {
    render(
      <Nav locale="pt" dict={getDict("pt")} path={(code) => `/${SKY_SLUG[code]}`} signedIn={false} />,
    );

    const link = screen.getByRole("link", { name: CIELO.pt.nav });
    expect(link.getAttribute("href")).toBe("/pt/ceu-hoje");
    expect(link.getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "EN" }).getAttribute("href")).toBe("/en/sky-today");
  });

  it("está en el sitemap en los tres idiomas", async () => {
    const { default: sitemap } = await import("@/app/sitemap");
    const urls = (await sitemap()).map((e) => e.url);

    for (const locale of LOCALES) {
      expect(urls).toContain(`https://astraguia.com/${locale}/${SKY_SLUG[locale]}`);
    }
  });
});

describe("fetchMoon", () => {
  it("traduce la abreviatura del próximo signo a su índice en el zodíaco", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          moment: MOON.moment,
          phase: "waning_crescent",
          illumination: 34,
          waxing: false,
          next_phases: MOON.nextPhases,
          next_sign_change: { sign: "Vir", moment: MOON.nextSignMoment },
        }),
      }),
    );

    expect(await fetchMoon()).toEqual(MOON);
  });

  it("si el backend no contesta, devuelve null en vez de romper la página", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("caído")));

    expect(await fetchMoon()).toBeNull();
  });
});
