import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChartShare } from "@/components/ChartShare";
import { SAMPLE_CHART } from "@/content/sample-chart";
import { getDict } from "@/lib/i18n";

const dict = getDict("es");
const CHART = "89151d40-e263-4d34-81e0-2fb434f70243";

const payload = {
  labels: {
    brand_tagline: "Tu carta natal",
    eyebrow: "Carta natal",
    chart_name: "Camila",
    birth_line: "12 de marzo de 1994 · Buenos Aires",
    positions: "Posiciones",
    aspects: "Aspectos",
    reading: "Tu lectura",
    made_with: "Hecho con ASTRA",
  },
  positions: [],
  aspects: [],
  wheel: null,
};

function renderShare(readingLang: "es" | "en" | "pt" | null = null, locale: "es" | "en" = "es") {
  return render(
    <ChartShare
      chartId={CHART}
      payload={payload}
      wheel={SAMPLE_CHART}
      readingLang={readingLang}
      dict={locale === "es" ? dict : getDict("en")}
      locale={locale}
    />,
  );
}

/** El PDF que devolvería el proxy: sólo se usan `ok`, `blob` y los headers. */
function pdfOk() {
  return {
    ok: true,
    status: 200,
    blob: async () => new Blob([new Uint8Array([37, 80, 68, 70])], { type: "application/pdf" }),
    headers: new Headers({ "content-disposition": "attachment; filename*=UTF-8''Jo%C3%A3o.pdf" }),
  };
}

/** Las firmas se declaran para poder leer `mock.calls`, no para usarlas. */
type Fetch = (url: string, init: { body: string }) => Promise<ReturnType<typeof pdfOk>>;
type Share = (data: { files: File[]; title: string }) => Promise<void>;

const click = (nombre: string) => fireEvent.click(screen.getByRole("button", { name: nombre }));

beforeEach(() => {
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:x"),
    revokeObjectURL: vi.fn(),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ChartShare", () => {
  it("ofrece el PDF y la imagen aunque la carta no tenga lectura", () => {
    renderShare(null);
    expect(screen.getByRole("button", { name: dict.share.pdf })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: dict.share.image })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: dict.share.pdfWithReading })).toBeNull();
  });

  it("el botón con la lectura aparece sólo cuando la lectura existe", () => {
    renderShare("es");
    expect(screen.getByRole("button", { name: dict.share.pdfWithReading })).toBeInTheDocument();
  });

  it("si la lectura está en otro idioma, el botón lo dice", () => {
    renderShare("es", "en");
    const en = getDict("en");
    const esperado = en.share.pdfWithReadingIn.replace("{lang}", en.share.langNames.es);
    expect(screen.getByRole("button", { name: esperado })).toBeInTheDocument();
  });

  it("el PDF de la carta no pide la lectura", async () => {
    const fetchMock = vi.fn<Fetch>(async () => pdfOk());
    vi.stubGlobal("fetch", fetchMock);
    renderShare("es");

    click(dict.share.pdf);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0]![1].body);
    expect(body.reading_lang).toBeNull();
  });

  it("el PDF con la lectura la pide en el idioma en que está escrita", async () => {
    const fetchMock = vi.fn<Fetch>(async () => pdfOk());
    vi.stubGlobal("fetch", fetchMock);
    renderShare("es", "en");

    const en = getDict("en");
    click(en.share.pdfWithReadingIn.replace("{lang}", en.share.langNames.es));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body).reading_lang).toBe("es");
  });

  it("usa la hoja de compartir del sistema cuando el navegador la tiene", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => pdfOk()));
    const share = vi.fn<Share>(async () => undefined);
    vi.stubGlobal("navigator", { canShare: () => true, share });
    renderShare();

    click(dict.share.pdf);

    await waitFor(() => expect(share).toHaveBeenCalled());
    const archivo = share.mock.calls[0]![0].files[0]!;
    // El nombre viaja con sus acentos, no percent-encoded.
    expect(archivo.name).toBe("João.pdf");
  });

  it("si el navegador no comparte archivos, descarga", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => pdfOk()));
    vi.stubGlobal("navigator", {});
    const click_ = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderShare();

    click(dict.share.pdf);

    await waitFor(() => expect(click_).toHaveBeenCalled());
  });

  it("cancelar la hoja de compartir no es un error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => pdfOk()));
    vi.stubGlobal("navigator", {
      canShare: () => true,
      share: vi.fn(async () => {
        throw new DOMException("cancelado", "AbortError");
      }),
    });
    renderShare();

    click(dict.share.pdf);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: dict.share.pdf })).toBeEnabled(),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("un fallo del backend se ve", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 502 })));
    renderShare();

    click(dict.share.pdf);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(dict.share.failed));
  });
});
