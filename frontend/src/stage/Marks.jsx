import React, { useEffect, useRef, useState } from "react";
import { iconPaths } from "./icons.js";
import { markGeometry } from "./handDrawn.js";
import { visibleCallouts as visibleByAt } from "./calloutsLogic.js";
import { MARKS } from "./tuning.js";
import { useLeaving } from "./useLeaving.js";

function useSize(ref) {
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const update = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return size;
}

function Mark({ item }) {
  const { mark, geo } = item;
  const color = MARKS.colors[mark.type] || "#f5f1e4";
  const step = MARKS.stagger;
  let n = 0;
  const delay = () => `${n++ * step}ms`;
  const paths = geo.paths.map((p, k) => (
    <path
      key={k}
      className="mk-path"
      d={p.d}
      pathLength="1"
      style={{ "--delay": p.role === "head" ? `${Math.round(MARKS.drawMs * 0.8) + (n - 1) * step}ms` : delay(), "--dur": `${p.role === "head" ? 320 : MARKS.drawMs}ms` }}
    />
  ));
  const iconDs = geo.icon ? iconPaths(geo.icon.name) : null;
  const labelDelay = `${Math.max(1, n + (iconDs ? iconDs.length : 0)) * step + 240}ms`;
  return (
    <g className="mk" style={{ "--c": color }}>
      {paths}
      {iconDs && (
        <g className="mk-icon" transform={`translate(${geo.icon.x} ${geo.icon.y}) scale(${geo.icon.size / 24})`}>
          {iconDs.map((d, k) => (
            <path key={k} className="mk-path mk-icon-path" d={d} pathLength="1" style={{ "--delay": `${k * 200}ms`, "--dur": "700ms" }} />
          ))}
        </g>
      )}
      {geo.label && (
        <text
          className={`mk-label ${geo.label.rot === -90 ? "is-vertical" : ""}`}
          x={geo.label.x}
          y={geo.label.y}
          textAnchor={geo.label.anchor}
          transform={geo.label.rot ? `rotate(${geo.label.rot} ${geo.label.x} ${geo.label.y})` : undefined}
          style={{ "--delay": labelDelay }}
        >
          {geo.label.text}
        </text>
      )}
    </g>
  );
}

/**
 * Traços feitos à mão (círculo, sublinhado, seta, colchete, ícone) que se desenham sobre a cena
 * quando a fala chega no `at` de cada um. Uma marca cujo alvo não está visível naquele momento
 * (mídia fora do mural, nó ainda não revelado) simplesmente não aparece.
 */
export default function Marks({ beatKey, marks, progress, finished, ctx }) {
  const ref = useRef(null);
  const size = useSize(ref);
  const shown = size.w
    ? visibleByAt(marks, progress, finished)
        .map((mark) => ({ mark, geo: markGeometry(mark, { ...ctx, size }, beatKey) }))
        .filter((it) => it.geo)
    : [];
  const leaving = useLeaving(beatKey, shown, MARKS.leaveMs);
  return (
    <div ref={ref} className="mk-layer" aria-hidden="true">
      {size.w > 0 && (
        <svg className="mk-svg" width={size.w} height={size.h} viewBox={`0 0 ${size.w} ${size.h}`}>
          {leaving && (
            <g key={`out-${leaving.key}`} className="mk-group is-leaving">
              {leaving.items.map((it, i) => <Mark key={i} item={it} />)}
            </g>
          )}
          <g key={`in-${beatKey}`} className="mk-group">
            {shown.map((it, i) => <Mark key={`${it.mark.type}-${it.mark.at}-${i}`} item={it} />)}
          </g>
        </svg>
      )}
    </div>
  );
}
