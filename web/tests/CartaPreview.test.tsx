import { readFileSync } from "node:fs";
import { join } from "node:path";

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

    // Dos: uno arriba, al lado del título, y el grande del cierre (18-10-2026).
    expect(screen.getAllByRole("button", { name: t.comprarCta.replace("{precio}", "US$ 29") })).toHaveLength(2);
    const terminos = screen.getByRole("link", { name: t.legalTerminos });
    const privacidad = screen.getByRole("link", { name: t.legalPrivacidad });
    expect(terminos.getAttribute("href")).toBe(`/${locale}/legal/terms`);
    expect(privacidad.getAttribute("href")).toBe(`/${locale}/legal/privacy`);
  });

  it("los dos botones de compra son principales y el del cierre es el grande", () => {
    pintar("es");
    const [arriba, cierre] = screen.getAllByRole("button", { name: /Leer el informe completo/ });
    expect(arriba!.className).toContain("btnPrimary");
    expect(cierre!.className).toContain("btnPrimary");
    expect(cierre!.className).toContain("btnGrande");
    expect(arriba!.className).not.toContain("btnGrande");
  });

  it.each([0, 1])("apretar el botón %i llama a onComprar y no manda a entrar", (i) => {
    const { onComprar } = pintar("es");
    fireEvent.click(screen.getAllByRole("button", { name: /Leer el informe completo/ })[i]!);

    expect(onComprar).toHaveBeenCalledTimes(1);
  });

  it("la nota de privacidad no promete que no se guarda nada: abrir el pago guarda la carta", () => {
    pintar("es");
    expect(screen.getByText(/Si comprás el informe, la carta queda guardada para entregártelo\./)).toBeTruthy();
    expect(screen.queryByText(/No guardamos nada de esto\. /)).toBeNull();
  });

  it("sin precio también se puede comprar, así que la nota es la misma", () => {
    pintar("es", { precio: null });
    expect(screen.getByText(/Si comprás el informe, la carta queda guardada para entregártelo\./)).toBeTruthy();
  });

  // Con precio (el caso normal) la nota dice las dos cosas ciertas: nada en el
  // servidor mientras mira, y la carta guardada sólo si compra. Ni una palabra
  // de lectura gratis ni de guardado en el navegador: ya no existen.
  it.each([
    ["es", "Tus datos de nacimiento no se guardan en nuestros servidores mientras mirás tu carta. Si comprás el informe, la carta queda guardada para entregártelo."],
    ["en", "Your birth details aren't stored on our servers while you look at your chart. If you buy the report, the chart is saved so we can deliver it."],
    ["pt", "Seus dados de nascimento não são guardados nos nossos servidores enquanto você olha sua carta. Se você comprar o relatório, a carta fica guardada para entregá-lo."],
  ] as const)("%s: con precio la nota de privacidad dice lo que de verdad pasa", (locale, texto) => {
    pintar(locale, { precio: "US$ 29" });
    expect(screen.getByText(texto)).toBeTruthy();
  });

  // Si el catálogo no respondió, el botón sigue: comprar no depende del precio
  // (lo arma el backend y Stripe lo muestra antes de cobrar). Antes del
  // 17-10-2026 sin precio no había botón, y con la breve gratis apagada la
  // pantalla quedaba con candados y sin ninguna salida.
  it.each(LOCALES)("%s: sin precio el botón de pago sigue, sin precio en el texto", (locale) => {
    pintar(locale, { precio: null });
    const t = getDict(locale).newChart;

    expect(screen.getAllByRole("button", { name: t.comprarCtaSinPrecio })).toHaveLength(2);
    expect(screen.getByRole("link", { name: t.legalTerminos })).toBeTruthy();
    expect(t.comprarCtaSinPrecio).not.toContain("{precio}");
  });

  it("mientras la compra está en curso el botón queda deshabilitado", () => {
    pintar("es", { comprando: true });
    const botones = screen.getAllByRole("button", { name: getDict("es").precios.abriendo });

    expect(botones).toHaveLength(2);
    botones.forEach((b) => expect((b as HTMLButtonElement).disabled).toBe(true));
  });

  it("muestra el error de la compra", () => {
    pintar("es", { errorCompra: "No pudimos abrir el pago." });

    expect(screen.getByRole("alert").textContent).toBe("No pudimos abrir el pago.");
  });
});

