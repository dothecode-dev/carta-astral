// El sistema solar del splash de la app, portado tal cual: mismos radios, mismos
// colores y mismos periodos orbitales (carta-astral-app/src/components/SolarSystem.tsx).
// Acá gira con CSS en vez de Reanimated, y se queda quieto si el sistema pide
// menos movimiento.

const VB = 200;
const C = VB / 2;
const ORBITS = { outer: 80, middle: 60, dotted: 42.5 };
const SUN_R = 20;

type Planet = {
  r: number;
  orbit: number;
  angle: number;
  periodMs: number;
  color: string;
  glow: string;
};

const PLANETS: Planet[] = [
  { r: 12.5, orbit: ORBITS.outer, angle: 162, periodMs: 20000, color: "#131BA7", glow: "#4B14CD" },
  { r: 10, orbit: ORBITS.middle, angle: -47, periodMs: 12000, color: "#A71391", glow: "#CD1561" },
];

export function SolarSystem({ size = 200, speed = 1 }: { size?: number; speed?: number }) {
  return (
    <div className="solar" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${VB} ${VB}`} width={size} height={size} aria-hidden="true">
        <defs>
          <radialGradient id="sunGlow" cx="50%" cy="50%" r="50%">
            <stop offset="30%" stopColor="#FAFF64" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#FAFF64" stopOpacity={0} />
          </radialGradient>
          {PLANETS.map((p) => (
            <radialGradient key={p.color} id={`halo${p.color.slice(1)}`} cx="50%" cy="50%" r="50%">
              <stop offset="35%" stopColor={p.glow} stopOpacity={0.5} />
              <stop offset="100%" stopColor={p.glow} stopOpacity={0} />
            </radialGradient>
          ))}
        </defs>

        <circle cx={C} cy={C} r={ORBITS.outer} stroke="rgba(178,173,138,0.6)" strokeWidth={2} fill="none" />
        <circle cx={C} cy={C} r={ORBITS.middle} stroke="rgba(178,173,138,0.6)" strokeWidth={2} fill="none" />
        <circle
          cx={C}
          cy={C}
          r={ORBITS.dotted}
          stroke="#DCCB54"
          strokeWidth={1}
          strokeDasharray="1.5 4"
          fill="none"
        />

        <circle cx={C} cy={C} r={SUN_R * 2.4} fill="url(#sunGlow)" />
        <circle cx={C} cy={C} r={SUN_R} fill="#D5C046" />

        {PLANETS.map((p) => (
          <g
            key={p.color}
            className="solarOrbit"
            style={{
              animationDuration: `${p.periodMs / speed}ms`,
              transform: `rotate(${p.angle}deg)`,
            }}
          >
            <circle cx={C + p.orbit} cy={C} r={p.r * 2.6} fill={`url(#halo${p.color.slice(1)})`} />
            <circle cx={C + p.orbit} cy={C} r={p.r} fill={p.color} />
          </g>
        ))}
      </svg>
    </div>
  );
}
