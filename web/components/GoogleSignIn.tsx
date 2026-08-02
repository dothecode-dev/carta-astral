"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

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
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  const [status, setStatus] = useState<"loading" | "ready" | "blocked" | "failed">(
    clientId ? "loading" : "blocked",
  );

  useEffect(() => {
    if (!clientId) return;

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
  }, [clientId, locale, router]);

  return (
    <div className="signin">
      <div ref={holder} />
      {status === "loading" && <p className="signinNote">{labels.loading}</p>}
      {status === "blocked" && <p className="signinNote signinError">{labels.blocked}</p>}
      {status === "failed" && <p className="signinNote signinError">{labels.failed}</p>}
    </div>
  );
}
