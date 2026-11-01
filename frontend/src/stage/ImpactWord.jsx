import React, { useEffect, useRef } from "react";
import { IMPACT } from "./tuning.js";
import { formedRatio, makeParticles, samplePoints, stepParticles } from "./particles.js";
import { rng, hashStr } from "./handDrawn.js";

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Desenha a palavra num canvas escondido e devolve onde há tinta (os alvos das partículas). */
async function wordPoints(text, W, H) {
  const base = 200;
  try {
    await Promise.race([document.fonts.load(`${base}px ${IMPACT.font}`), new Promise((r) => setTimeout(r, 1200))]);
  } catch { /* sem a fonte: usa a de reserva */ }
  const off = document.createElement("canvas");
  off.width = W;
  off.height = H;
  const c = off.getContext("2d", { willReadFrequently: true });
  c.font = `${base}px ${IMPACT.font}`;
  const w200 = c.measureText(text).width || 1;
  const px = Math.max(24, Math.min((W * IMPACT.maxWidth * base) / w200, H * IMPACT.maxHeight * 1.1));
  c.font = `${px}px ${IMPACT.font}`;
  c.textAlign = "center";
  c.textBaseline = "middle";
  c.fillStyle = "#fff";
  c.fillText(text, W / 2, H * 0.46);
  const { data } = c.getImageData(0, 0, W, H);
  return { ...samplePoints(data, W, H, IMPACT.maxParticles, 3), px };
}

/** Uma palavra: forma, segura e se desfaz. Devolve { dissolve, cancel }. */
function startRun(canvas, impact) {
  const parent = canvas.parentElement;
  const W = Math.max(200, Math.round(parent.clientWidth));
  const H = Math.max(160, Math.round(parent.clientHeight));
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const color = IMPACT.colors[impact.tone] || IMPACT.colors.neutral;
  canvas.style.setProperty("--im-glow", color);

  let raf = 0;
  let cancelled = false;
  let hold = null;
  let phase = "form";
  let phaseStart = performance.now();
  let last = phaseStart;
  let state = null;
  let sizeBase = 3;

  const clear = () => ctx.clearRect(0, 0, W, H);
  const cancel = () => { cancelled = true; cancelAnimationFrame(raf); clearTimeout(hold); clear(); };
  const dissolve = () => {
    if (cancelled || phase === "dissolve") return;
    clearTimeout(hold);
    phase = "dissolve";
    phaseStart = performance.now();
  };

  const frame = (now) => {
    if (cancelled) return;
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const t = (now - phaseStart) / 1000;
    const alive = stepParticles(state, dt, phase, t);
    clear();
    ctx.globalCompositeOperation = "lighter";
    ctx.fillStyle = color;
    const shimmer = phase === "hold" ? 0.7 : 0;
    let lastA = -1;
    for (let i = 0; i < state.n; i++) {
      const a = state.alpha[i];
      if (a < 0.03) continue;
      if (Math.abs(a - lastA) > 0.06) { ctx.globalAlpha = a; lastA = a; }
      const sz = state.size[i] * sizeBase;
      const jx = shimmer ? (Math.random() - 0.5) * shimmer : 0;
      const jy = shimmer ? (Math.random() - 0.5) * shimmer : 0;
      ctx.fillRect(state.x[i] - sz / 2 + jx, state.y[i] - sz / 2 + jy, sz, sz);
    }
    ctx.globalAlpha = 1;
    if (phase === "form" && (formedRatio(state, 8) > 0.93 || t > IMPACT.formS + 0.9)) {
      phase = "hold";
      phaseStart = now;
      hold = setTimeout(dissolve, IMPACT.holdMs);
    }
    if (phase === "dissolve" && !alive) { clear(); return; }
    raf = requestAnimationFrame(frame);
  };

  (async () => {
    try {
      const { points, step } = await wordPoints(impact.text, W, H);
      if (cancelled || !points.length) return;
      sizeBase = Math.max(2.2, step * 0.95);
      state = makeParticles(points, [0, 0], W, H, rng(hashStr(impact.text)));
      if (reducedMotion()) {          // sem animação: a palavra aparece pronta e some depois
        for (let i = 0; i < state.n; i++) { state.x[i] = state.tx[i]; state.y[i] = state.ty[i]; state.alpha[i] = 0.95; }
        phase = "hold";
        hold = setTimeout(() => { cancelled = true; clear(); }, IMPACT.holdMs);
        frame(performance.now());
        cancelAnimationFrame(raf);
        return;
      }
      last = phaseStart = performance.now();
      raf = requestAnimationFrame(frame);
    } catch (err) {
      console.warn("[JARVIS] palavra-impacto indisponível:", err?.message || err);
    }
  })();

  return { dissolve, cancel };
}

/**
 * Palavra-impacto: no ponto da fala em que o diretor a citou, ela se forma no meio da tela por
 * partículas, fica inteira por um instante e se desfaz (ou se desfaz já quando o trecho acaba).
 */
export default function ImpactWord({ beatKey, impact, progress, finished }) {
  const canvasRef = useRef(null);
  const run = useRef(null);
  const impactRef = useRef(impact);
  impactRef.current = impact;

  const fire = impact && (finished || progress >= impact.at) ? `${beatKey}|${impact.text}` : null;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (!fire) {              // trecho mudou (ou acabou): a palavra anterior se desfaz
      run.current?.dissolve();
      return;
    }
    run.current?.cancel();
    run.current = startRun(canvas, impactRef.current);
  }, [fire]);

  useEffect(() => () => run.current?.cancel(), []);

  return (
    <div className="im-layer" aria-hidden="true">
      <canvas ref={canvasRef} className="im-canvas" />
    </div>
  );
}
