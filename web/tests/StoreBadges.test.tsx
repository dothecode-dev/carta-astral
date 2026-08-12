import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StoreBadges } from "@/components/StoreBadges";
import { LOCALES, getDict } from "@/lib/i18n";

// Las apps se anuncian en la portada pero todavía no existen. Mientras tanto
// los badges se muestran y no llevan a ningún lado: un enlace a una ficha de
// tienda que no está publicada manda al visitante a un 404 de Apple o Google.

describe("StoreBadges", () => {
  for (const locale of LOCALES) {
    it(`${locale}: los badges no son navegables mientras no haya apps`, () => {
      render(<StoreBadges dict={getDict(locale)} />);

      expect(screen.queryAllByRole("link")).toHaveLength(0);
    });

    it(`${locale}: avisa que las apps todavía no están disponibles`, () => {
      const dict = getDict(locale);

      render(<StoreBadges dict={dict} />);

      expect(screen.getByText(dict.download.soon)).toBeInTheDocument();
    });
  }

  it("muestra las dos tiendas", () => {
    render(<StoreBadges dict={getDict("es")} />);

    expect(screen.getByText("App Store")).toBeInTheDocument();
    expect(screen.getByText("Google Play")).toBeInTheDocument();
  });
});
