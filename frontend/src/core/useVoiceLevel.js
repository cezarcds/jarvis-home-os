import { useEffect, useRef } from "react";
import { rmsLevel } from "./levelMath.js";

// VITE_CORE_MIC=off desliga a análise do microfone (o núcleo usa um pulso simulado).
const MIC_ENABLED = String(import.meta.env.VITE_CORE_MIC || "on").toLowerCase() !== "off";

/**
 * Mede a intensidade da sua voz enquanto `active` for verdadeiro (status LISTENING).
 * Devolve um ref (não causa re-render): `ref.current` é 0..1, ou null quando não há sinal
 * (ainda abrindo, sem permissão, ou desligado). O microfone é solto assim que `active` cai.
 */
export function useVoiceLevel(active) {
  const levelRef = useRef(null);

  useEffect(() => {
    levelRef.current = null;
    if (!active || !MIC_ENABLED || !navigator.mediaDevices?.getUserMedia) return undefined;

    let stopped = false;
    let stream = null;
    let ctx = null;
    let raf = 0;

    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
        });
        if (stopped) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        const AC = window.AudioContext || window.webkitAudioContext;
        ctx = new AC();
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        ctx.createMediaStreamSource(stream).connect(analyser);
        const buf = new Uint8Array(analyser.fftSize);
        const tick = () => {
          analyser.getByteTimeDomainData(buf);
          levelRef.current = rmsLevel(buf);
          raf = requestAnimationFrame(tick);
        };
        tick();
      } catch (err) {
        // Sem permissão ou sem microfone: o núcleo segue com o pulso simulado.
        console.warn("[JARVIS] Análise de voz indisponível:", err?.name || err);
        levelRef.current = null;
      }
    })();

    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
      ctx?.close?.().catch(() => {});
      levelRef.current = null;
    };
  }, [active]);

  return levelRef;
}
