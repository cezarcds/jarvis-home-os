import React, { useEffect, useRef, useState } from "react";
import { fetchSystemStats, fetchWeather } from "../lib/api.js";

function Panel({ title, icon, children, className = "" }) {
  return (
    <div className={`panel p-3.5 ${className}`}>
      <div className="panel-title">
        {icon && <span aria-hidden="true">{icon}</span>}
        {title}
      </div>
      {children}
    </div>
  );
}

function Bar({ label, value }) {
  const known = typeof value === "number";
  return (
    <div className="mb-2.5 last:mb-0">
      <div className="flex justify-between text-xs">
        <span>{label}</span>
        <span>{known ? `${value}%` : "—"}</span>
      </div>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${known ? value : 0}%` }} />
      </div>
    </div>
  );
}

/** CPU e memória reais do computador (backend/psutil). Sem o backend, mostra "—" em vez de inventar. */
function useSystemStats() {
  const [stats, setStats] = useState({ cpu: null, mem: null });
  useEffect(() => {
    let alive = true;
    const load = () =>
      fetchSystemStats()
        .then((s) => alive && setStats({ cpu: s.cpu, mem: s.mem }))
        .catch(() => alive && setStats({ cpu: null, mem: null }));
    load();
    const id = setInterval(load, 3000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  return stats;
}

function Sun() {
  return (
    <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="#fbbf24" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

export function LeftPanels() {
  const stats = useSystemStats();
  const [weather, setWeather] = useState(null);
  const [weatherErr, setWeatherErr] = useState(false);

  useEffect(() => {
    const load = () =>
      fetchWeather()
        .then((w) => { setWeather(w); setWeatherErr(false); })
        .catch((e) => { console.error("[JARVIS] clima:", e); setWeatherErr(true); });
    load();
    const id = setInterval(load, 10 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex flex-col gap-4 w-64">
      <Panel title="SISTEMA">
        <Bar label="CPU" value={stats.cpu} />
        <Bar label="MEM" value={stats.mem} />
      </Panel>
      <Panel title="METEOROLOGIA">
        {weather ? (
          <div className="flex items-center gap-3">
            <Sun />
            <div className="text-3xl font-light text-cyan-50">{Math.round(weather.temperature_2m)}°C</div>
            <div className="ml-auto text-[11px] leading-5 text-cyan-100/70">
              <div>Vento {weather.wind_speed_10m} km/h</div>
              <div>Umidade {weather.relative_humidity_2m}%</div>
            </div>
          </div>
        ) : (
          <div className={`text-xs ${weatherErr ? "text-hud-amber" : ""}`}>
            {weatherErr ? "SEM DADOS" : "CARREGANDO..."}
          </div>
        )}
      </Panel>
    </div>
  );
}

/** Eventos do sistema (o que o Jarvis fez e ouviu). */
function Events({ logs }) {
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [logs]);
  return (
    <Panel title="EVENTOS" className="flex flex-col h-56">
      <div ref={ref} className="flex-1 overflow-y-auto text-[11px] leading-5 space-y-0.5 pr-1">
        {logs.map((l, i) => (
          <div key={i} className={l.level === "warn" ? "text-hud-amber" : "text-cyan-100/80"}>
            <span className="opacity-50">{l.time}</span> {l.msg}
          </div>
        ))}
      </div>
    </Panel>
  );
}

/** Miniaturas das imagens e vídeos das últimas cenas. Só mostra o que realmente apareceu. */
function RecentMedia({ items }) {
  return (
    <Panel title="MÍDIA RECENTE">
      {items.length ? (
        <div className="grid grid-cols-4 gap-1.5">
          {items.slice(0, 8).map((m) => (
            <a key={m.key} href={m.page || m.thumb} target="_blank" rel="noreferrer" title={m.title} className="recent-thumb">
              <img src={m.thumb} alt={m.title || ""} referrerPolicy="no-referrer" draggable="false" />
              {m.kind === "video" && <span>▶</span>}
            </a>
          ))}
        </div>
      ) : (
        <div className="text-[11px] text-cyan-100/50 leading-5">As imagens e vídeos das suas cenas aparecem aqui.</div>
      )}
    </Panel>
  );
}

export function RightConsole({ logs, recentMedia = [] }) {
  return (
    <div className="flex flex-col gap-4 w-72">
      <Events logs={logs} />
      <RecentMedia items={recentMedia} />
    </div>
  );
}
