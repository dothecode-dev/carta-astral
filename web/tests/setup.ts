import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

/** jsdom no implementa `ResizeObserver` y no piensa hacerlo: es API de layout,
 *  y jsdom no maquetea. Lo usa `GoogleSignIn` para volver a dibujar el botón
 *  cuando cambia el ancho de la columna —al rotar el teléfono, sobre todo—.
 *  El doble no observa nada, que es exactamente lo que corresponde en un
 *  entorno donde nada cambia de tamaño: sirve para que el componente pueda
 *  construirlo sin explotar. */
class ObservadorDeTamañoInerte implements ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver ??= ObservadorDeTamañoInerte;
