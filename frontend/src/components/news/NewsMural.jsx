import React, { useState } from "react";
import { useNewsMural } from "../../hooks/useNewsMural.js";
import { timeAgo } from "../../lib/newsApi.js";
import "./news.css";

function Cover({ src }) {
  const [broken, setBroken] = useState(false);
  if (!src || broken) {
    return (
      <div className="h-28 w-full bg-hud-cyan/5 border-b border-hud-cyan/20 flex items-center justify-center text-hud-cyan/30 text-[10px] tracking-[0.35em]">
        SEM IMAGEM
      </div>
    );
  }
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setBroken(true)}
      className="h-28 w-full object-cover border-b border-hud-cyan/20"
    />
  );
}

function Card({ item, out }) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className={`news-card ${out ? "out" : ""} panel pointer-events-auto block w-72 max-w-[85vw] overflow-hidden no-underline`}
    >
      <Cover src={item.image} />
      <div className="p-3 space-y-1.5">
        <div className="flex items-center justify-between text-[10px] tracking-widest">
          <span className="text-hud-amber uppercase truncate pr-2">{item.outlet || "Fonte"}</span>
          <span className="text-hud-cyan/60 whitespace-nowrap">{timeAgo(item.published)}</span>
        </div>
        <div className="news-clamp-3 text-sm leading-snug text-cyan-100">{item.title}</div>
      </div>
    </a>
  );
}

function Callout({ item, side, out }) {
  const pos = side === "l" ? "left-4" : "right-4";
  return (
    <div
      className={`news-callout news-callout-${side} ${out ? "out" : ""} fixed ${pos} top-[38%] z-30 w-56 panel p-3 pointer-events-none hidden lg:block`}
    >
      <div className="text-[10px] tracking-[0.3em] text-hud-amber uppercase truncate">{item.outlet || "Fonte"}</div>
      <div className="news-clamp-2 text-xs leading-snug text-cyan-100/90 mt-1">{item.title}</div>
    </div>
  );
}

/**
 * Mural de notícias: cartões com capa, manchete, veículo e hora; entram e saem a cada trecho.
 * Chamadas laterais mostram "a seguir". A fonte fica sempre visível.
 */
export default function NewsMural({ news, speaking, onDismiss }) {
  const { visible, upcoming, phase, page, pages, close } = useNewsMural(news, { speaking, onDismiss });
  if (!visible.length) return null;
  const out = phase === "out";
  const label = news?.kind === "briefing" ? "RESUMO DO DIA" : news?.topic ? `NOTÍCIAS · ${news.topic}` : "NOTÍCIAS";

  return (
    <>
      {upcoming.map((it, i) => (
        <Callout key={`${it.id}-${page}`} item={it} side={i % 2 === 0 ? "l" : "r"} out={out} />
      ))}
      <div className="fixed inset-x-0 bottom-6 z-30 flex flex-col items-center gap-2 px-4 pointer-events-none">
        <div className="pointer-events-auto flex items-center gap-3 text-[10px] tracking-[0.4em] text-hud-cyan/70 uppercase">
          <span>{label}</span>
          {pages > 1 && <span>{page + 1}/{pages}</span>}
          <button type="button" onClick={close} aria-label="Fechar notícias" className="text-hud-cyan/60 hover:text-hud-amber">
            ✕
          </button>
        </div>
        <div className="flex flex-wrap justify-center gap-4">
          {visible.map((it) => (
            <Card key={`${it.id}-${page}`} item={it} out={out} />
          ))}
        </div>
      </div>
    </>
  );
}
