import React from "react";

const STYLE = {
  STANDBY: { color: "#06b6d4", glow: 0.25, anim: "none" },
  LISTENING: { color: "#f59e0b", glow: 0.6, anim: "pulse-ring 1s ease-in-out infinite" },
  PROCESSING: { color: "#06b6d4", glow: 0.5, anim: "none" },
  SPEAKING: { color: "#22d3ee", glow: 0.9, anim: "pulse-ring 0.6s ease-in-out infinite" },
};

export default function CoreRings({ status, onClick }) {
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
