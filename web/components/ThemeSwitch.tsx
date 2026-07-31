"use client";

import { useSyncExternalStore } from "react";

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
