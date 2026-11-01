import React, { useEffect, useRef } from "react";

/**
 * Palavra-impacto feita de partículas (como no vídeo de referência: "NÃO", "VERDADE.").
 * As partículas voam até formar a palavra, tremem de leve e, quando `active` vira false,
 * se dispersam e somem. Quando todas sumiram, chama `onGone`.
 *
 * Props
 *  - text      palavra (1 a 2 palavras). Mude a `key` para trocar de palavra.
 *  - tone      "neutral" | "alert" | "positive"
 *  - active    true = formada; false = dispersa
 *  - anchors   [{x,y}] em px dentro do contêiner: de onde as partículas nascem
 *              (ex.: centro de cada foto/vídeo na tela, para a palavra "sair" das mídias).
 *              Vazio = entram pelas bordas.
 *  - onGone    chamado uma vez, quando a dispersão termina
 *
 * Uso: coloque dentro de um contêiner `position: relative` (ele cobre o contêiner todo,
 * não captura cliques).  <ParticleWord key={impact.text} text={impact.text} tone={impact.tone} active={visible} />
 */
const TONES = {
  neutral: ["#e0fbff", "#67e8f9"],
  alert: ["#fef3c7", "#f97316"],
  positive: ["#dcfce7", "#34d399"],
};
const MAX_PARTICLES = 3200;

export default function ParticleWord({ text, tone = "neutral", active = true, anchors = [], onGone, className = "" }) {
  const canvasRef = useRef(null);
  const live = useRef({ active, onGone, anchors });
  live.current = { active, onGone, anchors };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !text) return undefined;
    const ctx = canvas.getContext("2d");
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const [c1, c2] = TONES[tone] || TONES.neutral;

    let w = 0, h = 0, raf = 0, leaving = false, leaveT = 0, gone = false, particles = [], last = performance.now();

    const build = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      if (!w || !h) return;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // 1) desenha a palavra num canvas escondido e lê onde há pixels acesos
      const off = document.createElement("canvas");
      off.width = w;
      off.height = h;
      const o = off.getContext("2d", { willReadFrequently: true });
      const label = String(text).toUpperCase();
      const font = (s) => `800 ${s}px ui-sans-serif, "Arial Black", system-ui, sans-serif`;
      let size = Math.min(h * 0.34, 260);
      o.font = font(size);
      const tw = o.measureText(label).width;
      if (tw > w * 0.82) size *= (w * 0.82) / tw;
      o.font = font(size);
      o.textAlign = "center";
      o.textBaseline = "middle";
      o.fillStyle = "#fff";
      o.fillText(label, w / 2, h * 0.5);
      const data = o.getImageData(0, 0, w, h).data;

      const step = Math.max(3, Math.round(size / 42));
      const targets = [];
      for (let y = 0; y < h; y += step) {
        for (let x = 0; x < w; x += step) {
          if (data[(y * w + x) * 4 + 3] > 128) targets.push([x, y]);
        }
      }
      // limita a quantidade (desempenho): sorteia quais ficam
      while (targets.length > MAX_PARTICLES) targets.splice((Math.random() * targets.length) | 0, 1);

      // 2) de onde cada partícula nasce
      const from = live.current.anchors;
      const spawn = () => {
        if (from.length) {
          const a = from[(Math.random() * from.length) | 0];
          return [a.x + (Math.random() - 0.5) * 40, a.y + (Math.random() - 0.5) * 40];
        }
        const side = (Math.random() * 4) | 0;
        if (side === 0) return [Math.random() * w, -40];
        if (side === 1) return [Math.random() * w, h + 40];
        if (side === 2) return [-40, Math.random() * h];
        return [w + 40, Math.random() * h];
      };

      particles = targets.map(([tx, ty]) => {
        const [sx, sy] = reduced ? [tx, ty] : spawn();
        return {
          x: sx, y: sy, tx, ty, vx: 0, vy: 0,
          delay: reduced ? 0 : Math.random() * 450,
          r: step * (0.28 + Math.random() * 0.2),
          hot: Math.random() < 0.3,
          ph: Math.random() * 6.28,
          ox: 0, oy: 0, // velocidade de fuga
        };
      });
      leaving = false;
      gone = false;
    };

    build();
    const ro = new ResizeObserver(() => build());
    ro.observe(canvas);
    const start = performance.now();

    const frame = (now) => {
      const dt = Math.min(2.5, (now - last) / 16.67);
      last = now;
      const t = now - start;
      ctx.clearRect(0, 0, w, h);

      if (!live.current.active && !leaving) {
        leaving = true;
        leaveT = now;
        for (const p of particles) {
          const ang = Math.random() * 6.28;
          const sp = 2 + Math.random() * 5;
          p.ox = Math.cos(ang) * sp;
          p.oy = Math.sin(ang) * sp - 1.2;
        }
      }
      const fade = leaving ? Math.max(0, 1 - (now - leaveT) / 900) : 1;

      ctx.globalCompositeOperation = "lighter";
      for (const p of particles) {
        if (leaving) {
          p.x += p.ox * dt;
          p.y += p.oy * dt;
          p.oy += 0.03 * dt;
        } else if (t >= p.delay) {
          // mola amortecida até o ponto da letra
          p.vx += ((p.tx - p.x) * 0.055 - p.vx * 0.2) * dt;
          p.vy += ((p.ty - p.y) * 0.055 - p.vy * 0.2) * dt;
          p.x += p.vx * dt;
          p.y += p.vy * dt;
        }
        // brilho de "vida" depois de formada
        const shimmer = leaving ? 1 : 0.75 + 0.25 * Math.sin(t * 0.004 + p.ph);
        const jx = leaving || reduced ? 0 : Math.sin(t * 0.003 + p.ph) * 0.6;
        const jy = leaving || reduced ? 0 : Math.cos(t * 0.0033 + p.ph) * 0.6;
        ctx.globalAlpha = fade * shimmer;
        ctx.fillStyle = p.hot ? c2 : c1;
        ctx.fillRect(p.x + jx, p.y + jy, p.r * 2, p.r * 2);
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";

      if (leaving && fade <= 0 && !gone) {
        gone = true;
        live.current.onGone?.();
      }
      if (!gone) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [text, tone]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 h-full w-full ${className}`}
      style={{ filter: "drop-shadow(0 0 10px rgba(103,232,249,0.35))" }}
    />
  );
}
