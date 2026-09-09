// La forma de un código de cupón, separada de `cupon.ts` a propósito: esta
// función es pura (nada de red, nada de `next/headers`) y la usa
// `components/CuponInput.tsx`, un Client Component. `cupon.ts` importa
// `callApi` (`lib/session.ts`), que a su vez importa `next/headers` — prohibido
// en un bundle de cliente. Antes de este archivo, `normalizarCupon` vivía en
// `cupon.ts` y el bundler arrastraba todo ese árbol al cliente por un solo
// import; `next build` lo frenaba con "You're importing a module that depends
// on next/headers ... but you are using it in the Pages Router" apuntando a
// `CuponInput.tsx → cupon.ts → session.ts`.

/** El alfabeto de Stripe: mayúsculas, dígitos y guión, de 3 a 40. */
const FORMA = /^[A-Z0-9-]{3,40}$/;

/** El código como lo guarda el backend, o null si no tiene forma de código.
 *  Viene de la URL o de un campo: cualquiera escribe lo que quiera ahí. */
export function normalizarCupon(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const codigo = raw.trim().toUpperCase();
  return FORMA.test(codigo) ? codigo : null;
}
