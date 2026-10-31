import React, { useCallback, useEffect, useState } from "react";
import { fetchHeadlines, fetchTopics, timeAgo } from "../../lib/newsApi.js";
import "./news.css";

const REFRESH_MS = 10 * 60 * 1000;
const FALLBACK_TABS = [{ key: "mercado", label: "Mercado" }, { key: "brasil", label: "Brasil" }];

/** Cartão de manchetes da tela principal. Usa RSS, sem chave e sem passar pela pesquisa. */
export default function HeadlinesCard({ initialTopic = "mercado", limit = 4 }) {
  const [tabs, setTabs] = useState(FALLBACK_TABS);
  const [topic, setTopic] = useState(initialTopic);
  const [items, setItems] = useState([]);
  const [state, setState] = useState("loading"); // loading | ok | error

  useEffect(() => {
    fetchTopics().then(setTabs).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    try {
      const data = await fetchHeadlines(topic, limit);
      setItems(data.items || []);
      setState("ok");
    } catch {
      setState("error");
    }
  }, [topic, limit]);

  useEffect(() => {
    setState("loading");
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="panel p-3 w-64 max-w-full text-xs space-y-2">
      <div className="flex items-center gap-3 tracking-[0.3em] text-[10px] uppercase">
        <span className="text-hud-cyan/60">Manchetes</span>
        {tabs.slice(0, 4).map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTopic(t.key)}
            className={t.key === topic ? "text-hud-amber" : "text-hud-cyan/50 hover:text-hud-cyan"}
          >
            {t.label}
          </button>
        ))}
      </div>

      {state === "loading" && <div className="text-hud-cyan/40">carregando…</div>}
      {state === "error" && <div className="text-hud-amber/80">Sem conexão com as notícias.</div>}
      {state === "ok" && items.length === 0 && <div className="text-hud-cyan/40">Nada novo por aqui.</div>}

      <ul className="space-y-2">
        {items.map((it) => (
          <li key={it.id}>
            <a href={it.url} target="_blank" rel="noopener noreferrer" className="block no-underline group">
              <div className="news-clamp-2 text-cyan-100/90 leading-snug group-hover:text-hud-amber transition-colors">
                {it.title}
              </div>
              <div className="text-[10px] tracking-widest text-hud-cyan/50 uppercase mt-0.5">
                {it.outlet || "Fonte"} · {timeAgo(it.published)}
              </div>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
