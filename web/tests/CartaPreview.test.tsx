import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CartaPreview } from "@/components/CartaPreview";
import { getDict, LOCALES } from "@/lib/i18n";
import type { Teaser } from "@/lib/chart";

// La vista previa muestra el teaser y el índice bloqueado del informe, y la
// compra es la acción principal (spec 2026-10-17). Sin precio no hay botón: el
// precio sale del catálogo y no se inventa.

const CARTA = {
  data: {
    placements: [
      { name: "Sun", sign: "Gem", abs_pos: 70.5, house: "First_House", retrograde: false },
    ],
    houses: null,
    angles: null,
    aspects: [],
    flags: {
      moon_approximate: false,
      precision_degraded: false,
      bodies_missing: false,
      house_system_fallback: false,
    },
  },
};

const TEASER: Teaser = {
  bloques: [
    { cuerpo: "Sun", signo: "Gem", textos: { es: "Párrafo del Sol.", en: "Sun paragraph.", pt: "Parágrafo do Sol." } },
    { cuerpo: "Ascendant", signo: "Leo", textos: { es: "Párrafo del Asc.", en: "Asc paragraph.", pt: "Parágrafo do Asc." } },
  ],
  indice: [
    {
      slug: "identidad",
      titulos: { es: "Identidad y propósito", en: "Identity and purpose", pt: "Identidade e propósito" },
      temas: [
        { es: "Tu Sol y tu Luna", en: "Your Sun and Moon", pt: "Seu Sol e sua Lua" },
        { es: "Tu Marte en Casa 10", en: "Your Mars in House 10", pt: "Seu Marte na Casa 10" },
      ],
    },
    {
      slug: "vinculos",
      titulos: { es: "Vínculos", en: "Bonds", pt: "Vínculos" },
      temas: [],
    },
  ],
  informe: { secciones: 8, palabras: 6200 },
};

const CON_TEASER = { ...CARTA, teaser: TEASER };

afterEach(cleanup);

function propsBase(locale: "es" | "en" | "pt", extra: Partial<Parameters<typeof CartaPreview>[0]> = {}) {
  return {
    carta: CON_TEASER,
    dict: getDict(locale),
    locale,
    onVolver: vi.fn(),
    precio: "US$ 29",
    onComprar: vi.fn().mockResolvedValue(undefined),
    comprando: false,
    errorCompra: null,
    ...extra,
  };
}

function pintar(locale: "es" | "en" | "pt", extra: Partial<Parameters<typeof CartaPreview>[0]> = {}) {
  const props = propsBase(locale, extra);
  render(<CartaPreview {...props} />);
  return props;
}

describe("botón de compra de la vista previa", () => {
  it.each(LOCALES)("%s: muestra el botón con el precio y la nota legal con sus enlaces", (locale) => {
    pintar(locale);
    const t = getDict(locale).newChart;

    expect(screen.getByRole("button", { name: t.comprarCta.replace("{precio}", "US$ 29") })).toBeTruthy();
    const terminos = screen.getByRole("link", { name: t.legalTerminos });
    const privacidad = screen.getByRole("link", { name: t.legalPrivacidad });
    expect(terminos.getAttribute("href")).toBe(`/${locale}/legal/terms`);
    expect(privacidad.getAttribute("href")).toBe(`/${locale}/legal/privacy`);
  });

  it("el botón de compra es el principal", () => {
    pintar("es");
    const pago = screen.getByRole("button", { name: /Leer el informe completo/ });
    expect(pago.className).toContain("btnPrimary");
  });

  it("apretarlo llama a onComprar y no manda a entrar", () => {
    const { onComprar } = pintar("es");
    fireEvent.click(screen.getByRole("button", { name: /Leer el informe completo/ }));

    expect(onComprar).toHaveBeenCalledTimes(1);
  });

  it("la nota de privacidad no promete que no se guarda nada: abrir el pago guarda la carta", () => {
    pintar("es");
    expect(screen.getByText(/Si comprás el informe, la carta queda guardada para entregártelo\./)).toBeTruthy();
    expect(screen.queryByText(/No guardamos nada de esto\. /)).toBeNull();
  });

  it("sin precio no hay compra que mencionar: la nota dice que la lectura queda en el navegador", () => {
    pintar("es", { precio: null });
    expect(
      screen.getByText(
        "Tu carta y tu lectura quedan sólo en este navegador por 24 horas. No guardamos tus datos de nacimiento.",
      ),
    ).toBeTruthy();
  });

  // Final review I2: con precio (el caso normal) la nota tiene que decir las
  // tres cosas ciertas: nada en el servidor mientras mira, la lectura gratis
  // en el navegador 24 h, y la carta guardada sólo si compra.
  it.each([
    ["es", "Tus datos de nacimiento no se guardan en nuestros servidores mientras mirás tu carta. Si leés tu lectura gratis, tu carta y tu lectura quedan sólo en este navegador por 24 horas. Si comprás el informe, la carta queda guardada para entregártelo."],
    ["en", "Your birth details aren't stored on our servers while you look at your chart. If you read your free reading, your chart and your reading stay only in this browser for 24 hours. If you buy the report, the chart is saved so we can deliver it."],
    ["pt", "Seus dados de nascimento não são guardados nos nossos servidores enquanto você olha sua carta. Se você ler sua leitura grátis, sua carta e sua leitura ficam só neste navegador por 24 horas. Se você comprar o relatório, a carta fica guardada para entregá-lo."],
  ] as const)("%s: con precio la nota de privacidad dice lo que de verdad pasa", (locale, texto) => {
    pintar(locale, { precio: "US$ 29" });
    expect(screen.getByText(texto)).toBeTruthy();
  });

  it.each(LOCALES)("%s: la nota de privacidad existe y cambia con y sin precio", (locale) => {
    const t = getDict(locale).newChart;
    expect(t.previewPrivacidad).toBeTruthy();
    expect(t.previewPrivacidadSinCompra).toBeTruthy();
    expect(t.previewPrivacidad).not.toBe(t.previewPrivacidadSinCompra);
  });

  it("sin precio no se muestra el botón de pago ni la nota", () => {
    pintar("es", { precio: null });

    expect(screen.queryByRole("button", { name: /Leer el informe completo/ })).toBeNull();
    expect(screen.queryByRole("link", { name: getDict("es").newChart.legalTerminos })).toBeNull();
  });

  it("mientras la compra está en curso el botón queda deshabilitado", () => {
    pintar("es", { comprando: true });
    const boton = screen.getByRole("button", { name: getDict("es").precios.abriendo });

    expect((boton as HTMLButtonElement).disabled).toBe(true);
  });

  it("muestra el error de la compra", () => {
    pintar("es", { errorCompra: "No pudimos abrir el pago." });

    expect(screen.getByRole("alert").textContent).toBe("No pudimos abrir el pago.");
  });
});

