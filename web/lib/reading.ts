/**
 * El markdown que escribe el modelo, convertido a bloques para pintar.
 *
 * La lectura llegaba a la pantalla sin parsear: se leía "## Una presencia" y
 * "**Casa Doce**" con la almohadilla y los asteriscos a la vista, en el texto
 * por el que la persona pagó.
 *
 * Es un parser mínimo a propósito: cubre lo que el modelo produce —títulos,
 * negritas y listas— y nada más. Sin dependencias, como el resto de la web.
 */

export type Parte = { texto: string; fuerte?: boolean };

export type Bloque =
  | { tipo: "titulo"; nivel: 1 | 2 | 3; texto: string }
  | { tipo: "parrafo"; partes: Parte[] }
  | { tipo: "lista"; items: Parte[][] };

/** Parte el texto en tramos normales y en negrita. */
function partir(texto: string): Parte[] {
  const partes: Parte[] = [];
  let resto = texto;

  for (;;) {
    const m = resto.match(/\*\*([\s\S]+?)\*\*/);
    if (!m || m.index === undefined) break;
    if (m.index > 0) partes.push({ texto: resto.slice(0, m.index) });
    partes.push({ texto: m[1], fuerte: true });
    resto = resto.slice(m.index + m[0].length);
  }
  // Lo que sobra —incluida una negrita sin cerrar— va tal cual: es preferible
  // un asterisco suelto a perder texto de la lectura.
  if (resto) partes.push({ texto: resto });
  return partes.length > 0 ? partes : [{ texto: "" }];
}

/** Une los renglones de un párrafo: el corte de línea lo hace el navegador. */
function unir(bloque: string): string {
  return bloque.split("\n").map((l) => l.trim()).join(" ").trim();
}

export function parseReading(texto: string): Bloque[] {
  return texto
    .split(/\n{2,}/)
    .map((b) => b.trim())
    .filter(Boolean)
    .map((bloque): Bloque | null => {
      const titulo = bloque.match(/^(#{1,3})\s+([\s\S]*)$/);
      if (titulo) {
        return {
          tipo: "titulo",
          nivel: titulo[1].length as 1 | 2 | 3,
          texto: unir(titulo[2]),
        };
      }

      const renglones = bloque.split("\n").map((l) => l.trim()).filter(Boolean);
      if (renglones.length > 0 && renglones.every((l) => /^[-*]\s+/.test(l))) {
        return {
          tipo: "lista",
          items: renglones.map((l) => partir(l.replace(/^[-*]\s+/, ""))),
        };
      }

      return { tipo: "parrafo", partes: partir(unir(bloque)) };
    })
    .filter((b): b is Bloque => b !== null);
}
