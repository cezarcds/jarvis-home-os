import React, { useMemo } from "react";

const glyph = { diagram: "◇", steps: "↗", concepts: "✳", comparison: "⇄", timeline: "⌁", equation: "∑" };
const palette = ["#67e8f9", "#fbbf24", "#a78bfa", "#34d399", "#fb7185"];

function DrawLine({ x1, y1, x2, y2, delay = 0 }) {
  return <line className="draw-line" x1={x1} y1={y1} x2={x2} y2={y2} style={{ animationDelay: `${delay}ms` }} />;
}

function DiagramStage({ visual, index }) {
  const items = Array.isArray(visual.items) ? visual.items.slice(0, 5) : [];
  const kind = visual.type || "diagram";
  const isCompare = kind === "comparison";
  const isEquation = kind === "equation";
  const isFlow = kind === "steps" || kind === "timeline";
  const cols = Math.max(1, Math.min(items.length, 5));
  return (
    <article className={`stage-card stage-${kind}`} style={{ "--stage-index": index }}>
      <div className="stage-heading">
        <div className="stage-glyph">{glyph[kind] || "◇"}</div>
        <div><div className="stage-kicker">VISUALIZAÇÃO / {String(index + 1).padStart(2, "0")}</div><h2>{visual.title || "Modelo conceitual"}</h2></div>
        <span className="stage-live">DESENHANDO</span>
      </div>
      <div className={`stage-graphic ${isCompare ? "graphic-compare" : ""} ${isEquation ? "graphic-equation" : ""}`}>
        <svg className="stage-wires" viewBox="0 0 1000 420" preserveAspectRatio="none" aria-hidden="true">
          <defs><linearGradient id={`wire-${index}`} x1="0" x2="1"><stop offset="0" stopColor="#22d3ee" stopOpacity=".05"/><stop offset=".5" stopColor="#67e8f9" stopOpacity=".9"/><stop offset="1" stopColor="#22d3ee" stopOpacity=".08"/></linearGradient></defs>
          {items.slice(0, -1).map((_, i) => {
            const count = items.length;
            const x1 = isCompare ? (i % 2 === 0 ? 250 : 750) : 100 + (i * 800 / Math.max(1, count - 1));
            const x2 = isCompare ? 1000 - x1 : 100 + ((i + 1) * 800 / Math.max(1, count - 1));
            const y = isFlow ? 210 : 190 + (i % 2) * 45;
            return <DrawLine key={i} x1={x1} y1={y} x2={x2} y2={isFlow ? y : 190 + ((i + 1) % 2) * 45} delay={i * 160}/>;
          })}
        </svg>
        <div className={`stage-nodes ${isFlow ? "nodes-flow" : ""} ${isCompare ? "nodes-compare" : ""} ${isEquation ? "nodes-equation" : ""}`}>
          {items.map((item, i) => <React.Fragment key={`${item.label}-${i}`}>
            <div className={`stage-node ${i === 0 ? "node-primary" : ""}`} style={{ "--node-color": palette[i % palette.length], "--node-delay": `${180 + i * 180}ms` }}>
              <span className="node-index">{String(i + 1).padStart(2, "0")} / NODE</span>
              <strong>{item.label}</strong>
              <p>{item.detail}</p>
              <span className="node-port" />
            </div>
            {isEquation && i < items.length - 1 && <span className="equation-symbol">+</span>}
            {isFlow && i < items.length - 1 && <span className="flow-arrow">{kind === "timeline" ? "→" : "↓"}</span>}
          </React.Fragment>)}
        </div>
      </div>
      {visual.caption && <div className="stage-caption"><span>↳</span>{visual.caption}</div>}
    </article>
  );
}

function DeskGrid() {
  return <div className="desk-grid" aria-hidden="true"><div className="desk-horizon"/><div className="desk-grid-plane"/><div className="desk-orbit orbit-a"/><div className="desk-orbit orbit-b"/></div>;
}

export default function VisualExplain({ data, loading = false, question = "", answer = "", status = "PROCESSING" }) {
  const visuals = useMemo(() => (data?.visuals || []).slice(0, 3), [data]);
  return (
    <section className="visual-workspace" aria-live="polite">
      <DeskGrid />
      <div className="workspace-meta"><span className="meta-dot"/><span>JARVIS / EXPLICAÇÃO VISUAL</span><span className="meta-separator">·</span><span>{status === "SPEAKING" ? "NARRANDO" : loading ? "CONSTRUINDO CENA" : "MODELO INTERATIVO"}</span></div>
      <div className="workspace-question"><span>CONSULTA</span><p>{question || "Preparando a visualização…"}</p></div>
      {loading && !data && <div className="workspace-loading"><div className="loading-orb"><i/><i/><i/></div><div><strong>Construindo a explicação</strong><p>Organizando conceitos, conexões e camadas visuais.</p></div></div>}
      {data && <div className="workspace-content">
        <div className="workspace-title"><div className="title-overline">PROJEÇÃO DIDÁTICA // JARVIS</div><h1>{data.title || "Explicação visual"}</h1><p>Elementos montados para acompanhar a explicação falada.</p></div>
        <div className={`workspace-stages stages-${visuals.length || 1}`}>{visuals.map((visual, i) => <DiagramStage key={`${visual.title}-${i}`} visual={visual} index={i}/>)}</div>
        <div className="workspace-narration"><span className="narration-bars"><i/><i/><i/><i/><i/></span><div><span>VOZ DO JARVIS</span><p>{data.answer || answer}</p></div></div>
      </div>}
      {!loading && !data && <div className="workspace-fallback"><p>{answer}</p></div>}
      <div className="workspace-footer"><span>PROJEÇÃO DE MESA</span><span>ESC / FECHAR</span><span>RESPONSIVO · VIEWPORT ADAPTATIVO</span></div>
    </section>
  );
}
