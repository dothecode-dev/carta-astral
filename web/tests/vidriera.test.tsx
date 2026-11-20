import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

import { CartaPreview } from "@/components/CartaPreview";
import { Footer } from "@/components/Footer";
import { LegalDocument } from "@/components/LegalDocument";
import { Nav } from "@/components/Nav";
import sitemap from "@/app/sitemap";
import { getDict } from "@/lib/i18n";
import { cerradaEnVidriera, esVidriera, TEXTOS_VIDRIERA } from "@/lib/vidriera";

// Modo vidriera (NEXT_PUBLIC_VIDRIERA=1): el sitio como muestra de trabajo. No
// se cobra, no hay cuentas: nada en pantalla ofrece comprar ni entrar, y las
// páginas que sólo sirven para eso responden 404. Apagado, nada cambia.

vi.mock("@/lib/notes", () => ({ fetchNotesOrNone: async () => [] }));
vi.mock("@/lib/vinculo", async (original) => ({
  ...(await original<typeof import("@/lib/vinculo")>()),
  vinculoActivo: async () => false,
}));

const dict = getDict("es");

const CARTA = {
  data: {
    placements: [{ name: "Sun", sign: "Gem", abs_pos: 70.5, house: "First_House", retrograde: false }],
    houses: null,
    angles: null,
    aspects: [],
    flags: { moon_approximate: false, precision_degraded: false, bodies_missing: false, house_system_fallback: false },
  },
  teaser: {
    bloques: [{ cuerpo: "Sun", signo: "Gem", textos: { es: "Párrafo del Sol.", en: "Sun.", pt: "Sol." } }],
    indice: [{ slug: "identidad", titulos: { es: "Identidad", en: "Identity", pt: "Identidade" }, temas: [] }],
    informe: { secciones: 8, palabras: 6200 },
  },
};

const pedir = (pathname: string) =>
  ({
    nextUrl: new URL(pathname, "https://astra.dothecode.com"),
    headers: { get: () => null },
  }) as unknown as NextRequest;

async function cargarProxy() {
  vi.resetModules();
  return (await import("@/proxy")).proxy;
}

beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }),
  );
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ mantenimiento: false }) }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("modo vidriera", () => {
  it("viene apagado", () => {
    expect(esVidriera()).toBe(false);
  });

  it("cierra las páginas de compra y de cuenta, en cualquier idioma", () => {
    for (const ruta of ["/es/entrar", "/en/precios", "/pt/cuenta", "/es/compra", "/es/arrepentimiento", "/es/carta/abc"]) {
      expect(cerradaEnVidriera(ruta), ruta).toBe(true);
    }
    for (const ruta of ["/es", "/es/nueva", "/es/ejemplo", "/es/cielo-hoy", "/es/notas/las-12-casas", "/es/legal/terms"]) {
      expect(cerradaEnVidriera(ruta), ruta).toBe(false);
    }
  });

  it("el proxy responde 404 en esas páginas sólo con el modo prendido", async () => {
    let proxy = await cargarProxy();
    expect((await proxy(pedir("/es/precios"))).status).toBe(200);

    vi.stubEnv("NEXT_PUBLIC_VIDRIERA", "1");
    proxy = await cargarProxy();
    for (const ruta of ["/es/precios", "/es/entrar", "/en/cuenta", "/pt/carta/abc"]) {
      const res = await proxy(pedir(ruta));
      expect(res.status, ruta).toBe(404);
      expect(res.headers.get("cache-control")).toBe("no-store");
    }
    expect((await proxy(pedir("/es/nueva"))).status).toBe(200);
  });

  it("la navegación no ofrece precios ni entrar", () => {
    vi.stubEnv("NEXT_PUBLIC_VIDRIERA", "1");
    render(<Nav locale="es" dict={dict} path="/nueva" />);
    const destinos = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(destinos).not.toContain("/es/precios");
    expect(destinos).not.toContain("/es/entrar");
    expect(destinos).not.toContain("/es/cuenta");
    expect(destinos).toContain("/es/nueva");
  });

  it("apagado, la navegación los sigue ofreciendo", () => {
    render(<Nav locale="es" dict={dict} path="/nueva" />);
    const destinos = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(destinos).toContain("/es/precios");
    expect(destinos).toContain("/es/entrar");
  });

  it("el pie dice que es una muestra y no lleva al arrepentimiento ni al dato fiscal", () => {
    vi.stubEnv("NEXT_PUBLIC_VIDRIERA", "1");
    render(<Footer locale="es" dict={dict} />);
    const destinos = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(destinos).not.toContain("/es/arrepentimiento");
    expect(screen.queryByAltText("Data Fiscal")).toBeNull();
    // El mail era del dominio que se dio de baja: en la muestra no hay contacto.
    expect(destinos.some((d) => d?.startsWith("mailto:"))).toBe(false);
    expect(screen.getByText(/muestra/i)).toBeTruthy();
  });

  it("la carta sin cuenta no tiene botón de compra ni precio: lleva al informe de ejemplo", () => {
    vi.stubEnv("NEXT_PUBLIC_VIDRIERA", "1");
    const onComprar = vi.fn();
    render(
      <CartaPreview
        carta={CARTA as never}
        dict={dict}
        locale="es"
        onVolver={() => {}}
        precio="US$ 19,90"
        onComprar={onComprar}
        comprando={false}
        errorCompra={null}
      />,
    );
    expect(document.body.textContent).not.toContain("US$ 19,90");
    expect(screen.queryByRole("button", { name: /informe completo/i })).toBeNull();
    const ejemplo = screen.getAllByRole("link").filter((a) => a.getAttribute("href") === "/es/ejemplo");
    expect(ejemplo.length).toBeGreaterThan(0);
    // El índice del informe sigue a la vista: es lo que se está mostrando.
    expect(screen.getByText("Identidad")).toBeTruthy();
  });

  it("los legales no muestran el mail de contacto", () => {
    const doc = { heading: "Términos", blocks: [] };
    const { container, rerender } = render(
      <LegalDocument doc={doc as never} updatedLabel="Actualizado" updated="2026-10-20" />,
    );
    expect(container.querySelector('a[href^="mailto:"]')).toBeNull();
    // Con contacto (el sitio vendiendo) sigue saliendo.
    rerender(<LegalDocument doc={doc as never} updatedLabel="Actualizado" updated="2026-10-20" contact="a@b.com" />);
    expect(container.querySelector('a[href="mailto:a@b.com"]')).not.toBeNull();
  });

  it("apagado, el pie conserva el contacto", () => {
    render(<Footer locale="es" dict={dict} />);
    const destinos = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(destinos.some((d) => d?.startsWith("mailto:"))).toBe(true);
  });

  it("el diccionario no habla de cuentas, de guardar ni de pagar en lo que queda a la vista", () => {
    vi.stubEnv("NEXT_PUBLIC_VIDRIERA", "1");

    // Lo que se lee de promesa de venta o de cuenta en cada idioma. No es una
    // lista de palabras prohibidas en todo el sitio: es lo que estas claves
    // decían antes y no puede volver.
    const VENTA = {
      es: /tu cuenta|entr[aá]s con|guard[aá]s|se paga|compr[aá]s|no cuesta/i,
      en: /your account|sign in|you save|you pay|if you buy|costs nothing/i,
      pt: /sua conta|entra com|você salva|se paga|se você comprar|não custa/i,
    };
    for (const locale of ["es", "en", "pt"] as const) {
      const d = getDict(locale);
      const visible = [
        d.privacy.title,
        ...d.privacy.points.flatMap((p) => [p.strong, p.rest]),
        ...d.faq.items.flatMap((i) => [i.q, i.a]),
        d.newChart.previewPrivacidad,
        d.newChart.seoGratis,
        d.newChart.seoGratisBody,
        TEXTOS_VIDRIERA[locale].ejemploNota,
      ];
      for (const texto of visible) {
        expect(texto, `${locale}: ${texto}`).not.toMatch(VENTA[locale]);
      }
      // Cuatro preguntas propias del modo después de las tres que se conservan.
      expect(d.faq.items).toHaveLength(7);
      expect(d.privacy.points).toHaveLength(3);
    }
  });

  it("apagado, el diccionario es el de siempre", () => {
    expect(getDict("es").privacy.title).toBe("Tus datos de nacimiento no salen de tu cuenta.");
    expect(getDict("es").faq.items).toHaveLength(6);
    expect(getDict("es").newChart.seoGratisBody).toContain("lo único que se paga");
  });

  it("los legales avisan arriba que describen el sitio cuando se vendía", () => {
    const doc = { title: "t", heading: "Política", blocks: [{ kind: "p" as const, text: "Cuerpo." }] };

    render(<LegalDocument doc={doc} updatedLabel="Actualizado" updated="2026-10-20" aviso={TEXTOS_VIDRIERA.es.legal} />);

    expect(screen.getByRole("note").textContent).toContain("muestra de trabajo");
  });

  it("el sitemap no lista precios", async () => {
    vi.stubEnv("NEXT_PUBLIC_VIDRIERA", "1");
    const urls = (await sitemap()).map((e) => e.url);
    expect(urls.some((u) => u.endsWith("/precios"))).toBe(false);
    expect(urls.some((u) => u.endsWith("/nueva"))).toBe(true);
  });
});
