import React, { useEffect, useId, useState } from "react";

/**
 * Quadro negro que se desenha sozinho (referência: vídeos estilo Nerdologia).
 * Ícones são traçados à mão, setas surgem entre eles e os rótulos são escritos em giz.
 *
 * Props
 *  - title     título do quadro (sublinhado a giz)
 *  - items     [{ icon, label, detail }]  de 2 a 6 itens, na ordem da explicação
 *  - progress  0..1, quanto da fala já passou (use o progresso do beat). Se omitido,
 *              o quadro se desenha sozinho em `durationMs`.
 *  - durationMs  só vale sem `progress`
 *
 * Ícones: atom bolt flame drop gear globe book people house coin trend-up warning lightbulb check
 *         search newspaper shield heart clock leaf sun cloud megaphone vote. Outro nome = círculo.
 */
const ICONS = {
  atom: ["M12 12m-1.6 0a1.6 1.6 0 1 0 3.2 0a1.6 1.6 0 1 0 -3.2 0", "M12 12c5-1 9 0 9 0s-4 1-9 0-9-6-9-6", "M3 6c2-3 7 1 9 6s2 9 0 9-7-4-9-6", "M21 6c-2-3-7 1-9 6"],
  bolt: ["M13 2L4 14h7l-1 8 9-12h-7z"],
  flame: ["M12 3c1 4 5 5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3 0-6 1-9z"],
  drop: ["M12 3C9 8 6 11 6 15a6 6 0 0 0 12 0c0-4-3-7-6-12z"],
  gear: ["M12 8.5a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7z", "M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"],
  globe: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M3 12h18", "M12 3c3 3 3 15 0 18", "M12 3c-3 3-3 15 0 18"],
  book: ["M4 5c3-1 6-1 8 1v14c-2-2-5-2-8-1z", "M20 5c-3-1-6-1-8 1v14c2-2 5-2 8-1z"],
  people: ["M9 8a3 3 0 1 0 0-6a3 3 0 0 0 0 6z", "M3 21c0-4 3-7 6-7s6 3 6 7", "M17 9a2.5 2.5 0 1 0 0-5", "M17 14c3 0 5 3 5 7"],
  house: ["M3 11l9-8l9 8", "M5 10v11h14V10", "M10 21v-6h4v6"],
  coin: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M14.5 9c-.5-1-1.5-1.5-2.7-1.5c-1.6 0-2.8.8-2.8 2s1.2 1.6 3 2s3 .8 3 2s-1.2 2-3 2c-1.3 0-2.4-.6-3-1.6", "M12 6v1.5M12 16.5V18"],
  "trend-up": ["M3 17l6-6l4 4l8-9", "M15 6h6v6"],
  warning: ["M12 3L2 20h20z", "M12 10v5", "M12 17.5v.5"],
  lightbulb: ["M9 18h6M10 21h4", "M12 3a6 6 0 0 0-3.5 10.9c.8.7 1.5 1.6 1.5 2.6v.5h4v-.5c0-1 .7-1.9 1.5-2.6A6 6 0 0 0 12 3z"],
  check: ["M4 12l5 5L20 6"],
  search: ["M11 4a7 7 0 1 0 0 14a7 7 0 0 0 0-14z", "M16.5 16.5L21 21"],
  newspaper: ["M4 4h14v16H4z", "M18 8h2v10a2 2 0 0 1-2 2", "M7 8h8M7 12h8M7 16h5"],
  shield: ["M12 3l8 3v6c0 5-3.5 8-8 9c-4.5-1-8-4-8-9V6z"],
  heart: ["M12 20s-8-5-8-11a4.5 4.5 0 0 1 8-2.5A4.5 4.5 0 0 1 20 9c0 6-8 11-8 11z"],
  clock: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M12 7v5l3 2"],
  leaf: ["M5 19C5 9 11 4 20 4c0 9-5 15-15 15z", "M5 19c3-5 6-8 10-10"],
  sun: ["M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8z", "M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"],
  cloud: ["M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9.5a4 4 0 0 1-.5 8.5z"],
  megaphone: ["M3 10v4h4l8 5V5L7 10z", "M18 9c1.5 1 1.5 5 0 6"],
  vote: ["M5 12h14v8H5z", "M9 12V6l6 3", "M8 16h8"],
  _fallback: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z"],
};

const clamp01 = (v) => Math.max(0, Math.min(1, v));
const seg = (p, a, b) => clamp01((p - a) / (b - a));
const CHALK = "#f1efe6";
const CHALK_DIM = "rgba(241,239,230,0.7)";
const HAND = '"Segoe Print","Bradley Hand","Comic Sans MS","Chalkboard SE",cursive';

