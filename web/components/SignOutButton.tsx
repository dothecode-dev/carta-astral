"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function SignOutButton({ locale, label }: { locale: string; label: string }) {
  const router = useRouter();
  const [leaving, setLeaving] = useState(false);

  async function signOut() {
    setLeaving(true);
    // Invalida el token en el backend y borra la cookie; si el backend no
    // responde, la ruta borra la cookie igual.
    await fetch("/api/session", { method: "DELETE" });
    router.replace(`/${locale}`);
    router.refresh();
  }

  return (
    <button type="button" className="btn btnGhost" onClick={signOut} disabled={leaving}>
      {label}
    </button>
  );
}
