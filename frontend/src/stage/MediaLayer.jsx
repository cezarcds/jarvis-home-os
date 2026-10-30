import React, { useState } from "react";

// Imagem com plano B: se a URL principal falhar na tela, troca por fallback_url (quando o backend mandou).
function SafeImg({ item, alt }) {
  const [src, setSrc] = useState(item.url);
  return (
    <img
      className="ml-img"
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

export default function MediaLayer({ entry, caption, mode, visible }) {
  if (!entry || entry.status === "none") return null;

  if (entry.status === "loading") {
    return (
      <div className={`ml ml-${mode}`}>
        <div className="ml-loading"><span /><p>BUSCANDO REFERÊNCIA…</p></div>
      </div>
    );
  }

  const { item } = entry;
  const credit = [item.credit, item.license, item.source].filter(Boolean).join(" · ");
  const text = caption || item.caption || item.title;

  return (
    <div className={`ml ml-${mode}`}>
      <div className="ml-frame">
        {item.kind === "image" && <SafeImg key={item.url} item={item} alt={text || ""} />}
        {item.kind === "video" && item.embed && visible && (
          <iframe
            key={item.embed}
            className="ml-embed"
            title={text || "Vídeo"}
            src={`${item.embed}?autoplay=1&mute=1&controls=0&rel=0&playsinline=1&modestbranding=1`}
            allow="autoplay; encrypted-media; picture-in-picture"
            referrerPolicy="strict-origin-when-cross-origin"
          />
        )}
        {item.kind === "video" && item.src && (
          <video key={item.src} className="ml-img" src={item.src} poster={item.poster} muted autoPlay loop playsInline />
        )}
        <span className="ml-corner tl" /><span className="ml-corner tr" /><span className="ml-corner bl" /><span className="ml-corner br" />
        <div className="ml-scan" />
      </div>
      {mode !== "bg" && text && <div className="ml-caption"><b>▸</b> {text}</div>}
      {mode === "pane" && credit && <div className="ml-credit">{credit}</div>}
      {mode === "bg" && credit && <div className="ml-credit ml-credit-bg">{credit}</div>}
    </div>
  );
}
