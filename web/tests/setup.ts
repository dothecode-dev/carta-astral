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

/** Node 25 trae su propio `localStorage` global, que sin `--localstorage-file`
 *  no guarda nada y tapa el de jsdom (`localStorage.clear is not a function`).
 *  Si el que hay no hace ida y vuelta, se instala uno en memoria. Sólo para
 *  los tests: el código de producción no se toca.
 *
 *  Los métodos cuelgan de `Storage.prototype` (y las instancias heredan de
 *  él) para que `vi.spyOn(Storage.prototype, "setItem")` siga interceptando,
 *  como en un navegador. */
function andaElAlmacen(nombre: "localStorage" | "sessionStorage"): boolean {
  try {
    const a = globalThis[nombre];
    a.setItem("__prueba", "1");
    const ok = a.getItem("__prueba") === "1";
    a.removeItem("__prueba");
    return ok;
  } catch {
    return false;
  }
}

const rotos = (["localStorage", "sessionStorage"] as const).filter((n) => !andaElAlmacen(n));
if (rotos.length > 0) {
  const datos = new WeakMap<object, Map<string, string>>();
  const de = (o: object) => {
    let m = datos.get(o);
    if (!m) datos.set(o, (m = new Map()));
    return m;
  };
  const proto = Storage.prototype;
  Object.defineProperties(proto, {
    length: { configurable: true, get(this: object) { return de(this).size; } },
    clear: { configurable: true, writable: true, value(this: object) { de(this).clear(); } },
    getItem: {
      configurable: true,
      writable: true,
      value(this: object, k: string) { return de(this).get(String(k)) ?? null; },
    },
    key: {
      configurable: true,
      writable: true,
      value(this: object, i: number) { return [...de(this).keys()][i] ?? null; },
    },
    removeItem: { configurable: true, writable: true, value(this: object, k: string) { de(this).delete(String(k)); } },
    setItem: {
      configurable: true,
      writable: true,
      value(this: object, k: string, v: string) { de(this).set(String(k), String(v)); },
    },
  });
  for (const nombre of rotos) {
    const almacen = Object.create(proto);
    Object.defineProperty(globalThis, nombre, { value: almacen, configurable: true, writable: true });
    Object.defineProperty(window, nombre, { value: almacen, configurable: true, writable: true });
  }
}
