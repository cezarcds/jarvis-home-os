import { useCallback, useEffect, useRef, useState } from "react";

const SR = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);

export function useSpeech({ onFinalTranscript, onSpeakStart, onSpeakEnd, onError }) {
  const recRef = useRef(null);
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
    window.speechSynthesis.cancel();
    const rec = new SR();
    rec.lang = "pt-BR";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => onFinalTranscript?.(e.results[0][0].transcript);
    rec.onerror = (e) => {
      console.error("[JARVIS] SpeechRecognition erro:", e.error);
      onError?.(`Erro no microfone: ${e.error}`);
    };
    recRef.current = rec;
    rec.start();
  }, [onFinalTranscript, onError]);

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

  return { supported, startListening, stopListening, speak };
}
