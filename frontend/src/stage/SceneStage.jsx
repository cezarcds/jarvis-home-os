import React, { useEffect, useState } from "react";
import "./stage.css";
import DiagramLayer from "./DiagramLayer.jsx";
import MediaLayer from "./MediaLayer.jsx";
import ChartLayer from "./ChartLayer.jsx";
import EyeLayer from "./EyeLayer.jsx";
import { effectiveLayout, rectsFor, rectStyle } from "./layouts.js";

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

export default function SceneStage({ scene, media, player, loading, dim, question, status, notice, onClose }) {
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

  const mediaId = beat?.media || scene?.media?.[0]?.id;
  let entry = mediaId ? entries[mediaId] : null;
  // Se a mídia escolhida para este beat não existe (busca falhou), usa outra que já esteja pronta
  // em vez de deixar o palco vazio. Enquanto ainda carrega, não troca (evita piscar).
  if (entry?.status === "none") {
    const alt = (scene?.media || []).map((m) => entries[m.id]).find((e) => e?.status === "ready");
    if (alt) entry = alt;
  }
  const hasMedia = entry?.status === "ready";
  const ctx = { hasMedia, hasDiagram: !!scene?.diagram, hasChart: !!scene?.chart, hasGeo: !!scene?.geo };
  const layout = scene && beat ? effectiveLayout(beat, ctx) : "title";
  const rects = rectsFor(layout, ctx);
  const mediaRect = rects.media;
  const mediaMode = mediaRect.bg ? "bg" : mediaRect.pip ? "pip" : "pane";

  return (
    <section className={`st ${dim ? "is-dim" : ""} st-layout-${layout}`} aria-live="polite">
      <div className="st-bg" aria-hidden="true"><div className="st-grid" /><div className="st-horizon" /></div>

      {scene && (
        <div className="st-meta">
          <i className={player.playing ? "is-live" : ""} />
          <span>{scene.title.toUpperCase()}</span>
          {player.total > 0 && <span className="st-meta-count">{String(Math.max(1, player.index + 1)).padStart(2, "0")}/{String(player.total).padStart(2, "0")}</span>}
        </div>
      )}

      {scene && (
        <div className="st-panes">
          {/* mídia */}
          {scene.media.length > 0 && (
            <div className={`st-pane st-media ${mediaRect.bg ? "is-bg" : ""} ${mediaRect.pip ? "is-pip" : ""}`} style={rectStyle(mediaRect)}>
              <MediaLayer entry={entry} caption={beat?.caption} mode={mediaMode} visible={mediaRect.o > 0.5} />
            </div>
          )}
          {/* diagrama */}
          {scene.diagram && (
            <div className="st-pane" style={rectStyle(rects.diagram)}>
              <DiagramLayer diagram={scene.diagram} revealed={player.revealed} focus={player.focus} active={rects.diagram.o > 0.5} />
            </div>
          )}
          {/* gráfico */}
          {scene.chart && (
            <div className="st-pane" style={rectStyle(rects.chart)}>
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
          {cc && <Subtitle beat={beat} progress={player.progress} finished={player.finished && !player.playing} />}
        </footer>
      )}
    </section>
  );
}
