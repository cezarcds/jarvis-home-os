import React, { useEffect, useRef } from "react";
import { prefersReducedMotion } from "../live/DecodeText.jsx";

// Uma palavra de impacto que se forma a partir de partículas saindo do núcleo, segura por um instante
// e se desfaz. O texto é lido de um canvas escondido: cada ponto da letra vira o destino de uma partícula.
// Tempos e tamanhos ficam em KB logo abaixo (milissegundos e frações da tela).

const KB = {
  startDelayMs: 380,   // espera a cena se ajeitar antes de a palavra começar a se formar
  spreadMs: 480,       // as partículas não partem todas juntas
  formMs: 1150,        // quanto cada partícula leva até o seu lugar
  holdMs: 1500,        // a palavra fica legível
  dissolveMs: 1000,    // tempo de dispersão
  dissolveSpreadMs: 380,
  maxPoints: 1500,     // limite de partículas (abaixa em PCs fracos)
  origin: { x: 0.5, y: 0.44 },   // de onde elas saem (o núcleo recuado), em fração do palco
  line: { y: 0.46, maxWidth: 0.6, maxHeight: 0.24, maxPx: 210 },
};

const FONT = (px) =>
  `700 ${px}px "Segoe UI Variable Display","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif`;

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const easeOut = (u) => 1 - Math.pow(1 - u, 3.2);

/** Lê os pixels da palavra desenhada e devolve os pontos (em px do palco) onde as partículas pousam. */
export function sampleWord(word, w, h, maxPoints = KB.maxPoints) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const g = c.getContext("2d", { willReadFrequently: true });
  let fs = Math.min(h * KB.line.maxHeight, KB.line.maxPx);
  g.font = FONT(fs);
  const measured = g.measureText(word).width;
  const maxW = w * KB.line.maxWidth;
  if (measured > maxW) fs = (fs * maxW) / measured;
  g.font = FONT(fs);
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillStyle = "#fff";
  const cx = w / 2;
  const cy = h * KB.line.y;
  g.fillText(word, cx, cy);
  const data = g.getImageData(0, 0, w, h).data;

  let pts = [];
  let step = 3;
  for (; step < 16; step++) {
    pts = [];
    for (let y = 0; y < h; y += step) {
      for (let x = 0; x < w; x += step) {
        if (data[(y * w + x) * 4 + 3] > 140) pts.push([x, y]);
      }
    }
    if (pts.length <= maxPoints) break;
  }
  return { pts, step, fs, cx, cy };
}

/** Bolinha de luz pré-desenhada (centro quente, borda transparente): muito mais barata que gradiente por partícula. */
function makeSprite(rgb) {
  const s = document.createElement("canvas");
  s.width = s.height = 48;
  const g = s.getContext("2d");
  const grad = g.createRadialGradient(24, 24, 0, 24, 24, 24);
  grad.addColorStop(0, "rgba(255,255,255,0.95)");
  grad.addColorStop(0.18, `rgba(${rgb},0.75)`);
  grad.addColorStop(0.5, `rgba(${rgb},0.18)`);
  grad.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = grad;
  g.fillRect(0, 0, 48, 48);
  return s;
}

