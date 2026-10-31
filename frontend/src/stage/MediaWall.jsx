import React, { useState } from "react";
import NewsFace from "./NewsFace.jsx";
import "./news-cards.css";

// Imagem com plano B: se a URL principal falhar na tela, troca por fallback_url (quando o backend mandou).
function SafeImg({ item, alt }) {
  const [src, setSrc] = useState(item.url);
  return (
    <img
      className="mw-img"
      src={src}
      alt={alt}
      draggable="false"
      referrerPolicy="no-referrer"
      onError={() => {
        if (item.fallback_url && src !== item.fallback_url) setSrc(item.fallback_url);
      }}
    />
  );
}

function Content({ entry, featured, visible, alt }) {
  const { item } = entry;
  if (item.kind === "news") return <NewsFace item={item} featured={featured} />;
  if (item.kind === "image") return <SafeImg key={item.url} item={item} alt={alt} />;
  if (item.src) {
    // Vários vídeos tocam ao mesmo tempo (mudos e em laço), como um mural.
    return <video key={item.src} className="mw-img" src={item.src} poster={item.poster} muted autoPlay loop playsInline />;
  }
  if (item.embed && featured && visible) {
    // O player do YouTube é pesado: só o cartão em destaque toca; os outros mostram a capa.
    return (
      <iframe
        key={item.embed}
        className="mw-embed"
        title={alt || "Vídeo"}
        src={`${item.embed}?autoplay=1&mute=1&controls=0&rel=0&playsinline=1&modestbranding=1`}
        allow="autoplay; encrypted-media; picture-in-picture"
        referrerPolicy="strict-origin-when-cross-origin"
      />
    );
  }
  return item.poster ? <img className="mw-img" src={item.poster} alt={alt} referrerPolicy="no-referrer" /> : <div className="mw-poster">▶</div>;
}

/**
 * Mural de mídia flutuante. `cards` vem de placeWall (posições em % do palco); cada cartão tem a
 * própria chave, então ao mudar o conjunto os que ficam deslizam para o novo lugar e os novos
 * entram "de trás para a frente".
 */
export default function MediaWall({ cards, entries, scene, beat, visible }) {
  if (!cards.length) return null;
  const captionOf = (id) => scene.media.find((m) => m.id === id)?.caption;
  return (
    <>
      {cards.map((c) => {
        const entry = entries[c.id];
        if (!entry) return null;
        const caption = c.featured ? beat?.caption || entry.item?.caption || captionOf(c.id) : "";
        const credit = entry.item ? [entry.item.credit, entry.item.license, entry.item.source].filter(Boolean).join(" · ") : "";
        return (
          <figure
            key={c.id}
            className={`mw-card ${c.featured ? "is-featured" : ""} ${entry.status === "loading" ? "is-loading" : ""}`}
            style={{
              left: `${c.x}%`, top: `${c.y}%`, width: `${c.w}%`, height: `${c.h}%`,
              "--rot": `${c.rot}deg`, "--d": `${c.delay}ms`, "--f": `${c.float}s`,
            }}
          >
            <div className="mw-inner">
              {entry.status === "loading" ? (
                <div className="mw-loading"><span /><p>BUSCANDO…</p></div>
              ) : (
                <Content entry={entry} featured={c.featured || cards.length === 1} visible={visible} alt={caption || entry.item.title || ""} />
              )}
              <span className="mw-corner tl" /><span className="mw-corner tr" /><span className="mw-corner bl" /><span className="mw-corner br" />
              {caption && <figcaption className="mw-caption"><b>▸</b> {caption}</figcaption>}
              {credit && c.featured && <span className="mw-credit">{credit}</span>}
            </div>
          </figure>
        );
      })}
    </>
  );
}
