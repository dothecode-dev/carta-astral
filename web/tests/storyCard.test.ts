import { afterEach, describe, expect, it, vi } from "vitest";

import { SITE_HOST, STORY_H, STORY_W, renderStoryCard } from "@/lib/storyCard";

// jsdom no trae canvas 2d: se arma uno falso que sólo anota qué texto se dibuja.
function canvasFalso(textos: string[]) {
  const ctx = new Proxy(
    { fillText: (t: string) => textos.push(t) } as Record<string, unknown>,
    {
      get: (obj, key: string) => obj[key] ?? (() => undefined),
      set: (obj, key: string, value) => ((obj[key] = value), true),
    },
  );
  return {
    width: 0,
    height: 0,
    getContext: () => ctx,
    toBlob: (cb: (b: Blob) => void) => cb(new Blob(["png"], { type: "image/png" })),
  };
}

describe("renderStoryCard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("firma la imagen con el dominio, para que quien la ve sepa adónde ir", async () => {
    const textos: string[] = [];
    vi.spyOn(document, "createElement").mockReturnValue(
      canvasFalso(textos) as unknown as HTMLCanvasElement,
    );
    await renderStoryCard(null, {
      name: "Camila",
      birthLine: "12 de marzo de 1994",
      madeWith: "Hecho con ASTRA",
    });
    expect(textos).toContain(SITE_HOST);
    expect(SITE_HOST).toBe("astraguia.com");
    expect(STORY_W).toBe(1080);
    expect(STORY_H).toBe(1920);
  });
});
