/** El glifo del Sol (☉) con un planeta montado en la órbita, que recorta el
 *  trazo al pasar. Es la geometría del splash de la app reducida a lo que
 *  sobrevive en 16 píxeles; la app ya usa ☉ para el saldo de créditos. */
export function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="12" fill="none" stroke="var(--accent)" strokeWidth="1.4" />
      <circle cx="16" cy="16" r="4.4" fill="var(--accent)" />
      <circle cx="24.5" cy="7.5" r="4.4" fill="var(--ground)" />
      <circle cx="24.5" cy="7.5" r="2.6" fill="var(--accent)" />
    </svg>
  );
}
