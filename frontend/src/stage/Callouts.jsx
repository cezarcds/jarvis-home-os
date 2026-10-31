import React, { useEffect, useRef, useState } from "react";
import { LANE, anchorFor, placeCallouts, visibleCallouts } from "./calloutsLogic.js";
import { CALLOUT } from "./tuning.js";

const LEAVE_MS = CALLOUT.leaveMs;

/** Guarda por um instante as chamadas do beat anterior, para elas saírem em vez de sumirem de repente. */
function useLeaving(key, items) {
  const [leaving, setLeaving] = useState(null);
  const prev = useRef({ key, items });
  useEffect(() => {
    if (prev.current.key !== key) {
      const old = prev.current;
      prev.current = { key, items };
      if (old.items.length) {
        setLeaving(old);
        const t = setTimeout(() => setLeaving(null), LEAVE_MS);
        return () => clearTimeout(t);
      }
      return undefined;
    }
    prev.current = { key, items };
    return undefined;
  }, [key, items]);
  return leaving;
}

function Group({ items, ctx, leaving }) {
  return (
    <div className={`co-group ${leaving ? "is-leaving" : ""}`}>
      <svg className="co-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {items.map((c, i) => {
          const a = anchorFor(c, ctx);
          const x1 = LANE[c.side].edge;
          return <line key={i} className={`co-line co-line-${c.side}`} x1={x1} y1={c.y} x2={a.x} y2={a.y} vectorEffect="non-scaling-stroke" pathLength="1" />;
        })}
      </svg>
      {items.map((c, i) => {
        const a = anchorFor(c, ctx);
        return <i key={`d${i}`} className="co-end" style={{ left: `${a.x}%`, top: `${a.y}%` }} />;
      })}
      {items.map((c, i) => (
        <div
          key={`c${i}`}
          className={`co co-${c.side} co-${c.kind || "fact"}`}
          style={{ top: `${c.y}%`, left: `${LANE[c.side].x}%`, width: `${LANE[c.side].w}%` }}
        >
          <span className="co-text">{c.text}</span>
        </div>
      ))}
    </div>
  );
}

/**
 * Chamadas de texto que entram pela esquerda e pela direita no ritmo da fala.
 * `progress` (0..1) vem do player: cada chamada aparece quando a fala chega no `at` dela.
 */
export default function Callouts({ beatKey, callouts, progress, finished, ctx }) {
  const placed = placeCallouts(callouts);
  const shown = visibleCallouts(placed, progress, finished);
  const leaving = useLeaving(beatKey, shown);
  return (
    <div className="co-layer" aria-hidden="true">
      {leaving && <Group key={`out-${leaving.key}`} items={leaving.items} ctx={ctx} leaving />}
      <Group key={`in-${beatKey}`} items={shown} ctx={ctx} />
    </div>
  );
}
