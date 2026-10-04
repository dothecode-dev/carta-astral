// Espejo de INSTALL_FREE_CREDITS del backend. NO se pide por red: /entrar es la
// única página que todo visitante sin sesión toca sí o sí, y hacerla depender
// del backend la deja rota cada vez que el backend esté lento, caído o con el
// cartel de mantenimiento puesto.
//
// Que los dos números coincidan lo garantiza backend/tests/test_regalo_coherente.py,
// que falla el gate si alguien cambia uno y no el otro.
export const LECTURAS_DE_REGALO = 1;

/**
 * El texto que corresponde a la cantidad de regalo: `una` si es una sola,
 * `varias` (con `{n}`) si son más. Los diccionarios lo usan para que «tus
 * primeras tres lecturas» no quede escrito a mano el día que el regalo cambie.
 */
export function segunRegalo(una: string, varias: string): string {
  return LECTURAS_DE_REGALO === 1 ? una : varias.replaceAll("{n}", String(LECTURAS_DE_REGALO));
}
