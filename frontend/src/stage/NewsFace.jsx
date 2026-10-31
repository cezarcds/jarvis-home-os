import React, { useState } from "react";

function hora(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const hoje = new Date();
  return d.toDateString() === hoje.toDateString()
    ? d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

/** Cartão de notícia dentro do mural: capa (quando há), veículo, hora e manchete. */
export default function NewsFace({ item, featured }) {
  const [broken, setBroken] = useState(false);
  const cover = item.image && !broken ? item.image : null;
  const meta = [item.outlet, hora(item.published)].filter(Boolean).join(" · ");
  return (
    <div className={`nf ${cover ? "has-cover" : "no-cover"} ${featured ? "is-featured" : ""}`}>
      {cover && (
        <img className="nf-cover" src={cover} alt="" draggable="false" referrerPolicy="no-referrer" onError={() => setBroken(true)} />
      )}
      <div className="nf-text">
        {meta && <span className="nf-meta">{meta}</span>}
        <strong className="nf-title">{item.title}</strong>
      </div>
    </div>
  );
}
