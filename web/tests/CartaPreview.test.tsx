import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CartaPreview } from "@/components/CartaPreview";
import { getDict, LOCALES } from "@/lib/i18n";
import type { EstadoLectura } from "@/components/useLecturaAnonima";

// El botón de pago de la vista previa es secundario: el principal sigue siendo
// la lectura gratis, que se escribe ahí mismo, sin cuenta. Y sin precio no hay botón: el precio
// sale del catálogo y no se inventa.

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

afterEach(cleanup);

function pintar(locale: "es" | "en" | "pt", extra: Partial<Parameters<typeof CartaPreview>[0]> = {}) {
  const props = {
    carta: CARTA,
    dict: getDict(locale),
    locale,
    lectura: { tipo: "nada" } as EstadoLectura,
    onPedirLectura: vi.fn(),
    onReintentar: vi.fn(),
    onVolver: vi.fn(),
    precio: "US$ 29",
    onComprar: vi.fn().mockResolvedValue(undefined),
    comprando: false,
    errorCompra: null,
    ...extra,
  };
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

  it("el principal gratis va primero y el de pago es secundario, debajo", () => {
    pintar("es");
    const t = getDict("es").newChart;
    const gratis = screen.getByRole("button", { name: t.previewCta });
    const pago = screen.getByRole("button", { name: /Leer el informe completo/ });

    expect(gratis.className).toContain("btnPrimary");
    expect(pago.className).not.toContain("btnPrimary");
    expect(gratis.compareDocumentPosition(pago) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("apretarlo llama a onComprar y no manda a entrar", () => {
    const { onComprar, onPedirLectura } = pintar("es");
    fireEvent.click(screen.getByRole("button", { name: /Leer el informe completo/ }));

    expect(onComprar).toHaveBeenCalledTimes(1);
    expect(onPedirLectura).not.toHaveBeenCalled();
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
    expect(screen.getByRole("button", { name: getDict("es").newChart.previewCta })).toBeTruthy();
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

describe("la lectura breve en la vista previa", () => {
  it("con la lectura lista la muestra con el disclaimer y saca el botón de pedir", () => {
    pintar("es", { lectura: { tipo: "lista", texto: "Tu Sol en Escorpio", lang: "es", disclaimer: "Entretenimiento." } });
    expect(screen.getByText(/Tu Sol en Escorpio/)).toBeInTheDocument();
    expect(screen.getByText("Entretenimiento.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: getDict("es").newChart.previewCta })).toBeNull();
  });

  it("«usada» muestra la carta nueva y ofrece el informe", () => {
    pintar("es", { lectura: { tipo: "usada" } });
    expect(screen.getByText(getDict("es").newChart.lecturaUsada)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Leer el informe completo/ })).toBeInTheDocument();
  });

  it("en otro idioma lo avisa", () => {
    pintar("en", { lectura: { tipo: "lista", texto: "t", lang: "es", disclaimer: "" } });
    expect(screen.getByText("Your reading is in Spanish.")).toBeInTheDocument();
  });

  it("fallida ofrece reintentar", () => {
    const onReintentar = vi.fn();
    pintar("es", { lectura: { tipo: "fallida" }, onReintentar });
    fireEvent.click(screen.getByRole("button", { name: getDict("es").newChart.lecturaReintentar }));
    expect(onReintentar).toHaveBeenCalled();
  });
});
