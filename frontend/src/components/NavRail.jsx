import React from "react";

const ICONS = {
  home: <path d="M3 11l9-8 9 8v9a1 1 0 01-1 1h-5v-6H9v6H4a1 1 0 01-1-1z" />,
  list: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
  sliders: (
    <>
      <path d="M4 6h9M19 6h1M4 12h3M13 12h7M4 18h11M21 18h-1" />
      <circle cx="16" cy="6" r="2.2" /><circle cx="10" cy="12" r="2.2" /><circle cx="18" cy="18" r="2.2" />
    </>
  ),
  mic: (
    <>
      <path d="M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3z" />
      <path d="M19 11a7 7 0 01-14 0M12 18v3" />
    </>
  ),
};

function Icon({ name }) {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICONS[name]}
    </svg>
  );
}

function Item({ icon, label, active, onClick, title, dot }) {
  return (
    <button type="button" onClick={onClick} title={title || label} className={`rail-item ${active ? "is-active" : ""}`}>
      <Icon name={icon} />
      <span>{label}</span>
      {dot && <i className={`rail-dot rail-dot-${dot}`} />}
    </button>
  );
}

const MIC_DOT = { listening: "on", awake: "hot", connecting: "wait", loading: "wait", unavailable: "bad", error: "bad" };

/** Menu lateral. Só tem o que funciona: início, rotinas, configurações e a voz livre. */
export default function NavRail({ phase, onHome, onRoutines, onSettings, mic }) {
  return (
    <nav className="rail" aria-label="Navegação">
      <Item icon="home" label="Início" active={phase === "home"} onClick={onHome} title="Voltar ao início (Esc)" />
      <Item icon="list" label="Rotinas" onClick={onRoutines} title="Painel de rotinas (Alt+R)" />
      <Item icon="sliders" label="Config" onClick={onSettings} title="Conexões e configurações" />
      {mic.supported && (
        <>
          <div className="rail-spacer" />
          <Item
            icon="mic"
            label={mic.on ? "Voz livre" : "Voz off"}
            onClick={mic.toggle}
            title={mic.hint}
            dot={mic.on ? MIC_DOT[mic.state] || "wait" : "off"}
          />
        </>
      )}
    </nav>
  );
}
