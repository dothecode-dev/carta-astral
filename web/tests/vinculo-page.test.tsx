import { readFileSync } from "node:fs";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SinastriaPage, { generateMetadata as metaSinastria } from "@/app/[locale]/sinastria/page";
import SynastryPage, { generateMetadata as metaSynastry } from "@/app/[locale]/synastry/page";
import { VINCULO } from "@/content/vinculo";
import { SITE_URL } from "@/lib/config";
import { SYNASTRY_SLUG } from "@/lib/i18n";

// Las dos landings de Vínculo. `pt` comparte carpeta con `es`: el slug es el
// mismo, así que `/en/sinastria` y `/es/synastry` existen como carpetas y NO
// son páginas. Lo que se prueba acá es cuándo la ruta responde y cuándo es 404.
//
// La forma (Nav, main, Footer) la chequea `esqueleto.test.ts`.

const vinculo = vi.hoisted(() => ({ activo: true }));
vi.mock("@/lib/vinculo", async (original) => ({
  ...(await original<typeof import("@/lib/vinculo")>()),
  vinculoActivo: async () => vinculo.activo,
}));
vi.mock("@/lib/session", () => ({ haySesion: async () => false }));

const navProps = vi.hoisted(() => ({ ultimo: null as null | { path: (c: string) => string } }));
vi.mock("@/components/Nav", () => ({
  Nav: (props: { path: (c: string) => string }) => {
    navProps.ultimo = props;
    return <nav data-testid="nav" />;
  },
}));
vi.mock("@/components/Footer", () => ({ Footer: () => <footer data-testid="footer" /> }));
// El formulario y el resultado tienen sus propios tests.
vi.mock("@/components/VinculoPagina", () => ({
  VinculoPagina: ({ locale }: { locale: string }) => <div data-testid="pagina" data-locale={locale} />,
}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

const params = (locale: string) => ({ params: Promise.resolve({ locale }) });

beforeEach(() => {
  vinculo.activo = true;
  navProps.ultimo = null;
});

describe("/sinastria (es y pt)", () => {
  it.each(["es", "pt"] as const)("%s: muestra el título y el formulario", async (locale) => {
    render(await SinastriaPage(params(locale)));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(VINCULO[locale].title);
    expect(screen.getByTestId("pagina")).toHaveAttribute("data-locale", locale);
    expect(screen.getByRole("main")).toContainElement(screen.getByTestId("pagina"));
  });

  it("el selector de idioma del nav lleva a la landing de cada idioma", async () => {
    render(await SinastriaPage(params("es")));
    const path = navProps.ultimo!.path;
    expect(path("es")).toBe("/sinastria");
    expect(path("en")).toBe("/synastry");
    expect(path("pt")).toBe("/sinastria");
  });

  it("apagado: 404", async () => {
    vinculo.activo = false;
    await expect(SinastriaPage(params("es"))).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("en inglés no es una página: /en/sinastria es 404", async () => {
    await expect(SinastriaPage(params("en"))).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("un idioma que no existe es 404", async () => {
    await expect(SinastriaPage(params("fr"))).rejects.toThrow("NEXT_NOT_FOUND");
  });
});

describe("/synastry (en)", () => {
  it("en: muestra el título y el formulario", async () => {
    render(await SynastryPage(params("en")));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(VINCULO.en.title);
    expect(screen.getByTestId("pagina")).toHaveAttribute("data-locale", "en");
  });

  it("apagado: 404", async () => {
    vinculo.activo = false;
    await expect(SynastryPage(params("en"))).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it.each(["es", "pt"])("/%s/synastry es 404", async (locale) => {
    await expect(SynastryPage(params(locale))).rejects.toThrow("NEXT_NOT_FOUND");
  });
});

describe("metadatos", () => {
  it.each([
    ["es", metaSinastria],
    ["pt", metaSinastria],
    ["en", metaSynastry],
  ] as const)("%s: canonical absoluto, los tres idiomas y x-default", async (locale, meta) => {
    const m = await meta(params(locale));
    const t = VINCULO[locale];
    expect(m.title).toBe(`${t.metaTitle} · ASTRA`);
    expect(m.description).toBe(t.metaDescription);
    expect(m.alternates?.canonical).toBe(`${SITE_URL}/${locale}/${SYNASTRY_SLUG[locale]}`);
    expect(m.alternates?.languages).toEqual({
      es: `${SITE_URL}/es/sinastria`,
      en: `${SITE_URL}/en/synastry`,
      pt: `${SITE_URL}/pt/sinastria`,
      "x-default": `${SITE_URL}/es/sinastria`,
    });
  });

  it("comparte con las redes: título, descripción y url del idioma", async () => {
    const m = await metaSinastria(params("pt"));
    expect(m.openGraph).toMatchObject({
      type: "website",
      locale: "pt",
      url: `${SITE_URL}/pt/sinastria`,
      description: VINCULO.pt.metaDescription,
    });
    expect(m.twitter).toMatchObject({ card: "summary_large_image" });
  });

  it("una combinación que no es página no tiene metadatos", async () => {
    expect(await metaSinastria(params("en"))).toEqual({});
    expect(await metaSynastry(params("es"))).toEqual({});
  });
});

// vitest no puede ejecutar el build de Next, y esto sólo se ve ahí. Sin
// `force-dynamic`, una landing construida con el flag apagado queda prerenderizada
// como 404 (`notFound()` se lanza antes de `haySesion()`) y, al encender el flag,
// cada regeneración falla con DYNAMIC_SERVER_USAGE y sigue sirviendo el 404: la
// página no aparece nunca. Ningún otro test ni el build lo detectan (se comprobó
// el 05-10-2026 con un backend de mentira), así que se fija leyendo el fuente,
// como `esqueleto.test.ts`.
describe("las landings son siempre dinámicas", () => {
  it.each(["sinastria", "synastry"])("%s declara force-dynamic", (carpeta) => {
    const fuente = readFileSync(`app/[locale]/${carpeta}/page.tsx`, "utf8");
    expect(fuente).toMatch(/^export const dynamic = "force-dynamic";$/m);
  });
});
