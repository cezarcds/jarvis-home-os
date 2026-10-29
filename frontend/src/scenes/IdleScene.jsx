import React, { useEffect, useState } from "react";
import HologramCanvas from "../components/HologramCanvas.jsx";

const OWNER = (import.meta.env.VITE_OWNER_NAME || "").trim();

function greeting(d) {
  const h = d.getHours();
  const base = h < 5 ? "Boa madrugada" : h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
  return OWNER ? `${base}, ${OWNER}` : base;
}

function Corner({ className }) {
  return <span className={`absolute w-8 h-8 border-hud-cyan/50 ${className}`} />;
}

export default function IdleScene({ onWake }) {
  const [t, setT] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setT(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const hh = String(t.getHours()).padStart(2, "0");
  const mm = String(t.getMinutes()).padStart(2, "0");
  const ss = String(t.getSeconds()).padStart(2, "0");
  const date = t.toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });

  return (
    <div
      className="blueprint relative h-full w-full flex flex-col items-center justify-between text-hud-cyan cursor-pointer select-none"
      style={{ backgroundColor: "#030712" }}
      onClick={onWake}
    >
      <HologramCanvas />

      {/* Varredura horizontal sutil */}
      <div className="scanline pointer-events-none absolute inset-x-0 h-24" />

      {/* Cantos estilo HUD */}
      <Corner className="top-4 left-4 border-t border-l" />
      <Corner className="top-4 right-4 border-t border-r" />
      <Corner className="bottom-4 left-4 border-b border-l" />
      <Corner className="bottom-4 right-4 border-b border-r" />

      <header className="relative z-10 pt-6 text-xs tracking-[0.5em] opacity-70">
        JARVIS // HOME OS
      </header>

      <div className="relative z-10 flex flex-col items-center gap-2 mb-6">
        <div className="text-sm tracking-[0.35em] text-cyan-200/80 uppercase">{greeting(t)}</div>
        <div
          className="font-light tabular-nums leading-none"
          style={{ fontSize: "clamp(56px, 9vw, 120px)", textShadow: "0 0 24px rgba(6,182,212,0.6)" }}
        >
          {hh}
          <span className="blink">:</span>
          {mm}
          <span className="text-2xl align-top ml-2 opacity-60">{ss}</span>
        </div>
        <div className="text-xs tracking-[0.3em] uppercase opacity-70">{date}</div>
      </div>

      <footer className="relative z-10 pb-6 flex flex-col items-center gap-1 text-[10px] tracking-[0.4em]">
        <span className="opacity-60">SISTEMA EM ESPERA // TODOS OS SISTEMAS OPERACIONAIS</span>
        <span className="text-hud-amber blink-slow">TOQUE OU MOVA O MOUSE PARA ATIVAR</span>
      </footer>
    </div>
  );
}
