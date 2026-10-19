import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Footer } from "@/components/Footer";
import { getDict } from "@/lib/i18n";

describe("pie: Data Fiscal de ARCA", () => {
  it.each(["es", "en", "pt"] as const)("en %s lleva el logo por https y el enlace de ARCA", (locale) => {
    const html = renderToStaticMarkup(<Footer locale={locale} dict={getDict(locale)} />);

    expect(html).toContain('href="http://qr.afip.gob.ar/?qr=ubYBPcTLEsiYwH81mDC7Uw,,"');
    expect(html).toContain('src="https://www.afip.gob.ar/images/f960/DATAWEB.jpg"');
    expect(html).not.toContain('src="http://');
  });
});