describe("el teaser y el índice del informe", () => {
  it.each(LOCALES)("%s: el orden es bloques, índice, compra, rueda y datos", (locale) => {
    const { container } = render(<CartaPreview {...propsBase(locale)} />);
    const t = getDict(locale).newChart;
    const orden = [
      container.querySelector(".teaserBloques"),
      container.querySelector(".teaserIndice"),
      screen.getByRole("button", { name: t.comprarCta.replace("{precio}", "US$ 29") }),
      container.querySelector(".chartBody"),
      container.querySelector(".datosCarta"),
    ];
    orden.forEach((el) => expect(el).not.toBeNull());
    for (let i = 0; i < orden.length - 1; i++) {
      expect(orden[i]!.compareDocumentPosition(orden[i + 1]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("cada bloque lleva «{cuerpo} en {signo}» y su párrafo en el idioma de la página", () => {
    pintar("es");
    expect(screen.getByText("Sol en Géminis")).toBeTruthy();
    expect(screen.getByText("Párrafo del Sol.")).toBeTruthy();
    expect(screen.getByText("Ascendente en Leo")).toBeTruthy();
    cleanup();
    pintar("en");
    expect(screen.getByText("Sun in Gemini")).toBeTruthy();
    expect(screen.getByText("Sun paragraph.")).toBeTruthy();
  });

  it("el índice muestra cada sección y sus temas como bloqueados", () => {
    pintar("es");
    const t = getDict("es").newChart;
    expect(screen.getByText("Identidad y propósito")).toBeTruthy();
    expect(screen.getByText("Tu Marte en Casa 10")).toBeTruthy();
    // Sólo los dos temas llevan candado; una sección sin temas muestra el título.
    expect(screen.getAllByLabelText(t.temaBloqueado)).toHaveLength(2);
    expect(screen.getByText("Vínculos")).toBeTruthy();
  });

  it.each([
    ["es", "8 secciones escritas para tu carta, unas 6.200 palabras, en tu idioma."],
    ["en", "8 sections written for your chart, about 6,200 words, in your language."],
    ["pt", "8 seções escritas para o seu mapa, cerca de 6.200 palavras, no seu idioma."],
  ] as const)("%s: la línea de qué trae el informe usa los números del teaser", (locale, texto) => {
    pintar(locale);
    expect(screen.getByText(texto)).toBeTruthy();
  });

  it("no queda nada de la lectura anónima", () => {
    pintar("es");
    const t = getDict("es").newChart;
    expect(screen.queryByText(t.previewCta)).toBeNull();
    expect(screen.queryByText(t.previewNote)).toBeNull();
    expect(screen.queryByText(t.lecturaEscribiendo)).toBeNull();
    expect(screen.queryByRole("button", { name: t.lecturaReintentar })).toBeNull();
  });

  it("sin teaser (backend viejo) muestra la compra, la rueda y los datos sin romper", () => {
    pintar("es", { carta: CARTA });
    expect(screen.getByRole("button", { name: /Leer el informe completo/ })).toBeTruthy();
    expect(screen.queryByText(/secciones escritas/)).toBeNull();
    expect(screen.getByText(getDict("es").newChart.previewTitle)).toBeTruthy();
  });
});
