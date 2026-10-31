import React, { useEffect, useMemo, useState } from "react";
import "./stage.css";
import DiagramLayer from "./DiagramLayer.jsx";
import MediaWall from "./MediaWall.jsx";
import Callouts from "./Callouts.jsx";
import ChartLayer from "./ChartLayer.jsx";
import EyeLayer from "./EyeLayer.jsx";
import { effectiveLayout, rectsFor, rectStyle } from "./layouts.js";
import { placeWall, wallIds } from "./wall.js";

function Subtitle({ beat, progress, finished }) {
  if (!beat) return <p className="st-say">&nbsp;</p>;
  const words = beat.say.split(" ");
  const spoken = finished ? words.length : Math.floor(progress * words.length);
  return (
    <p className="st-say" key={beat.say}>
      {words.map((w, i) => (
        <span key={i} className={i < spoken ? "is-spoken" : i === spoken ? "is-now" : ""}>{w}{" "}</span>
      ))}
    </p>
  );
}

// Legendas desligadas por padrão: a explicação é falada e o palco mostra imagens/desenhos.
function useCaptions() {
  const [on, setOn] = useState(() => {
    try { return localStorage.getItem("jarvis.cc") === "1"; } catch { return false; }
  });
  const toggle = () => setOn((v) => {
    try { localStorage.setItem("jarvis.cc", v ? "0" : "1"); } catch { /* sem storage */ }
    return !v;
  });
  return [on, toggle];
}

/**
 * A cena na mesma tela: este componente é uma camada transparente por cima do HUD. O núcleo e os
 * painéis saem de cena (App/CSS), e aqui entram o mural de mídia, os desenhos e as chamadas de texto.
 */
export default function SceneStage({ scene, media, player, loading, dim, status, notice, onClose }) {
  const [cc, toggleCc] = useCaptions();
  const entries = media.entries;
  const beat = player.beat;

  // Atalhos: ← → navegam pelos beats, espaço pausa/retoma.
  useEffect(() => {
    if (!scene) return undefined;
    const onKey = (e) => {
      if (e.target?.tagName === "INPUT" || e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === "ArrowRight") player.next();
      else if (e.key === "ArrowLeft") player.prev();
      else if (e.key === " ") { e.preventDefault(); player.toggle(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [scene, player]);

  const ids = scene ? wallIds(scene, beat, entries) : [];
  const hasMedia = ids.some((id) => entries[id]?.status === "ready");
  const ctx = { hasMedia, hasDiagram: !!scene?.diagram, hasChart: !!scene?.chart, hasGeo: !!scene?.geo };
  const layout = scene && beat ? effectiveLayout(beat, ctx) : "title";
  const rects = rectsFor(layout, ctx);

  const featured = beat?.media && ids.includes(beat.media) ? beat.media : ids[0];
  const cards = useMemo(
    () => (rects.media.o > 0 ? placeWall(ids, featured, rects.media) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ids.join("|"), featured, layout, hasMedia],
  );

  // Onde cada nó do diagrama está no palco, para as linhas das chamadas apontarem para ele.
  const nodes = useMemo(() => {
    const out = {};
    const r = rects.diagram;
    (scene?.diagram?.nodes || []).forEach((n) => {
      out[n.id] = { x: r.x + (n.x * r.w) / 100, y: r.y + (n.y * r.h) / 100 };
    });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene?.id, layout]);

  const calloutCtx = { cards, nodes };
  const wallOpacity = rects.media.o;

  return (
    <section className={`st ${dim ? "is-dim" : ""} st-layout-${layout}`} aria-live="polite">
      {scene && (
        <div className="st-meta">
          <i className={player.playing ? "is-live" : ""} />
          <span>{scene.title.toUpperCase()}</span>
          {player.total > 0 && <span className="st-meta-count">{String(Math.max(1, player.index + 1)).padStart(2, "0")}/{String(player.total).padStart(2, "0")}</span>}
        </div>
      )}

      {scene && (
        <div className="st-panes">
          {/* mural de mídia: vários cartões ao mesmo tempo */}
          <div className="st-wall" style={{ opacity: wallOpacity, pointerEvents: wallOpacity > 0.5 ? "auto" : "none" }}>
            <MediaWall cards={cards} entries={entries} scene={scene} beat={beat} visible={wallOpacity > 0.5} />
          </div>
          {/* diagrama */}
          {scene.diagram && (
            <div className="st-pane st-glass" style={rectStyle(rects.diagram)}>
              <DiagramLayer diagram={scene.diagram} revealed={player.revealed} focus={player.focus} active={rects.diagram.o > 0.5} />
            </div>
          )}
          {/* gráfico */}
          {scene.chart && (
            <div className="st-pane st-glass" style={rectStyle(rects.chart)}>
              {rects.chart.o > 0.5 && <ChartLayer chart={scene.chart} />}
            </div>
          )}
          {/* olho de deus */}
          {scene.geo && (
            <div className={`st-pane st-eye ${rects.eye.bleed ? "is-bleed" : ""}`} style={rectStyle(rects.eye)}>
              {rects.eye.o > 0.5 && <EyeLayer geo={scene.geo} revealed={player.revealed} focus={player.focus} active />}
            </div>
          )}
          {/* título */}
          <div className={`st-titlecard ${layout === "title" ? "is-on" : ""}`}>
            <span>JARVIS · {scene.kind?.toUpperCase() || "EXPLICAÇÃO"}</span>
            <h1>{scene.title}</h1>
          </div>
          {/* chamadas de texto, no ritmo da fala */}
          {beat && (
            <Callouts
              beatKey={`${scene.id}:${player.index}`}
              callouts={beat.callouts || []}
              progress={player.progress}
              finished={player.finished && !player.playing}
              ctx={calloutCtx}
            />
          )}
        </div>
      )}

      {!scene && !loading && notice && <div className="st-notice">{notice}</div>}

      {loading && (
        <div className="st-loading">
          <div className="st-orb"><i /><i /><i /></div>
          <div><strong>Dirigindo a cena</strong><p>Escolhendo imagens, desenhos e ritmo da explicação.</p></div>
        </div>
      )}

      {scene && (
        <footer className="st-bar">
          {cc && <Subtitle beat={beat} progress={player.progress} finished={player.finished && !player.playing} />}
          <div className="st-bar-top">
            <span className="st-wave" data-on={status === "SPEAKING" && player.playing}><i /><i /><i /><i /><i /></span>
            <div className="st-dots">
              {scene.beats.map((b, i) => (
                <button key={i} type="button" className={`${i === player.index ? "is-cur" : ""} ${i < player.index || player.finished ? "is-done" : ""}`}
                  onClick={() => player.jump(i)} title={`Trecho ${i + 1}`} />
              ))}
            </div>
            <div className="st-ctrl">
              <button type="button" onClick={player.prev} title="Anterior (←)">‹</button>
              <button type="button" onClick={player.toggle} title="Pausar/retomar (espaço)">{player.playing ? "❚❚" : player.finished ? "↻" : "▶"}</button>
              <button type="button" onClick={player.next} title="Próximo (→)">›</button>
              <button type="button" className={cc ? "is-on" : ""} onClick={toggleCc} title="Legendas (texto da fala)">CC</button>
              {onClose && <button type="button" onClick={onClose} title="Fechar (Esc)">×</button>}
            </div>
          </div>
        </footer>
      )}
    </section>
  );
}
