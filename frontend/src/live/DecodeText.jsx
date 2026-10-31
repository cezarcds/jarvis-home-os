import React, { useEffect, useRef, useState } from "react";

// Texto "vivo": as letras surgem como ruído digital e vão se resolvendo até virarem a frase.
// Usado nas chamadas da cena, no título e no rótulo do núcleo.

const GLYPHS = "01<>/\\|+=*#%&ABCDEFGHJKLMNPQRSTUVXZ▌░▒";
const TICK_MS = 42; // cadência do "ruído": mais lento que 60 fps de propósito, parece sinal digital

export function prefersReducedMotion() {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/** Instante (ms) em que cada letra se resolve: da esquerda para a direita, com um pouco de acaso. */
export function resolveTimes(text, duration, delay) {
  const chars = Array.from(text);
  const n = Math.max(1, chars.length);
  return chars.map((ch, i) => {
    if (ch === " ") return 0;
    const jitter = ((i * 7919) % 13) / 13; // determinístico (nada de Math.random no render)
    return delay + (i / n) * duration * 0.72 + jitter * duration * 0.28;
  });
}

/**
 * Mostra `text` decodificando. O texto verdadeiro fica sempre no DOM (invisível), então
 * leitores de tela e o layout não mudam; só a camada de cima anima.
 */
export default function DecodeText({ text, duration = 700, delay = 0, className = "" }) {
  const reduced = useRef(prefersReducedMotion());
  const [frame, setFrame] = useState(() => (reduced.current ? null : { t: -1 }));
  const safe = String(text ?? "");

  useEffect(() => {
    if (reduced.current || !safe) {
      setFrame(null);
      return undefined;
    }
    const times = resolveTimes(safe, duration, delay);
    const end = Math.max(...times) + TICK_MS;
    const t0 = performance.now();
    setFrame({ t: 0 });
    const id = setInterval(() => {
      const t = performance.now() - t0;
      if (t >= end) {
        clearInterval(id);
        setFrame(null);
      } else {
        setFrame({ t });
      }
    }, TICK_MS);
    return () => clearInterval(id);
  }, [safe, duration, delay]);

  if (!frame) return <span className={`dx ${className}`}>{safe}</span>;

  const chars = Array.from(safe);
  const times = resolveTimes(safe, duration, delay);
  return (
    <span className={`dx ${className}`}>
      <span className="dx-ghost">{safe}</span>
      <span className="dx-live" aria-hidden="true">
        {chars.map((ch, i) => {
          if (ch === " " || frame.t >= times[i]) return <span key={i}>{ch}</span>;
          if (frame.t < delay) return <span key={i} className="dx-wait">{ch}</span>;
          const g = GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
          return <span key={i} className="dx-g">{g}</span>;
        })}
      </span>
    </span>
  );
}
