"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { identificar, track } from "@/lib/telemetry";

// Google Identity Services devuelve un id_token firmado directamente en la
// página. Ese token se manda a /api/session, que lo canjea contra el backend y
// guarda la sesión en una cookie httpOnly: el token de sesión nunca pasa por acá.

type Credential = { credential?: string };

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize(config: {
            client_id: string;
            callback: (response: Credential) => void;
            auto_select?: boolean;
          }): void;
          renderButton(parent: HTMLElement, options: Record<string, unknown>): void;
        };
      };
    };
  }
}

const SCRIPT_SRC = "https://accounts.google.com/gsi/client";

// El backend acepta varias credenciales en una sola variable separadas por coma
// —Google exige un client id por plataforma, ver `audiences_for` en api/sso.py—,
// pero acá va una sola. Pegar la lista del backend en esta variable deja un botón
// que renderiza bien y recién al clickearlo devuelve "invalid_client", con el
// motivo enterrado en un log de GSI. Pasó en producción el 13-08-2026.
function usableClientId(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  const value = raw.trim();
  if (/[,\s]/.test(value) || !value.endsWith(".apps.googleusercontent.com")) return undefined;
  return value;
}

export function GoogleSignIn({
  locale,
  labels,
}: {
  locale: string;
  labels: { loading: string; blocked: string; failed: string };
}) {
  const holder = useRef<HTMLDivElement>(null);
  const router = useRouter();
  // Se resuelve en el build: si falta la credencial, se sabe antes de renderizar
  // y no hay por qué averiguarlo dentro de un efecto.
  const raw = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  const clientId = usableClientId(raw);
  const [status, setStatus] = useState<"loading" | "ready" | "blocked" | "failed">(
    clientId ? "loading" : "blocked",
  );

  useEffect(() => {
    if (!clientId) {
      // Sin esto el problema es indistinguible de un bloqueador de rastreadores.
      console.error(
        raw
          ? `NEXT_PUBLIC_GOOGLE_CLIENT_ID mal formado (${raw.length} caracteres): se espera un único client id terminado en .apps.googleusercontent.com, sin comas ni espacios.`
          : "NEXT_PUBLIC_GOOGLE_CLIENT_ID no está definido: el acceso con Google queda deshabilitado.",
      );
      return;
    }

    async function onCredential(response: Credential) {
      if (!response.credential) {
        setStatus("failed");
        return;
      }
      const res = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: "google", id_token: response.credential }),
      });
      if (!res.ok) {
        setStatus("failed");
        return;
      }
      // El id interno, nunca el email: es lo que ata los eventos de esta
      // persona sin decirle a PostHog quién es.
      //
      // Envuelto entero: la sesión ya es válida en este punto y medirla no
      // puede hacerla fallar. Un cuerpo ilegible cuesta la identificación,
      // jamás el login.
      try {
        const sesion: { account_id?: number } = await res.json();
        if (typeof sesion.account_id === "number") identificar(sesion.account_id);
      } catch {
        // Ver arriba: sin id no hay a quién atribuir, y se sigue de largo.
      }
      track("login", { provider: "google" });
      router.replace(`/${locale}/cuenta`);
      router.refresh();
    }

    function render() {
      const google = window.google;
      if (!google || !holder.current || !clientId) return;
      google.accounts.id.initialize({ client_id: clientId, callback: onCredential });
      google.accounts.id.renderButton(holder.current, {
        theme: "outline",
        size: "large",
        shape: "pill",
        text: "continue_with",
        locale,
        width: 280,
      });
      setStatus("ready");
    }

    if (window.google) {
      render();
      return;
    }

    const script = document.createElement("script");
    script.src = SCRIPT_SRC;
    script.async = true;
    script.onload = render;
    // Un bloqueador de rastreadores puede impedir que cargue: mejor decirlo que
    // dejar un botón que no aparece nunca.
    script.onerror = () => setStatus("blocked");
    document.head.appendChild(script);
  }, [clientId, raw, locale, router]);

  return (
    <div className="signin">
      {/* Clase propia, y no `.signin`: el recorte de `.signinButton` (ver
          globals.css) no puede alcanzar a las notas de error de abajo. */}
      <div className="signinButton" ref={holder} />
      {status === "loading" && <p className="signinNote">{labels.loading}</p>}
      {status === "blocked" && <p className="signinNote signinError">{labels.blocked}</p>}
      {status === "failed" && <p className="signinNote signinError">{labels.failed}</p>}
    </div>
  );
}
