"use client";

import { useState } from "react";

import type { Dict, Locale } from "@/lib/i18n";

/** El formulario del botón de arrepentimiento: mail y número de compra. Al
 *  registrarse muestra el código, que es el comprobante «por el mismo medio»
 *  que pide la resolución (el backend además lo manda por mail). */
export function ArrepentimientoForm({ locale, dict }: { locale: Locale; dict: Dict }) {
  const t = dict.arrepentimiento;
  const [mail, setMail] = useState("");
  const [numero, setNumero] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [codigo, setCodigo] = useState<string | null>(null);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (enviando) return;
    setEnviando(true);
    setError(null);
    try {
      const res = await fetch("/api/arrepentimiento", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: mail.trim(), numero_compra: numero.trim(), locale }),
      });
      if (res.ok) {
        const { codigo: recibido } = (await res.json()) as { codigo: string };
        setCodigo(recibido);
        return;
      }
      setError(res.status === 400 ? t.mailInvalido : res.status === 429 ? t.demasiados : t.fallo);
    } catch {
      setError(t.fallo);
    }
    setEnviando(false);
  }

  if (codigo) {
    return (
      <section className="arrepentimientoListo" aria-live="polite">
        <h2>{t.listoTitulo}</h2>
        <p>{t.listoCodigo}</p>
        <p className="arrepentimientoCodigo">
          <strong>{codigo}</strong>
        </p>
        <p>{t.listoCuerpo}</p>
      </section>
    );
  }

  return (
    <form className="form" onSubmit={enviar} noValidate>
      <div className="field">
        <label className="fieldLabel" htmlFor="arrepentimiento-mail">
          {t.mailLabel}
        </label>
        <input
          id="arrepentimiento-mail"
          className="input"
          type="email"
          autoComplete="email"
          required
          value={mail}
          onChange={(e) => setMail(e.target.value)}
        />
        <p className="fieldNote">{t.mailNota}</p>
      </div>
      <div className="field">
        <label className="fieldLabel" htmlFor="arrepentimiento-numero">
          {t.numeroLabel}
        </label>
        <input
          id="arrepentimiento-numero"
          className="input"
          type="text"
          maxLength={40}
          value={numero}
          onChange={(e) => setNumero(e.target.value)}
        />
        <p className="fieldNote">{t.numeroNota}</p>
      </div>
      {error && (
        <p className="formError" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="btn btnPrimary" disabled={enviando}>
        {t.enviar}
      </button>
    </form>
  );
}
