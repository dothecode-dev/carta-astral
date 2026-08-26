"use client";

import { useState } from "react";

import type { SampleChart } from "@/content/sample-chart";
import type { Dict, Locale } from "@/lib/i18n";
import type { PdfPayload } from "@/lib/pdfPayload";
import { renderStoryCard } from "@/lib/storyCard";

// Llevarse la carta: el PDF y la imagen para historias.
//
// Va en su propio componente y no dentro de `ChartActions` porque aquél devuelve
// null cuando la carta ya está leída, y estos botones tienen que estar siempre:
// se comparte una carta leída tanto o más que una sin leer.

/** ¿Vale la pena ofrecer la hoja del sistema? Sólo en un dispositivo táctil.
 *
 *  El criterio era `canShare`, y estaba mal: Chrome y Safari en escritorio saben
 *  compartir archivos, así que la hoja ganaba siempre y la descarga —lo que el
 *  botón promete y lo que en una computadora se espera— no ocurría nunca. */
function esTactil(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches;
}

/** La descarga de siempre, que funciona en cualquier navegador. */
function descargar(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Entrega el archivo: en el teléfono por la hoja del sistema, que es donde una
 *  descarga se pierde de vista; en la computadora, descargándolo. */
async function entregar(blob: Blob, filename: string, title: string): Promise<void> {
  const file = new File([blob], filename, { type: blob.type });
  if (esTactil() && navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title });
      return;
    } catch (error) {
      // Cancelar no es fallar: la persona cerró la hoja y no hay nada que decir.
      if (error instanceof DOMException && error.name === "AbortError") return;
      // Cualquier otra cosa cae a la descarga, que siempre funciona.
    }
  }
  descargar(blob, filename);
}

/** Del `Content-Disposition` al nombre de archivo, con los acentos puestos. */
function nombreDeArchivo(cabecera: string | null, fallback: string): string {
  if (!cabecera) return fallback;
  const utf8 = cabecera.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8) return decodeURIComponent(utf8[1]);
  const simple = cabecera.match(/filename="([^"]+)"/i);
  return simple ? simple[1] : fallback;
}

export function ChartShare({
  chartId,
  payload,
  wheel,
  readingLang,
  dict,
  locale,
}: {
  chartId: string;
  payload: PdfPayload;
  /** La carta para dibujar la imagen; null si no tiene hora de nacimiento. */
  wheel: SampleChart | null;
  /** El idioma de la lectura ya escrita, si hay alguna. */
  readingLang: Locale | null;
  dict: Dict;
  locale: Locale;
}) {
  const [ocupado, setOcupado] = useState<null | "pdf" | "lectura" | "imagen">(null);
  const [error, setError] = useState(false);

  async function pdf(conLectura: boolean) {
    setOcupado(conLectura ? "lectura" : "pdf");
    setError(false);
    try {
      const res = await fetch(`/api/charts/${chartId}/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...payload,
          reading_lang: conLectura ? readingLang : null,
        }),
      });
      if (!res.ok) throw new Error(`pdf: ${res.status}`);
      const blob = await res.blob();
      await entregar(
        blob,
        nombreDeArchivo(res.headers.get("content-disposition"), "carta.pdf"),
        payload.labels.chart_name,
      );
    } catch {
      setError(true);
    } finally {
      setOcupado(null);
    }
  }

  async function imagen() {
    setOcupado("imagen");
    setError(false);
    try {
      const blob = await renderStoryCard(wheel, {
        name: payload.labels.chart_name,
        birthLine: payload.labels.birth_line,
        madeWith: payload.labels.made_with,
      });
      await entregar(blob, `${payload.labels.chart_name}.png`, payload.labels.chart_name);
    } catch {
      setError(true);
    } finally {
      setOcupado(null);
    }
  }

  // La lectura se compra una vez y se traduce sin costo: si está escrita en otro
  // idioma, el botón lo dice en vez de esconderse. Negarle el PDF a alguien que
  // ya pagó la lectura, porque está navegando en inglés, sería absurdo.
  const enOtroIdioma = readingLang !== null && readingLang !== locale;
  const rotuloLectura = enOtroIdioma
    ? dict.share.pdfWithReadingIn.replace("{lang}", dict.share.langNames[readingLang])
    : dict.share.pdfWithReading;

  // El rótulo nombra el archivo y la línea de abajo dice qué trae: "Descargar
  // PDF" no distinguía un PDF del otro, y prometía un verbo que en el teléfono
  // no es el que ocurre. Mientras se prepara cambia la nota, no el rótulo: si se
  // reemplazaba el rótulo entero el botón saltaba de ancho.
  return (
    <div className="chartShare">
      <button
        type="button"
        className="btn btnGhost"
        onClick={() => pdf(false)}
        disabled={ocupado !== null}
        aria-busy={ocupado === "pdf"}
      >
        <span className="btnLabel">{dict.share.pdf}</span>
        <span className="btnHint">
          {ocupado === "pdf" ? dict.share.working : dict.share.pdfHint}
        </span>
      </button>

      {readingLang && (
        <button
          type="button"
          className="btn btnGhost"
          onClick={() => pdf(true)}
          disabled={ocupado !== null}
          aria-busy={ocupado === "lectura"}
        >
          <span className="btnLabel">{rotuloLectura}</span>
          <span className="btnHint">
            {ocupado === "lectura" ? dict.share.working : dict.share.pdfWithReadingHint}
          </span>
        </button>
      )}

      <button
        type="button"
        className="btn btnGhost"
        onClick={imagen}
        disabled={ocupado !== null}
        aria-busy={ocupado === "imagen"}
      >
        <span className="btnLabel">{dict.share.image}</span>
        <span className="btnHint">
          {ocupado === "imagen" ? dict.share.working : dict.share.imageHint}
        </span>
      </button>

      {error && (
        <p className="formError" role="alert">
          {dict.share.failed}
        </p>
      )}
    </div>
  );
}