describe("el teaser y el índice del informe", () => {
  it.each(LOCALES)("%s: el orden es compra, rueda, datos, bloques, índice y compra grande", (locale) => {
    const { container } = render(<CartaPreview {...propsBase(locale)} />);
    const t = getDict(locale).newChart;
    const [arriba, cierre] = screen.getAllByRole("button", { name: t.comprarCta.replace("{precio}", "US$ 29") });
    const orden = [
      arriba,
      container.querySelector(".chartBody"),
      // Los datos son de la rueda: van con ella, y la compra grande queda
      // última antes del pie (18-10-2026).
      container.querySelector(".datosCarta"),
      container.querySelector(".teaserBloques"),
      screen.getByRole("heading", { name: t.indiceTitulo }),
      container.querySelector(".teaserIndice"),
      cierre,
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
    expect(screen.getAllByRole("button", { name: /Leer el informe completo/ }).length).toBeGreaterThan(0);
    expect(screen.queryByText(/secciones escritas/)).toBeNull();
    expect(screen.getByText(getDict("es").newChart.previewTitle)).toBeTruthy();
  });
});


describe("los bloques del adelanto", () => {
  it("van de a dos por fila, no de a tres (18-10-2026)", () => {
    // jsdom no calcula el grid: se chequea la regla en el CSS.
    const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");
    const regla = css.match(/\.teaserBloques\s*\{[^}]*\}/)![0];
    expect(regla).toMatch(/grid-template-columns:\s*repeat\(2,/);
  });
});

describe("la página con la carta calculada (18-10-2026)", () => {
  const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");

  it("«Tu carta natal» es el título de la página", () => {
    pintar("es");
    expect(screen.getByRole("heading", { level: 1, name: getDict("es").newChart.previewTitle })).toBeTruthy();
  });

  it("la página pasa al ancho del sitio y el encabezado del formulario se esconde", () => {
    expect(css).toMatch(/\.formFrame:has\(\.previewCarta\)\s*\{[^}]*max-width:\s*var\(--ancho-sitio\)/);
    expect(css).toMatch(/\.formFrame:has\(\.previewCarta\)\s*>\s*\.formHead\s*\{[^}]*display:\s*none/);
  });

  it("la rueda grande es la misma en la vista previa y en la carta con cuenta", () => {
    expect(css).toMatch(/\n\.wheelHolderWide\s*\{[^}]*width:\s*min\(100%,\s*52rem\)/);
  });

  it("el título de la carta con cuenta usa el mismo paso que el de la vista previa", () => {
    expect(css).toMatch(/\.chartName\s*\{[^}]*font-size:\s*var\(--step-4\)/);
  });
});

describe("el título de la vista previa", () => {
  it("tiene el tamaño del título de la home, no el de una página angosta", () => {
    const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");
    expect(css).toMatch(/\.previewTitle\s*\{[^}]*font-size:\s*var\(--step-4\)/);
  });
});


describe("el error de la compra aparece junto al botón que se apretó", () => {
  it("si se apretó el de arriba, el error va arriba, antes de la rueda", () => {
    const props = propsBase("es");
    const { container, rerender } = render(<CartaPreview {...props} />);
    fireEvent.click(screen.getAllByRole("button", { name: /Leer el informe completo/ })[0]!);
    rerender(<CartaPreview {...props} errorCompra="No pudimos abrir el pago." />);

    const alertas = screen.getAllByRole("alert");
    expect(alertas).toHaveLength(1);
    const rueda = container.querySelector(".chartBody")!;
    expect(alertas[0]!.compareDocumentPosition(rueda) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("si se apretó el grande, el error va abajo, junto a él", () => {
    const props = propsBase("es");
    const { container, rerender } = render(<CartaPreview {...props} />);
    fireEvent.click(screen.getAllByRole("button", { name: /Leer el informe completo/ })[1]!);
    rerender(<CartaPreview {...props} errorCompra="No pudimos abrir el pago." />);

    const alerta = screen.getByRole("alert");
    expect(container.querySelector(".previewCta")!.contains(alerta)).toBe(true);
  });
});

describe("la medida de los párrafos no pisa la de cada componente", () => {
  it("la regla general no tiene especificidad (:where), así gana la clase del párrafo", () => {
    const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");
    expect(css).toMatch(/:where\(\.docFrame\) p\s*\{/);
    expect(css).not.toMatch(/\n\.docFrame p\s*\{/);
  });
});

// Lo que hace quien calculó su carta sin cuenta, contado en el servidor sin
// cookies (20-10-2026): con ~200 cartas y 0 pagos no se sabía dónde se cortaban.
describe("conteo de los pasos del teaser", () => {
  function contados(fetchMock: ReturnType<typeof vi.fn>) {
    return fetchMock.mock.calls
      .filter(([url]) => url === "/api/conteo/teaser")
      .map(([, init]) => JSON.parse((init as RequestInit).body as string));
  }

  function conFetch() {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("el clic en el botón de arriba cuenta la posición y la moneda", () => {
    const fetchMock = conFetch();
    pintar("es", { moneda: "usd" });
    const [arriba] = screen.getAllByRole("button", { name: /US\$ 29/ });

    fireEvent.click(arriba);

    expect(contados(fetchMock)).toEqual([{ evento: "clic_arriba", moneda: "usd" }]);
  });

  it("el clic en el botón grande del final cuenta clic_cierre", () => {
    const fetchMock = conFetch();
    pintar("es", { moneda: "brl" });
    const botones = screen.getAllByRole("button", { name: /US\$ 29/ });

    fireEvent.click(botones[botones.length - 1]);

    expect(contados(fetchMock)).toEqual([{ evento: "clic_cierre", moneda: "brl" }]);
  });

  it("en pesos, mandar el mail cuenta mail_enviado además del clic", () => {
    const fetchMock = conFetch();
    pintar("es", { moneda: "ars", pideMail: true });
    const t = getDict("es").newChart;
    fireEvent.click(screen.getAllByRole("button", { name: /US\$ 29/ })[0]);

    fireEvent.change(screen.getByLabelText(t.mailLabel), { target: { value: "ana@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: t.mailPagar }));

    expect(contados(fetchMock)).toEqual([
      { evento: "clic_arriba", moneda: "ars" },
      { evento: "mail_enviado", moneda: "ars" },
    ]);
  });

  it("volver a los datos cuenta volver", () => {
    const fetchMock = conFetch();
    pintar("es", { moneda: "usd" });

    fireEvent.click(screen.getByRole("button", { name: getDict("es").newChart.navNew }));

    expect(contados(fetchMock)).toEqual([{ evento: "volver" }]);
  });

  it("abrir los datos de la carta cuenta una sola vez", () => {
    const fetchMock = conFetch();
    const { container } = render(<CartaPreview {...propsBase("es", { moneda: "usd" })} />);
    const datos = container.querySelector("details.datosCarta") as HTMLDetailsElement;

    for (let i = 0; i < 3; i++) {
      datos.open = !datos.open;
      fireEvent(datos, new Event("toggle"));
    }

    expect(contados(fetchMock)).toEqual([{ evento: "datos_abiertos" }]);
  });

  it("llegar al final cuenta una sola vez, aunque se vuelva a pasar", () => {
    const fetchMock = conFetch();
    let avisar: (entradas: { isIntersecting: boolean }[]) => void = () => {};
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(cb: typeof avisar) {
          avisar = cb;
        }
        observe() {}
        disconnect() {}
      },
    );
    pintar("es", { moneda: "usd" });

    avisar([{ isIntersecting: false }]);
    avisar([{ isIntersecting: true }]);
    avisar([{ isIntersecting: true }]);

    expect(contados(fetchMock)).toEqual([{ evento: "cierre_visto" }]);
  });

  it("si contar falla, la compra sigue igual", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("sin red")));
    const props = pintar("es", { moneda: "usd" });

    fireEvent.click(screen.getAllByRole("button", { name: /US\$ 29/ })[0]);

    expect(props.onComprar).toHaveBeenCalledOnce();
  });
});
