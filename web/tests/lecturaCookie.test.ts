import { describe, expect, it } from "vitest";
import { LECTURA_COOKIE, opcionesLectura } from "@/lib/lecturaCookie";

describe("cookie de la lectura anónima", () => {
  it("es httpOnly, lax, de 24 h y para todo el sitio", () => {
    expect(LECTURA_COOKIE).toBe("astra_lectura");
    expect(opcionesLectura()).toMatchObject({ httpOnly: true, sameSite: "lax", maxAge: 86400, path: "/" });
  });
});
