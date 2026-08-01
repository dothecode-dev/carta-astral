"use client";

import { useEffect, useState } from "react";

import { BODIES, formatDegree, positions, signOf, type Positions } from "@/lib/ephemeris";
import { INTL_LOCALE, PLANET_NAMES, type Locale } from "@/lib/i18n";

type Row = { glyph: string; name: string; degree: string; sign: string };

/** Se renderiza vacío en el servidor a propósito: depende de la hora del
 *  visitante, y pintarlo en el HTML sería un mismatch de hidratación seguro. */
export function EphemerisRail({
  locale,
  eyebrow,
  note,
  initial,
}: {
  locale: Locale;
  eyebrow: string;
  note: string;
  initial: Positions | null;
}) {
  const [clock, setClock] = useState("");
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    const format = new Intl.DateTimeFormat(INTL_LOCALE[locale], {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

    function refresh(withPositions: boolean) {
      const now = new Date();
      setClock(format.format(now).replace(",", " ·"));
      if (!withPositions) return;
      // Las del servidor salen de Swiss Ephemeris; el cálculo local es el
      // respaldo si el backend no contestó.
      const pos = initial ?? positions(now);
      setRows(
        BODIES.slice(0, 7).map((body, i) => {
          const lon = pos[body.key];
          return {
            glyph: body.glyph,
            name: PLANET_NAMES[locale][i],
            degree: formatDegree(lon),
            sign: signOf(lon),
          };
        }),
      );
    }

    refresh(true);
    let ticks = 0;
    const timer = window.setInterval(() => {
      ticks += 1;
      refresh(ticks % 30 === 0);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [locale, initial]);

  return (
    <aside className="rail">
      <div className="railInner">
        <div className="ephem">
          <p className="eyebrow">{eyebrow}</p>
          <p className="ephemClock">{clock}</p>
          <ul className="ephemList">
            {rows.map((row) => (
              <li className="ephemRow" key={row.glyph}>
                <span className="ephemGlyph">{row.glyph}</span>
                <span className="ephemName">{row.name}</span>
                <span className="ephemDeg">
                  {row.degree} {row.sign}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="railNote">{note}</p>
      </div>
    </aside>
  );
}
