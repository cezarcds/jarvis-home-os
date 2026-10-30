import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { arcPath, fitView, flyFrame, project, shiftCenter, unproject, TILE } from "./geo.js";
import { useSize } from "./useSize.js";

const TILE_URL = import.meta.env.VITE_TILE_URL || "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const LAYER_COLORS = ["#67e8f9", "#fbbf24", "#a78bfa", "#34d399", "#fb7185", "#f9a8d4"];
const FLY_MS = 1700;

function tileUrl(z, x, y) {
  const retina = typeof window !== "undefined" && window.devicePixelRatio > 1.5 ? "@2x" : "";
  return TILE_URL.replace("{s}", "abcd"[(x + y) % 4]).replace("{z}", z).replace("{x}", x).replace("{y}", y).replace("{r}", retina);
}

export default function EyeLayer({ geo, revealed, focus, active }) {
  const [ref, { w, h }] = useSize();
  const [view, setView] = useState({ lat: 15, lon: 0, zoom: 1.6 });
  const [hidden, setHidden] = useState(() => new Set()); // camadas desligadas
  const viewRef = useRef(view);
  viewRef.current = view;
  const flyRef = useRef(null);
  const dragRef = useRef(null);

  const points = useMemo(() => geo.points.filter((p) => revealed.has(p.id)), [geo, revealed]);
  const layers = useMemo(() => [...new Set(geo.points.map((p) => p.layer))], [geo]);
  const layerColor = (l) => LAYER_COLORS[layers.indexOf(l) % LAYER_COLORS.length];
  const byId = useMemo(() => Object.fromEntries(geo.points.map((p) => [p.id, p])), [geo]);

  const flyTo = useCallback((to, ms = FLY_MS) => {
    cancelAnimationFrame(flyRef.current?.raf);
    const from = viewRef.current;
    const t0 = performance.now();
    const state = { raf: 0 };
    const step = (now) => {
      const t = Math.min(1, (now - t0) / ms);
      setView(flyFrame(from, to, t));
      if (t < 1) state.raf = requestAnimationFrame(step);
    };
    state.raf = requestAnimationFrame(step);
    flyRef.current = state;
  }, []);

  // A câmera acompanha a narração: foco → voa até o ponto; sem foco → enquadra tudo que já entrou em cena.
  const focusKey = focus.join(",");
  const revealedKey = points.map((p) => p.id).join(",");
  useEffect(() => {
    if (!active || !w) return;
    const target = focus.map((id) => byId[id]).find(Boolean);
    // A faixa inferior (~170px) pertence à legenda: enquadra só a área livre acima dela.
    if (target) flyTo(shiftCenter({ lat: target.lat, lon: target.lon, zoom: Math.max(4.5, Math.min(7, viewRef.current.zoom + 1.5)) }, 70));
    else flyTo(shiftCenter(fitView(points, w, h - 170), 85));
  }, [active, focusKey, revealedKey, w, h]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => cancelAnimationFrame(flyRef.current?.raf), []);

  // Navegação manual: arrastar e roda do mouse (interrompe o voo automático).
  const onPointerDown = (e) => {
    if (e.target.closest("button")) return;
    cancelAnimationFrame(flyRef.current?.raf);
    dragRef.current = { x: e.clientX, y: e.clientY };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e) => {
    const d = dragRef.current;
    if (!d) return;
    const v = viewRef.current;
    const c = project(v.lat, v.lon, v.zoom);
    const n = unproject(c.x - (e.clientX - d.x), c.y - (e.clientY - d.y), v.zoom);
    dragRef.current = { x: e.clientX, y: e.clientY };
    setView({ ...v, lat: Math.max(-80, Math.min(80, n.lat)), lon: n.lon });
  };
  const onPointerUp = () => { dragRef.current = null; };
  const onWheel = (e) => {
    cancelAnimationFrame(flyRef.current?.raf);
    setView((v) => ({ ...v, zoom: Math.max(1, Math.min(14, v.zoom - e.deltaY * 0.002)) }));
  };

  // --- tiles visíveis ---
  const tiles = useMemo(() => {
    if (!w || !h) return [];
    const zi = Math.max(1, Math.min(16, Math.round(view.zoom)));
    const s = Math.pow(2, view.zoom - zi);
    const c = project(view.lat, view.lon, zi);
    const size = TILE * s;
    const x0 = Math.floor((c.x - w / (2 * s)) / TILE), x1 = Math.floor((c.x + w / (2 * s)) / TILE);
    const y0 = Math.max(0, Math.floor((c.y - h / (2 * s)) / TILE)), y1 = Math.min(Math.pow(2, zi) - 1, Math.floor((c.y + h / (2 * s)) / TILE));
    const out = [];
    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        const wrapped = ((tx % Math.pow(2, zi)) + Math.pow(2, zi)) % Math.pow(2, zi);
        out.push({ key: `${zi}/${tx}/${ty}`, url: tileUrl(zi, wrapped, ty), left: w / 2 + (tx * TILE - c.x) * s, top: h / 2 + (ty * TILE - c.y) * s, size });
      }
    }
    return out;
  }, [view, w, h]);

  const toScreen = useCallback((p) => {
    const c = project(view.lat, view.lon, view.zoom), q = project(p.lat, p.lon, view.zoom);
    return { x: w / 2 + (q.x - c.x), y: h / 2 + (q.y - c.y) };
  }, [view, w, h]);

  const visible = points.filter((p) => !hidden.has(p.layer));
  const visibleIds = new Set(visible.map((p) => p.id));
  const links = geo.links.filter((l) => visibleIds.has(l.from) && visibleIds.has(l.to));
  const focusSet = new Set(focus);

  const toggleLayer = (l) => setHidden((s) => { const n = new Set(s); n.has(l) ? n.delete(l) : n.add(l); return n; });

  return (
    <div className="eye" ref={ref} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} onWheel={onWheel}>
      <div className="eye-tiles">
        {tiles.map((t) => (
          <img key={t.key} src={t.url} alt="" draggable="false" className="eye-tile"
            style={{ left: t.left, top: t.top, width: t.size + 0.5, height: t.size + 0.5 }}
            onLoad={(e) => e.currentTarget.classList.add("is-loaded")} />
        ))}
      </div>
      <div className="eye-tint" />

      {w > 0 && (
        <svg className="eye-links" width={w} height={h} aria-hidden="true">
          {links.map((l) => {
            const a = toScreen(byId[l.from]), b = toScreen(byId[l.to]);
            const g = arcPath(a, b);
            const lit = focusSet.has(l.from) || focusSet.has(l.to);
            return (
              <g key={`${l.from}>${l.to}`}>
                <path d={g.d} className={`eye-arc ${lit ? "is-lit" : ""}`} style={{ stroke: layerColor(byId[l.from].layer) }} />
                {l.label && <text x={g.mid.x} y={g.mid.y - 6} textAnchor="middle" className="eye-arc-label">{l.label}</text>}
              </g>
            );
          })}
        </svg>
      )}

      {w > 0 && visible.map((p) => {
        const s = toScreen(p);
        if (s.x < -80 || s.x > w + 80 || s.y < -80 || s.y > h + 80) return null;
        const isFocus = focusSet.has(p.id);
        return (
          <div key={p.id} className={`eye-pt ${isFocus ? "is-focus" : ""}`} style={{ left: s.x, top: s.y, "--c": layerColor(p.layer) }}>
            <i className="eye-pulse" /><i className="eye-dot" />
            <span className="eye-pt-label">{p.label}</span>
            {isFocus && p.detail && <span className="eye-pt-detail">{p.detail}</span>}
          </div>
        );
      })}

      <div className="eye-hud">
        <div className="eye-hud-title"><i /> OLHO DE DEUS</div>
        <div className="eye-hud-coords">{view.lat.toFixed(2)}°, {view.lon.toFixed(2)}° · Z{view.zoom.toFixed(1)}</div>
        {layers.length > 1 && (
          <div className="eye-layers">
            {layers.map((l) => (
              <button key={l} type="button" className={hidden.has(l) ? "is-off" : ""} style={{ "--c": layerColor(l) }} onClick={() => toggleLayer(l)}>
                <i />{l}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="eye-attrib">© OpenStreetMap · © CARTO</div>
      <div className="eye-reticle" aria-hidden="true" />
    </div>
  );
}
