import React, { useEffect, useRef, useState } from "react";
import { fetchWeather } from "../lib/api.js";

function Panel({ title, children, className = "" }) {
  return (
    <div className={`panel p-3 ${className}`}>
      <div className="text-[10px] tracking-[0.3em] text-hud-cyan/70 mb-2">// {title}</div>
      {children}
    </div>
  );
}

function Bar({ label, value }) {
  return (
    <div className="mb-2">
      <div className="flex justify-between text-xs">
        <span>{label}</span>
        <span>{value}%</span>
      </div>
      <div className="h-1 bg-hud-cyan/15">
        <div className="h-1 bg-hud-cyan transition-all duration-700" style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

export function LeftPanels() {
  const [cpu, setCpu] = useState(30);
  const [mem, setMem] = useState(45);
  const [weather, setWeather] = useState(null);
  const [weatherErr, setWeatherErr] = useState(false);

  // Telemetria simulada
  useEffect(() => {
    const id = setInterval(() => {
      setCpu(Math.round(20 + Math.random() * 40));
      setMem(Math.round(40 + Math.random() * 20));
    }, 1500);
    return () => clearInterval(id);
  }, []);

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
      <Panel title="TELEMETRIA">
        <Bar label="CPU" value={cpu} />
        <Bar label="MEM" value={mem} />
      </Panel>
      <Panel title="METEOROLOGIA">
        {weather ? (
          <div className="text-sm space-y-1">
            <div className="text-2xl text-hud-cyan">{Math.round(weather.temperature_2m)}°C</div>
            <div>Umidade: {weather.relative_humidity_2m}%</div>
            <div>Vento: {weather.wind_speed_10m} km/h</div>
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

export function RightConsole({ logs }) {
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [logs]);

  return (
    <Panel title="CONSOLE DE EVENTOS" className="w-72 h-80 flex flex-col">
      <div ref={ref} className="flex-1 overflow-y-auto text-[11px] leading-5 space-y-0.5">
        {logs.map((l, i) => (
          <div key={i} className={l.level === "warn" ? "text-hud-amber" : "text-hud-cyan/80"}>
            <span className="opacity-50">{l.time}</span> {l.msg}
          </div>
        ))}
      </div>
    </Panel>
  );
}
