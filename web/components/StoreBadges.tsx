import type { Dict } from "@/lib/i18n";

// Los badges se muestran porque las apps están anunciadas, pero no llevan a
// ningún lado: todavía no hay ficha publicada en ninguna de las dos tiendas y
// un enlace mandaría al visitante a un 404 de Apple o de Google. Por eso son
// `<span>` y no `<a>` — el cartel de próximamente explica por qué no responden.
//
// Badges propios: los oficiales de Apple y Google tienen guías de marca
// obligatorias y hay que reemplazarlos antes de publicar.

export function StoreBadges({ dict }: { dict: Dict }) {
  return (
    <>
      <div className="stores">
        <span className="store" aria-disabled="true">
          <svg width="17" height="21" viewBox="0 0 17 21" aria-hidden="true">
            <path
              fill="currentColor"
              d="M14.09 11.02c-.02-2.2 1.8-3.36 1.88-3.42-1.02-1.5-2.62-1.7-3.18-1.72-1.35-.14-2.64.8-3.33.8-.69 0-1.75-.78-2.87-.76-1.48.02-2.84.86-3.6 2.18-1.53 2.66-.39 6.6 1.1 8.76.73 1.06 1.6 2.25 2.74 2.2 1.1-.04 1.51-.71 2.84-.71 1.33 0 1.7.71 2.86.69 1.18-.02 1.93-1.08 2.65-2.14.83-1.22 1.18-2.4 1.2-2.47-.03-.01-2.29-.88-2.31-3.49z"
            />
            <path
              fill="currentColor"
              d="M11.9 4.48c.61-.74 1.02-1.77.91-2.79-.88.04-1.94.58-2.57 1.32-.56.65-1.05 1.7-.92 2.7.98.08 1.98-.5 2.58-1.23z"
            />
          </svg>
          <span className="storeText">
            <span className="storeSmall">{dict.download.appleSmall}</span>
            <span className="storeName">App Store</span>
          </span>
        </span>

        <span className="store" aria-disabled="true">
          <svg width="19" height="21" viewBox="0 0 19 21" aria-hidden="true">
            <path
              fill="currentColor"
              d="M1.1 1.2C.9 1.5.8 1.9.8 2.5v16c0 .6.1 1 .3 1.3l8.4-8.8L1.1 1.2z"
            />
            <path
              fill="currentColor"
              d="M10.6 10.1l2.7-2.8L2.9.6C2.4.3 1.9.2 1.5.4l9.1 9.7z"
            />
            <path
              fill="currentColor"
              d="M10.6 11.9L1.5 20.6c.4.2.9.1 1.4-.2l10.4-6.7-2.7-1.8z"
            />
            <path
              fill="currentColor"
              d="M17.4 9.2l-2.9-1.9-3 3.2 3 3.1 2.9-1.9c.9-.6.9-1.9 0-2.5z"
            />
          </svg>
          <span className="storeText">
            <span className="storeSmall">{dict.download.playSmall}</span>
            <span className="storeName">Google Play</span>
          </span>
        </span>
      </div>

      <p className="storesSoon">{dict.download.soon}</p>
    </>
  );
}
