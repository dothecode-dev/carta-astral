"use client";

import { useEffect, useSyncExternalStore } from "react";

type Theme = "dark" | "light";

// La fuente de verdad del tema es el atributo del <html>, no un estado de React:
// lo escribe el script anti-parpadeo antes de que React exista. Por eso se lee
// con useSyncExternalStore en vez de copiarlo a un useState desde un efecto.
function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  const media = window.matchMedia("(prefers-color-scheme: light)");
  media.addEventListener("change", onChange);
  return () => {
    observer.disconnect();
    media.removeEventListener("change", onChange);
  };
}

function getSnapshot(): Theme {
  const explicit = document.documentElement.dataset.theme;
  if (explicit === "dark" || explicit === "light") return explicit;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

/** En el servidor no hay tema todavía: ningún botón sale marcado. */
function getServerSnapshot(): Theme | null {
  return null;
}

/** Los dos estados llevan nombre porque ninguno es "el normal": la página nace
 *  en el que tenga puesto el sistema y de ahí lo mueve quien lee. */
export function ThemeSwitch({ night, day, label }: { night: string; day: string; label: string }) {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  // Repone el atributo si el DOM lo perdió.
  //
  // El script anti-parpadeo lo escribe una sola vez, al cargar el documento.
  // Cambiar de idioma cambia el segmento `[locale]`, que es el del layout raíz:
  // React remonta el <html> con el markup del servidor —que no trae
  // `data-theme`— y el tema elegido se evapora. Quien había puesto día
  // aterrizaba en noche, con este mismo switch marcando día (03-09-2026).
  //
  // Es la red de seguridad, no el arreglo principal: el selector de idioma
  // navega con recarga completa justamente para que el script corra antes del
  // primer paint. Esto cubre cualquier otro remonte del layout raíz, a costa
  // de un frame en el tema del sistema.
  useEffect(() => {
    if (document.documentElement.dataset.theme) return;
    try {
      const guardado = localStorage.getItem("astra-theme");
      if (guardado === "dark" || guardado === "light") {
        document.documentElement.dataset.theme = guardado;
      }
    } catch {
      // Storage bloqueado: manda la preferencia del sistema, como al principio.
    }
  }, []);

  function choose(next: Theme) {
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("astra-theme", next);
    } catch {
      // Modo incógnito o storage bloqueado: el tema vale para esta visita y ya.
    }
  }

  return (
    <div className="switch" role="group" aria-label={label}>
      <button type="button" aria-pressed={theme === "dark"} onClick={() => choose("dark")}>
        <span aria-hidden="true">☾</span> {night}
      </button>
      <button type="button" aria-pressed={theme === "light"} onClick={() => choose("light")}>
        <span aria-hidden="true">☀</span> {day}
      </button>
    </div>
  );
}
