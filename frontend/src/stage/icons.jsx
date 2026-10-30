import React from "react";

// Ícones de traço (viewBox 24x24), desenhados à mão para o estilo holográfico.
const P = {
  atom: <><circle cx="12" cy="12" r="1.6" /><ellipse cx="12" cy="12" rx="10" ry="4" /><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(60 12 12)" /><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(120 12 12)" /></>,
  bolt: <path d="M13 2 4 14h7l-1 8 9-12h-7z" />,
  flame: <path d="M12 2c1 4 5 6 5 11a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-4-1-6 1-10z" />,
  drop: <path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z" />,
  gear: <><circle cx="12" cy="12" r="3.2" /><path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9 7 7m10 10 2.1 2.100M19.1 4.9 17 7M7 17l-2.1 2.1" /></>,
  fan: <><circle cx="12" cy="12" r="1.8" /><path d="M12 10.200C12 6 10 3 8 3.5 6 4 7 8 10.5 10.700M13.8 12c4.2 0 7.2 2 6.7 4-.5 2-4.5 1-7.2-2.500M12 13.800c0 4.2 2 7.2 4 6.7 2-.5 1-4.5-2.5-7.200M10.2 12C6 12 3 10 3.5 8" /></>,
  cloud: <path d="M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9.5 4.2 4.2 0 0 1 17.5 18z" />,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.900l1.4 1.400m11.4 11.4 1.4 1.400m0-14.2-1.4 1.400M6.3 17.700l-1.4 1.4" /></>,
  wind: <path d="M3 8h11a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h8" />,
  cell: <><ellipse cx="12" cy="12" rx="9" ry="7" /><circle cx="10" cy="11" r="2.5" /><circle cx="16" cy="14" r="1" /></>,
  dna: <path d="M7 3c0 6 10 6 10 12s-10 6-10 6M17 3c0 6-10 6-10 12M8 7h8M8.5 17h7M9 12h6" />,
  brain: <path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 5 1V4a3 3 0 0 0-2 0zm6 0a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-5 1V4a3 3 0 0 1 2 0z" />,
  heart: <path d="M12 21s-8-5-8-11a4.5 4.5 0 0 1 8-2.500A4.5 4.5 0 0 1 20 10c0 6-8 11-8 11z" />,
  globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></>,
  building: <path d="M4 21V5l8-2v18M12 9l8 2v10M2 21h20M7 8h2m-2 4h2m-2 4h2m6-4h2m-2 4h2" />,
  factory: <path d="M2 21V10l6 4v-4l6 4V6h4v15zM6 18h2m3 0h2m3 0h2" />,
  chip: <><rect x="6" y="6" width="12" height="12" rx="1.5" /><rect x="9.5" y="9.5" width="5" height="5" /><path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4" /></>,
  database: <><ellipse cx="12" cy="5.5" rx="8" ry="3" /><path d="M4 5.500v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>,
  network: <><circle cx="12" cy="5" r="2" /><circle cx="5" cy="18" r="2" /><circle cx="19" cy="18" r="2" /><path d="M11 7 6 16m7-9 5 9M7 18h10" /></>,
  lock: <><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>,
  rocket: <path d="M12 2c4 2 6 6 6 10l-3 3H9l-3-3c0-4 2-8 6-10zM9 15l-3 3 .5-4M15 15l3 3-.5-4M12 9.500a1.5 1.5 0 1 0 0 .01M10 18l2 4 2-4" />,
  planet: <><circle cx="12" cy="12" r="5" /><ellipse cx="12" cy="12" rx="10" ry="3.5" transform="rotate(-20 12 12)" /></>,
  book: <path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zm0 14a2 2 0 0 1 2-2h13" />,
  scale: <path d="M12 3v18M7 21h10M5 7h14M5 7l-3 7a3.5 3.5 0 0 0 6 0zM19 7l-3 7a3.5 3.5 0 0 0 6 0z" />,
  coin: <><circle cx="12" cy="12" r="9" /><path d="M14.5 9a3 3 0 0 0-5 1.500c0 3 5 1.5 5 4.500a3 3 0 0 1-5 1.500M12 6.500v1.500m0 8v1.5" /></>,
  chart: <path d="M3 3v18h18M7 15l4-4 3 3 5-6" />,
  person: <><circle cx="12" cy="7.5" r="4" /><path d="M4 21c0-4.5 3.5-7 8-7s8 2.5 8 7" /></>,
  leaf: <path d="M20 4C9 4 4 9 4 15a5 5 0 0 0 5 5c6 0 11-5 11-16zM4 20c3-6 7-9 12-11" />,
  thermo: <path d="M10 13.500V5a2 2 0 0 1 4 0v8.500a4 4 0 1 1-4 0zM12 9v7" />,
  magnet: <path d="M6 3v9a6 6 0 0 0 12 0V3h-4v9a2 2 0 0 1-4 0V3zM6 7h4m4 0h4" />,
  wave: <path d="M2 12c2-6 4-6 6 0s4 6 6 0 4-6 6 0" />,
  flask: <path d="M9 3h6M10 3v6l-6 10a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3l-6-10V3M7.5 15h9" />,
  pipe: <path d="M3 9h10a3 3 0 0 1 3 3v3h5M3 9v6h4M16 15v3" />,
  shield: <path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>,
  pin: <><path d="M12 21s7-6.5 7-12a7 7 0 0 0-14 0c0 5.5 7 12 7 12z" /><circle cx="12" cy="9" r="2.5" /></>,
};

// Ícone padrão por tipo de nó, quando o LLM não escolhe um.
const KIND_DEFAULT = {
  source: "bolt", process: "gear", store: "database", output: "chart",
  actor: "person", concept: "atom", hazard: "flame",
};

export function Icon({ name, kind, size = 24, ...rest }) {
  const key = P[name] ? name : KIND_DEFAULT[kind] || "atom";
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}>
      {P[key]}
    </svg>
  );
}
