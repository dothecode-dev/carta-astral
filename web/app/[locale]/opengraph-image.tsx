import { ImageResponse } from "next/og";

import { DEFAULT_LOCALE, getDict, isLocale } from "@/lib/i18n";

// La imagen que se ve al compartir un enlace. Hasta ahora no había ninguna y
// todo enlace a ASTRA salía como un rectángulo vacío en WhatsApp, X o Slack.
//
// Se genera en el build, una por idioma, con los mismos tokens de color que el
// sitio (`app/globals.css`). Sin fuente propia a propósito: las del proyecto
// son `.woff2` y satori —el motor de `ImageResponse`— sólo lee ttf, otf y woff.
// Convertir Fraunces para esto sumaría un binario más al repo por una ganancia
// que nadie va a notar en una miniatura.

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export async function generateImageMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const dict = getDict(isLocale(locale) ? locale : DEFAULT_LOCALE);
  return [{ id: "cover", size, contentType, alt: dict.meta.title }];
}

export default async function Image({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const dict = getDict(isLocale(locale) ? locale : DEFAULT_LOCALE);

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          background: "#150715",
          padding: "0 96px",
          position: "relative",
        }}
      >
        {/* El mismo disco dorado del isotipo, recortado por el borde. */}
        <div
          style={{
            position: "absolute",
            top: -260,
            right: -180,
            width: 620,
            height: 620,
            borderRadius: 620,
            border: "2px solid rgba(213, 192, 70, 0.45)",
            display: "flex",
          }}
        />
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 24,
            color: "#d5c046",
            fontSize: 34,
            letterSpacing: 14,
          }}
        >
          ASTRA
        </div>
        <div
          style={{
            display: "flex",
            color: "#f9f7f7",
            fontSize: 72,
            lineHeight: 1.15,
            marginTop: 28,
            maxWidth: 900,
          }}
        >
          {dict.meta.title}
        </div>
        <div
          style={{
            display: "flex",
            color: "#a79baf",
            fontSize: 32,
            marginTop: 28,
            maxWidth: 820,
          }}
        >
          {dict.meta.description}
        </div>
      </div>
    ),
    size,
  );
}