function layout(n) {
  const cols = n <= 3 ? n : Math.ceil(n / 2);
  const rows = n <= 3 ? 1 : 2;
  const cw = 900 / cols;
  return Array.from({ length: n }, (_, i) => {
    const r = Math.floor(i / cols);
    const c = i % cols;
    return { x: 50 + cw * (c + 0.5), y: rows === 1 ? 300 : r === 0 ? 235 : 440, last: c === cols - 1 || i === n - 1, cw };
  });
}

function Stroke({ d, p, width = 3.2, ...rest }) {
  return (
    <path
      d={d}
      pathLength="1"
      fill="none"
      stroke={CHALK}
      strokeWidth={width}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray="1"
      strokeDashoffset={1 - p}
      opacity={p > 0 ? 1 : 0}
      {...rest}
    />
  );
}

export default function ChalkBoard({ title, items = [], progress, durationMs, className = "" }) {
  const uid = useId().replace(/:/g, "");
  const list = items.slice(0, 6);
  const n = list.length;
  const [auto, setAuto] = useState(0);

  useEffect(() => {
    if (progress != null) return undefined;
    const total = durationMs || 1800 * Math.max(1, n) + 1200;
    const t0 = performance.now();
    let raf;
    const tick = (now) => {
      const v = clamp01((now - t0) / total);
      setAuto(v);
      if (v < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [progress, durationMs, n]);

  const p = progress != null ? clamp01(progress) : auto;
  const pos = layout(n);
  const titleP = seg(p, 0, 0.12);
  const slot = n ? 0.88 / n : 1;

  return (
    <div className={`relative h-full w-full overflow-hidden ${className}`} style={{ background: "radial-gradient(120% 90% at 50% 40%, #2c3a35 0%, #1b2420 55%, #121916 100%)", borderRadius: 14, boxShadow: "inset 0 0 0 6px #5b4630, inset 0 0 40px rgba(0,0,0,0.6)" }}>
      <svg viewBox="0 0 1000 560" preserveAspectRatio="xMidYMid meet" className="h-full w-full" role="img" aria-label={title || "Quadro explicativo"}>
        <defs>
          {/* giz: borda levemente irregular + poeira */}
          <filter id={`chalk-${uid}`} x="-5%" y="-5%" width="110%" height="110%">
            <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="4" result="n" />
            <feDisplacementMap in="SourceGraphic" in2="n" scale="2.6" />
          </filter>
          <filter id={`dust-${uid}`}>
            <feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves="3" seed="9" />
            <feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.05 0" />
          </filter>
        </defs>
        <rect width="1000" height="560" filter={`url(#dust-${uid})`} />

        <g filter={`url(#chalk-${uid})`}>
          {title && (
            <>
              <text x="500" y="70" textAnchor="middle" fontFamily={HAND} fontSize="44" fill={CHALK} opacity={titleP > 0 ? 1 : 0}>
                {title.slice(0, Math.ceil(title.length * titleP))}
              </text>
              <Stroke d="M250 92 C380 84 620 100 750 90" p={seg(p, 0.07, 0.14)} width={3} />
            </>
          )}

          {list.map((it, i) => {
            const a = 0.12 + i * slot;
            const iconP = seg(p, a, a + slot * 0.55);
            const labelP = seg(p, a + slot * 0.45, a + slot * 0.8);
            const arrowP = seg(p, a + slot * 0.75, a + slot);
            const { x, y, last, cw } = pos[i];
            const paths = ICONS[it.icon] || ICONS._fallback;
            const per = 1 / paths.length;
            const label = String(it.label || "");
            const detail = String(it.detail || "");
            return (
              <g key={`${it.label}-${i}`}>
                {/* ícone 24x24 ampliado para ~120px */}
                <g transform={`translate(${x - 60} ${y - 120}) scale(5)`}>
                  {paths.map((d, k) => (
                    <Stroke key={k} d={d} p={seg(iconP, k * per, (k + 1) * per)} width={0.62} />
                  ))}
                </g>
                <text x={x} y={y + 50} textAnchor="middle" fontFamily={HAND} fontSize="30" fill={CHALK} opacity={labelP > 0 ? 1 : 0}>
                  {label.slice(0, Math.ceil(label.length * labelP))}
                </text>
                {detail && (
                  <text x={x} y={y + 84} textAnchor="middle" fontFamily={HAND} fontSize="19" fill={CHALK_DIM} opacity={labelP > 0.6 ? 1 : 0}>
                    {detail.slice(0, Math.ceil(detail.length * seg(labelP, 0.6, 1)))}
                  </text>
                )}
                {!last && n > 1 && (
                  <Stroke
                    d={`M${x + cw / 2 - 95} ${y - 60} q${35} ${-12} ${70} 0 m-14 -11 l14 11 l-16 10`}
                    p={arrowP}
                    width={3}
                  />
                )}
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
