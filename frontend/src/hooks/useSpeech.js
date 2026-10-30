import { useCallback, useEffect, useRef, useState } from "react";

const SR = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);

// Quanto silêncio (ms) depois da última palavra antes de considerar que você terminou de falar.
// O navegador sozinho corta em ~1s, o que pegava só metade da frase.
const SILENCE_MS = 2200;
const MAX_LISTEN_MS = 45000;

export function useSpeech({ onFinalTranscript, onInterim, onListenEnd, onSpeakStart, onSpeakEnd, onError }) {
  const recRef = useRef(null);
  const tokenRef = useRef(0); // identifica a fala "viva"; callbacks de falas antigas são ignorados
  const [voice, setVoice] = useState(null);
  const supported = Boolean(SR);

  // Escolhe uma voz pt-BR assim que o navegador as carregar
  useEffect(() => {
    const pick = () => {
      const voices = window.speechSynthesis.getVoices();
      setVoice(voices.find((v) => v.lang === "pt-BR") || voices.find((v) => v.lang.startsWith("pt")) || null);
    };
    pick();
    window.speechSynthesis.onvoiceschanged = pick;
  }, []);

  const startListening = useCallback(() => {
    if (!SR) return onError?.("Reconhecimento de voz não suportado. Use Chrome ou Edge.");
    tokenRef.current++; // invalida qualquer fala/beat em andamento
    window.speechSynthesis.cancel();
    try { recRef.current?.abort(); } catch { /* já parado */ }

    const rec = new SR();
    rec.lang = "pt-BR";
    rec.continuous = true; // não encerra na primeira pausa
    rec.interimResults = true; // dá para ver/usar o que já foi entendido
    rec.maxAlternatives = 1;

    let finalText = "", interim = "", done = false, silence = null, maxTimer = null;
    const finish = () => {
      if (done) return;
      done = true;
      clearTimeout(silence);
      clearTimeout(maxTimer);
      const text = `${finalText} ${interim}`.replace(/\s+/g, " ").trim();
      if (text) onFinalTranscript?.(text);
      onListenEnd?.(Boolean(text));
    };
    const armSilence = () => {
      clearTimeout(silence);
      silence = setTimeout(() => { try { rec.stop(); } catch { finish(); } }, SILENCE_MS);
    };

    rec.onresult = (e) => {
      interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalText += `${r[0].transcript} `;
        else interim += r[0].transcript;
      }
      onInterim?.(`${finalText} ${interim}`.replace(/\s+/g, " ").trim());
      armSilence(); // cada palavra nova reinicia a contagem do silêncio
    };
    rec.onerror = (e) => {
      if (e.error === "no-speech" || e.error === "aborted") return; // silêncio ou cancelado: sem alarde
      console.error("[JARVIS] SpeechRecognition erro:", e.error);
      onError?.(`Erro no microfone: ${e.error}`);
    };
    rec.onend = finish;
    maxTimer = setTimeout(() => { try { rec.stop(); } catch { finish(); } }, MAX_LISTEN_MS);
    recRef.current = rec;
    rec.start();
  }, [onFinalTranscript, onInterim, onListenEnd, onError]);

  const stopListening = useCallback(() => recRef.current?.stop(), []);

  const speak = useCallback(
    (text) => {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "pt-BR";
      u.rate = 1.0;
      u.pitch = 0.8; // ligeiramente grave
      if (voice) u.voice = voice;
      u.onstart = () => onSpeakStart?.();
      u.onend = () => onSpeakEnd?.();
      u.onerror = () => onSpeakEnd?.();
      window.speechSynthesis.speak(u);
    },
    [voice, onSpeakStart, onSpeakEnd]
  );

  // Fala um trecho (beat) e avisa quando termina. Usado pelo palco para
  // sincronizar a imagem com a voz, trecho a trecho.
  //  - onStart: a voz começou
  //  - onProgress(0..1): quanto do trecho já foi falado (boundary real ou estimativa)
  //  - onEnd: a voz terminou (nunca dispara se o trecho foi cancelado/substituído)
  const speakBeat = useCallback(
    (text, { onStart, onProgress, onEnd } = {}) => {
      const synth = window.speechSynthesis;
      synth.cancel();
      const token = ++tokenRef.current;
      const alive = () => token === tokenRef.current;
      const estMs = Math.max(1400, text.length * 62);
      let started = false, boundarySeen = false, t0 = 0, tick = null, watchdog = null;
      const clear = () => { clearInterval(tick); clearTimeout(watchdog); };

      const u = new SpeechSynthesisUtterance(text);
      u.lang = "pt-BR";
      u.rate = 1.0;
      u.pitch = 0.8;
      if (voice) u.voice = voice;
      u.onstart = () => {
        if (!alive()) return;
        started = true;
        t0 = performance.now();
        clearTimeout(watchdog);
        onStart?.();
        tick = setInterval(() => {
          if (!boundarySeen && alive()) onProgress?.(Math.min(0.97, (performance.now() - t0) / estMs));
        }, 120);
      };
      u.onboundary = (e) => {
        if (!alive() || (e.name && e.name !== "word")) return;
        boundarySeen = true;
        onProgress?.(Math.min(0.99, e.charIndex / text.length));
      };
      u.onend = () => {
        clear();
        if (!alive()) return;
        onProgress?.(1);
        onEnd?.();
      };
      u.onerror = (e) => {
        clear();
        if (!alive() || e.error === "canceled" || e.error === "interrupted") return;
        console.warn("[JARVIS] Síntese de voz falhou:", e.error);
        onEnd?.();
      };
      // Se o navegador nunca iniciar a voz (sem vozes instaladas, p.ex.), o palco não trava.
      watchdog = setTimeout(() => {
        if (!alive() || started) return;
        synth.cancel();
        onStart?.();
        const t = performance.now();
        tick = setInterval(() => alive() && onProgress?.(Math.min(0.97, (performance.now() - t) / estMs)), 120);
        setTimeout(() => { clear(); if (alive()) { onProgress?.(1); onEnd?.(); } }, estMs);
      }, 4000);
      synth.speak(u);
    },
    [voice]
  );

  const cancelSpeech = useCallback(() => {
    tokenRef.current++;
    window.speechSynthesis.cancel();
  }, []);

  return { supported, startListening, stopListening, speak, speakBeat, cancelSpeech };
}
