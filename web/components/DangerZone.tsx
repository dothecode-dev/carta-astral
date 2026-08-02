"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Dict } from "@/lib/i18n";

// Las dos acciones destructivas, con confirmación en dos pasos: los mismos
// textos y el mismo comportamiento que la pantalla de la app, para que la
// promesa sea idéntica en los dos lados.

type Target = "charts" | "account" | null;

export function DangerZone({ locale, dict }: { locale: string; dict: Dict }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState<Target>(null);
  const [busy, setBusy] = useState(false);
  const t = dict.auth;

  async function wipe(target: Exclude<Target, null>) {
    setBusy(true);
    const res = await fetch(target === "charts" ? "/api/charts" : "/api/account", {
      method: "DELETE",
    });
    setBusy(false);

    if (!res.ok) {
      setConfirming(null);
      return;
    }

    if (target === "account") {
      // La cuenta ya no existe: la cookie se borró del lado del servidor.
      router.replace(`/${locale}`);
    } else {
      setConfirming(null);
      router.refresh();
    }
  }

  function block(target: Exclude<Target, null>, title: string, body: string, confirm: string) {
    const open = confirming === target;
    return (
      <div className="dangerBlock">
        <h3 className="dangerHeading">{title}</h3>
        <p className="dangerBody">{body}</p>

        {open ? (
          <div className="dangerActions">
            <p className="dangerHint">{t.confirmHint}</p>
            <button
              type="button"
              className="btn btnDanger"
              onClick={() => wipe(target)}
              disabled={busy}
            >
              {busy ? t.working : confirm}
            </button>
            <button
              type="button"
              className="btn btnGhost"
              onClick={() => setConfirming(null)}
              disabled={busy}
            >
              {t.cancel}
            </button>
          </div>
        ) : (
          <button type="button" className="btn btnGhost" onClick={() => setConfirming(target)}>
            {title}
          </button>
        )}
      </div>
    );
  }

  return (
    <section className="danger">
      <p className="eyebrow dangerEyebrow">{t.dangerTitle}</p>
      {block("charts", t.deleteChartsTitle, t.deleteChartsBody, t.deleteChartsConfirm)}
      {block("account", t.deleteAccountTitle, t.deleteAccountBody, t.deleteAccountConfirm)}
    </section>
  );
}
