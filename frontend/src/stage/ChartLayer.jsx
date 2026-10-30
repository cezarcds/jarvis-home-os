import React, { useMemo } from "react";

const W = 800, H = 400, PAD = { l: 56, r: 24, t: 60, b: 52 };

const fmt = (v) => (Math.abs(v) >= 1000 ? v.toLocaleString("pt-BR", { maximumFractionDigits: 0 }) : String(+v.toFixed(2)).replace(".", ","));

export default function ChartLayer({ chart }) {
  const { series, type, unit, title } = chart;
  const geom = useMemo(() => {
    const vals = series.map((s) => s.value);
    const lo = Math.min(0, ...vals), hi = Math.max(...vals, lo + 1);
    const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
    const y = (v) => PAD.t + ih - ((v - lo) / (hi - lo)) * ih;
    const slot = iw / series.length;
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => lo + (hi - lo) * f);
    return { lo, hi, iw, ih, y, slot, ticks };
  }, [series]);

  const color = ["#67e8f9", "#fbbf24", "#a78bfa", "#34d399", "#fb7185"];
  const base = geom.y(0);
  const pts = series.map((s, i) => ({ x: PAD.l + geom.slot * (i + 0.5), y: geom.y(s.value) }));
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p.x},${p.y}`).join(" ");

  return (
    <div className="cl">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label={title || "Gráfico"}>
        {title && <text x={PAD.l} y={24} className="cl-title">{title}{unit ? ` (${unit})` : ""}</text>}
        {geom.ticks.map((t, i) => (
          <g key={i}>
            <line x1={PAD.l} x2={W - PAD.r} y1={geom.y(t)} y2={geom.y(t)} className="cl-grid" />
            <text x={PAD.l - 8} y={geom.y(t) + 4} textAnchor="end" className="cl-tick">{fmt(t)}</text>
          </g>
        ))}
        <line x1={PAD.l} x2={W - PAD.r} y1={base} y2={base} className="cl-axis" />
        {type === "line" ? (
          <>
            <path d={line} className="cl-line" pathLength="1" />
            {pts.map((p, i) => (
              <g key={i} className="cl-dot" style={{ animationDelay: `${300 + i * 140}ms` }}>
                <circle cx={p.x} cy={p.y} r="5" />
                <text x={p.x} y={p.y - 12} textAnchor="middle" className="cl-value">{fmt(series[i].value)}</text>
              </g>
            ))}
          </>
        ) : (
          series.map((s, i) => {
            const bw = Math.min(70, geom.slot * 0.56), x = pts[i].x - bw / 2;
            const top = Math.min(geom.y(s.value), base), hgt = Math.abs(base - geom.y(s.value));
            return (
              <g key={i} className="cl-bar" style={{ animationDelay: `${i * 130}ms`, transformOrigin: `${pts[i].x}px ${base}px` }}>
                <rect x={x} y={top} width={bw} height={hgt} rx="2" fill={color[i % color.length]} fillOpacity=".78" stroke={color[i % color.length]} />
                <text x={pts[i].x} y={top - 8} textAnchor="middle" className="cl-value">{fmt(s.value)}</text>
              </g>
            );
          })
        )}
        {series.map((s, i) => (
          <text key={i} x={pts[i].x} y={H - PAD.b + 22} textAnchor="middle" className="cl-label">{s.label}</text>
        ))}
      </svg>
    </div>
  );
}
