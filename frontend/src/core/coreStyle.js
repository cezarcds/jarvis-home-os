// Aparência do núcleo em cada estado. As cores seguem as do CoreRings antigo
// (ciano em espera, âmbar ouvindo, ciano vivo falando).

export const STATE_STYLE = {
  STANDBY:    { colorA: "#0b3b66", colorB: "#38bdf8", intensity: 0.9, spin: 0.12, ringSpeed: 0.6, particleSpeed: 1.0 },
  LISTENING:  { colorA: "#7c3a06", colorB: "#fbbf24", intensity: 1.0, spin: 0.30, ringSpeed: 1.6, particleSpeed: 2.2 },
  PROCESSING: { colorA: "#0b3b66", colorB: "#67e8f9", intensity: 1.0, spin: 0.90, ringSpeed: 3.2, particleSpeed: 3.0 },
  SPEAKING:   { colorA: "#0a5a78", colorB: "#2de2ff", intensity: 1.0, spin: 0.35, ringSpeed: 1.4, particleSpeed: 1.8 },
};

export function styleFor(status) {
  return STATE_STYLE[status] || STATE_STYLE.STANDBY;
}

/** "#rrggbb" -> [r, g, b] em 0..1 (para uniforms e THREE.Color). */
export function hexToRgb01(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim());
  if (!m) return [1, 1, 1];
  const n = parseInt(m[1], 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}
