import React from "react";

const STYLE = {
  STANDBY: { color: "#06b6d4", glow: 0.25, anim: "none" },
  LISTENING: { color: "#f59e0b", glow: 0.6, anim: "pulse-ring 1s ease-in-out infinite" },
  PROCESSING: { color: "#06b6d4", glow: 0.5, anim: "none" },
  SPEAKING: { color: "#22d3ee", glow: 0.9, anim: "pulse-ring 0.6s ease-in-out infinite" },
};

/** Versão compacta (modo visual): um botão de microfone pequeno que não disputa espaço com a cena. */
function MicDock({ status, onClick }) {
  const s = STYLE[status] || STYLE.STANDBY;
  return (
    <button
      onClick={onClick}
      aria-label={`Microfone (${status})`}
      title={`${status} — toque para falar`}
      className="relative flex items-center justify-center rounded-full transition"
      style={{
        width: 64,
        height: 64,
        border: `2px solid ${s.color}`,
        background: `radial-gradient(circle, ${s.color}33, rgba(2,6,13,.85) 75%)`,
        boxShadow: `0 0 ${30 * s.glow}px ${s.color}`,
        color: s.color,
        animation: s.anim,
      }}
    >
      {status === "SPEAKING" ? (
        <div className="flex items-center gap-[3px]" style={{ height: 24 }}>
          {[0, 1, 2, 3, 4].map((i) => (
            <span key={i} style={{ width: 3, height: 24, background: s.color, animation: `wave 0.7s ease-in-out ${i * 0.09}s infinite` }} />
          ))}
        </div>
      ) : (
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
        </svg>
      )}
    </button>
  );
}

export default function CoreRings({ status, onClick, compact = false }) {
  if (compact) return <MicDock status={status} onClick={onClick} />;
  const s = STYLE[status];
  const fast = status === "PROCESSING";
  const ring = (size, border, anim) => ({
    position: "absolute",
    width: size,
    height: size,
    borderRadius: "50%",
    border: `${border} ${s.color}`,
    opacity: 0.8,
    animation: anim,
  });

  return (
    <div className="relative flex items-center justify-center" style={{ width: 340, height: 340 }}>
      <div style={{ ...ring(340, "1px dashed", `spin-cw ${fast ? 4 : 30}s linear infinite`) }} />
      <div style={{ ...ring(290, "2px dotted", `spin-ccw ${fast ? 3 : 22}s linear infinite`) }} />
      <div style={{ ...ring(240, "1px solid", s.anim) }} />

      <button
        onClick={onClick}
        aria-label="Ativar voz"
        className="relative z-10 flex items-center justify-center rounded-full transition"
        style={{
          width: 170,
          height: 170,
          border: `2px solid ${s.color}`,
          background: `radial-gradient(circle, ${s.color}33, transparent 70%)`,
          boxShadow: `0 0 ${60 * s.glow}px ${s.color}`,
          color: s.color,
        }}
      >
        {status === "SPEAKING" ? (
          <div className="flex items-center gap-1" style={{ height: 50 }}>
            {[0, 1, 2, 3, 4, 5, 6].map((i) => (
              <span
                key={i}
                style={{
                  width: 4,
                  height: 50,
                  background: s.color,
                  animation: `wave 0.7s ease-in-out ${i * 0.09}s infinite`,
                }}
              />
            ))}
          </div>
        ) : (
          <span className="text-xs tracking-[0.3em]">{status}</span>
        )}
      </button>
    </div>
  );
}