export default function KeywordBurst({ word, runKey }) {
  const ref = useRef(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !word || prefersReducedMotion()) return undefined;
    const parent = canvas.parentElement;
    const W = parent.clientWidth;
    const H = parent.clientHeight;
    if (W < 200 || H < 200) return undefined;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const text = word.toLocaleUpperCase("pt-BR");
    const { pts, step, cx, cy } = sampleWord(text, Math.round(W), Math.round(H));
    if (!pts.length) return undefined;

    const ox = W * KB.origin.x;
    const oy = H * KB.origin.y;
    const reach = Math.min(W, H) * 0.07;
    const parts = pts.map(([px, py]) => {
      const a = Math.random() * Math.PI * 2;
      const r = Math.sqrt(Math.random()) * reach;
      const sx = ox + Math.cos(a) * r;
      const sy = oy + Math.sin(a) * r;
      const tx = px + (Math.random() - 0.5) * step * 0.7;
      const ty = py + (Math.random() - 0.5) * step * 0.7;
      const dx = tx - sx;
      const dy = ty - sy;
      const dist = Math.hypot(dx, dy) || 1;
      const bend = (Math.random() - 0.5) * 0.95 * dist; // curva de lado: vira um arco de luz, não uma reta
      const dirx = tx - cx;
      const diry = ty - cy;
      const dl = Math.hypot(dirx, diry) || 1;
      const push = 50 + Math.random() * 190;
      return {
        sx, sy, tx, ty,
        qx: (sx + tx) / 2 - (dy / dist) * bend,
        qy: (sy + ty) / 2 + (dx / dist) * bend,
        d: Math.random() * KB.spreadMs,
        f: KB.formMs * (0.75 + Math.random() * 0.4),
        dd: Math.random() * KB.dissolveSpreadMs,
        vx: (dirx / dl) * push + (Math.random() - 0.5) * 70,
        vy: (diry / dl) * push + (Math.random() - 0.5) * 70 - 28,
        size: clamp(step * (0.5 + Math.random() * 0.35), 1.4, 3.6),
        warm: Math.random() < 0.13,
        seed: Math.random() * 100,
        px: sx, py: sy,
      };
    });

    const cyan = makeSprite("103,232,249");
    const amber = makeSprite("251,191,36");
    const dissolveAt = KB.spreadMs + KB.formMs * 1.15 + KB.holdMs;
    const total = dissolveAt + KB.dissolveMs + KB.dissolveSpreadMs + 60;

    let raf = 0;
    let t0 = 0;
    let started = false;
    const startTimer = setTimeout(() => {
      started = true;
      t0 = performance.now();
      raf = requestAnimationFrame(frame);
    }, KB.startDelayMs);

    function frame(now) {
      const t = now - t0;
      ctx.clearRect(0, 0, W, H);
      if (t > total) return;
      ctx.globalCompositeOperation = "lighter";

      const streaks = [];
      for (const p of parts) {
        const u = clamp((t - p.d) / p.f, 0, 1);
        if (t < p.d) continue;
        const e = easeOut(u);
        const m = 1 - e;
        let x = m * m * p.sx + 2 * m * e * p.qx + e * e * p.tx;
        let y = m * m * p.sy + 2 * m * e * p.qy + e * e * p.ty;
        let a = Math.min(1, u * 3.2);

        if (u >= 1) {
          // segurando: um tremor leve, como luz viva
          x += Math.sin(t * 0.004 + p.seed) * 0.7;
          y += Math.cos(t * 0.0035 + p.seed * 1.7) * 0.7;
          a *= 0.8 + 0.2 * Math.sin(t * 0.006 + p.seed * 3);
        }
        const v = clamp((t - dissolveAt - p.dd) / KB.dissolveMs, 0, 1);
        if (v > 0) {
          const k = Math.pow(v, 1.5);
          x += p.vx * k;
          y += p.vy * k;
          a *= 1 - v;
        }
        if ((u < 1 || v > 0) && a > 0.04) streaks.push(p.px, p.py, x, y, a);
        p.px = x;
        p.py = y;
        if (a <= 0.01) continue;

        const s = p.size;
        ctx.globalAlpha = a * 0.9;
        ctx.drawImage(p.warm ? amber : cyan, x - s * 2.6, y - s * 2.6, s * 5.2, s * 5.2);
        ctx.globalAlpha = a;
        ctx.fillStyle = "#e8fdff";
        ctx.fillRect(x - s * 0.4, y - s * 0.4, s * 0.8, s * 0.8);
      }

      // rastros de luz: o que dá a sensação de velocidade enquanto forma e dispersa
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(103,232,249,0.42)";
      ctx.globalAlpha = 0.55;
      ctx.beginPath();
      for (let i = 0; i < streaks.length; i += 5) {
        ctx.moveTo(streaks[i], streaks[i + 1]);
        ctx.lineTo(streaks[i + 2], streaks[i + 3]);
      }
      ctx.stroke();

      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      raf = requestAnimationFrame(frame);
    }

    return () => {
      clearTimeout(startTimer);
      if (started) cancelAnimationFrame(raf);
      ctx.clearRect(0, 0, W, H);
    };
  }, [word, runKey]);

  if (!word) return null;
  return <canvas ref={ref} className="st-kw" aria-hidden="true" />;
}
