// Biblioteca de ícones de traço fino (grade 24x24). Cada ícone é uma lista de caminhos, que o quadro
// "desenha" um a um. Os nomes precisam ser iguais a MARK_ICONS em backend/scene_schema.py (há um teste).

function ellipse(rx, ry, deg, n = 28) {
  const a = (deg * Math.PI) / 180;
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const t = (i / n) * Math.PI * 2;
    const x = rx * Math.cos(t);
    const y = ry * Math.sin(t);
    pts.push(`${(12 + x * Math.cos(a) - y * Math.sin(a)).toFixed(2)} ${(12 + x * Math.sin(a) + y * Math.cos(a)).toFixed(2)}`);
  }
  return `M${pts.join("L")}Z`;
}

export const ICONS = {
  bolt: ["M13 2L4 14h7l-1 8 9-12h-7z"],
  atom: [ellipse(10, 3.8, 0), ellipse(10, 3.8, 60), ellipse(10, 3.8, 120), "M12 11a1 1 0 100 2 1 1 0 000-2z"],
  flame: ["M12 3c1 4 5 5 5 10a5 5 0 01-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 1-9z"],
  drop: ["M12 3C9 8 6 11 6 15a6 6 0 0012 0c0-4-3-7-6-12z"],
  gear: [
    "M10 2.5h4l.6 2.4 1.7.9 2.3-.9 2 3.4-1.8 1.7v1.9l1.8 1.7-2 3.4-2.3-.9-1.7.9-.6 2.4h-4l-.6-2.4-1.7-.9-2.3.9-2-3.4 1.8-1.7v-1.9L3.4 8.9l2-3.4 2.3.9 1.7-.9z",
    "M12 9a3 3 0 100 6 3 3 0 000-6z",
  ],
  shield: ["M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z", "M8.5 12l2.5 2.5 4.5-5"],
  globe: ["M12 3a9 9 0 100 18 9 9 0 000-18z", "M3 12h18", "M12 3c3 3 3 15 0 18", "M12 3c-3 3-3 15 0 18"],
  clock: ["M12 3a9 9 0 100 18 9 9 0 000-18z", "M12 7v5l3 2"],
  coin: [
    "M12 3a9 9 0 100 18 9 9 0 000-18z",
    "M14.5 9.5c-.5-1-1.5-1.5-2.5-1.5-1.5 0-2.5.8-2.5 2s1 1.7 2.5 2 2.5.8 2.5 2-1 2-2.5 2c-1 0-2-.5-2.5-1.5",
    "M12 6.5V8M12 16v1.5",
  ],
  "trend-up": ["M3 17l6-6 4 4 8-8", "M15 7h6v6"],
  "trend-down": ["M3 7l6 6 4-4 8 8", "M15 17h6v-6"],
  people: ["M9 11a3 3 0 100-6 3 3 0 000 6z", "M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6", "M16.5 11a2.5 2.5 0 100-5", "M17.5 14.2c2.2.5 3.5 2.4 3.5 5.8"],
  house: ["M3 11l9-8 9 8", "M5 10v10h14V10", "M10 20v-6h4v6"],
  heart: ["M12 20s-8-5-8-11a4.5 4.5 0 018-2.8A4.5 4.5 0 0120 9c0 6-8 11-8 11z"],
  book: ["M4 4h7a2 2 0 012 2v14a2 2 0 00-2-2H4z", "M20 4h-7a2 2 0 00-2 2v14a2 2 0 012-2h7z"],
  lock: ["M6 11h12v9H6z", "M8 11V8a4 4 0 018 0v3", "M12 15v2"],
  warning: ["M12 3l10 18H2z", "M12 10v5", "M12 18v.5"],
  check: ["M4 12l5 5L20 6"],
  cross: ["M5 5l14 14", "M19 5L5 19"],
  star: ["M12 3l2.8 5.8 6.2.9-4.5 4.4 1 6.2-5.5-3-5.5 3 1-6.2L3 9.7l6.2-.9z"],
  search: ["M10 3a7 7 0 100 14 7 7 0 000-14z", "M15 15l6 6"],
  pin: ["M12 21s7-6.5 7-12a7 7 0 10-14 0c0 5.5 7 12 7 12z", "M12 7a2.5 2.5 0 100 5 2.5 2.5 0 000-5z"],
  flag: ["M5 21V4", "M5 4h11l-2 4 2 4H5"],
  scale: ["M12 4v16", "M7 20h10", "M5 7h14", "M5 7l-3 7a3 3 0 006 0z", "M19 7l-3 7a3 3 0 006 0z"],
  megaphone: ["M3 10v4h3l8 4V6L6 10z", "M18 9a4 4 0 010 6"],
  newspaper: ["M4 5h13v14H6a2 2 0 01-2-2z", "M17 9h3v8a2 2 0 01-2 2", "M7 9h7", "M7 13h7", "M7 16h4"],
  lightbulb: ["M9 18h6", "M10 21h4", "M12 3a6 6 0 00-3.5 10.9c.8.7 1.5 1.6 1.5 2.6v.5h4v-.5c0-1 .7-1.9 1.5-2.6A6 6 0 0012 3z"],
  rocket: ["M12 3c3 2 5 6 5 10l-2 3H9l-2-3c0-4 2-8 5-10z", "M9 16l-3 4 3-1", "M15 16l3 4-3-1", "M12 9.5a1.5 1.5 0 100 3 1.5 1.5 0 000-3z"],
  leaf: ["M5 19C5 10 10 5 20 4c0 10-5 15-14 15", "M5 19c3-5 6-8 11-11"],
  sun: ["M12 8a4 4 0 100 8 4 4 0 000-8z", "M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"],
  cloud: ["M7 18a4 4 0 010-8 5 5 0 019.6-1A4.5 4.5 0 0117 18z"],
  phone: ["M7 3h10v18H7z", "M11 18h2"],
  mail: ["M3 6h18v12H3z", "M3 7l9 7 9-7"],
  factory: ["M3 20V10l6 4v-4l6 4V6h3v14z", "M7 20v-3", "M12 20v-3"],
  vote: ["M4 13h16v7H4z", "M8 13l1-6 6 0 1 6", "M9 16.5h6", "M10.5 4.5l1.5 2 1.5-2"],
};

export const iconPaths = (name) => ICONS[name] || null;
