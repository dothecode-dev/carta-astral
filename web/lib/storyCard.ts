import type { SampleChart } from "@/content/sample-chart";
import { drawWheel } from "@/lib/drawWheel";

// La imagen vertical para historias: 1080×1920, la rueda grande y los datos.
//
// Se dibuja en el navegador y no en el servidor: el canvas de la página ya sabe
// pintar esta misma rueda, y mandarla al backend sería una ida y vuelta de red
// para algo que acá ya está resuelto.
//
// La paleta es la de marca, fija. Una carta compartida en Instagram con el tema
// claro de quien la exportó no se vería como ASTRA, se vería como una captura.

export const STORY_W = 1080;
export const STORY_H = 1920;

const PALETTE = {
  void: "#150715",
  starlight: "#F9F7F7",
  stardust: "#A79BAF",
  sol: "#D5C046",
  hairline: "rgba(178, 173, 138, 0.28)",
  hairStrong: "rgba(178, 173, 138, 0.6)",
  dotted: "#DCCB54",
};

const SANS = "system-ui, -apple-system, Helvetica, sans-serif";

export type StoryCopy = {
  /** El nombre de la carta, o el rótulo de carta sin nombre. */
  name: string;
  /** Fecha, hora y lugar, en una línea. */
  birthLine: string;
  /** El pie: "Hecho con ASTRA". */
  madeWith: string;
};

/**
 * Dibuja la card y la devuelve como PNG.
 *
 * Sin rueda —una carta sin hora de nacimiento— la imagen sale igual, con el
 * nombre y los datos: es lo que hay para mostrar.
 */
export async function renderStoryCard(
  chart: SampleChart | null,
  copy: StoryCopy,
): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = STORY_W;
  canvas.height = STORY_H;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("sin contexto 2d");

  ctx.fillStyle = PALETTE.void;
  ctx.fillRect(0, 0, STORY_W, STORY_H);

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  // La marca arriba, con el mismo espaciado de letra que la portada del PDF.
  ctx.fillStyle = PALETTE.starlight;
  ctx.font = `300 96px ${SANS}`;
  ctx.letterSpacing = "32px";
  ctx.fillText("ASTRA", STORY_W / 2 + 16, 260);
  ctx.letterSpacing = "0px";

  ctx.fillStyle = PALETTE.starlight;
  ctx.font = `300 72px ${SANS}`;
  ctx.fillText(copy.name, STORY_W / 2, 420);

  ctx.fillStyle = PALETTE.stardust;
  ctx.font = `32px ${SANS}`;
  ctx.fillText(copy.birthLine, STORY_W / 2, 490);

  if (chart) {
    const size = 960;
    ctx.save();
    ctx.translate((STORY_W - size) / 2, 640);
    drawWheel(ctx, size, chart, {
      ink: PALETTE.starlight,
      inkSoft: PALETTE.stardust,
      accent: PALETTE.sol,
      hairline: PALETTE.hairline,
      hairStrong: PALETTE.hairStrong,
      dotted: PALETTE.dotted,
      mono: SANS,
    });
    ctx.restore();
  }

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = PALETTE.stardust;
  ctx.font = `28px ${SANS}`;
  ctx.letterSpacing = "8px";
  ctx.fillText(copy.madeWith.toUpperCase(), STORY_W / 2, STORY_H - 140);
  ctx.letterSpacing = "0px";

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("no se pudo exportar la imagen"))),
      "image/png",
    );
  });
}
