import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const GAP_MS = 380; // respiro entre um beat e o próximo
const FRESH = { id: null, index: -1, progress: 0, playing: false, finished: false };

/**
 * Toca o roteiro de uma cena: fala cada beat e avança quando a voz termina.
 *
 * Todo o estado de reprodução carrega o id da cena a que pertence. Se a cena
 * muda, o estado antigo é ignorado na mesma renderização (nunca se usa o
 * índice de uma cena em outra, que tem outro número de beats).
 *
 * O que está "revelado" e em foco é DERIVADO do índice do beat, então pular
 * para frente/trás sempre deixa o palco consistente.
 */
export function useScenePlayer({ scene, ready, speakBeat, cancelSpeech, onFinish }) {
  const [state, setState] = useState(FRESH);
  const st = scene && state.id === scene.id ? state : FRESH;

  const runRef = useRef(0);
  const gapRef = useRef(null);
  const sceneRef = useRef(scene);
  const speakRef = useRef(speakBeat);
  const cancelRef = useRef(cancelSpeech);
  const finishRef = useRef(onFinish);
  sceneRef.current = scene;
  speakRef.current = speakBeat;
  cancelRef.current = cancelSpeech;
  finishRef.current = onFinish;

  const stop = useCallback(() => {
    runRef.current++;
    clearTimeout(gapRef.current);
    cancelRef.current?.();
  }, []);

  const play = useCallback((i) => {
    const sc = sceneRef.current;
    if (!sc) return;
    if (i >= sc.beats.length) {
      setState((s) => (s.id === sc.id ? { ...s, playing: false, finished: true, progress: 1 } : s));
      finishRef.current?.();
      return;
    }
    clearTimeout(gapRef.current);
    const run = ++runRef.current;
    setState({ id: sc.id, index: i, progress: 0, playing: true, finished: false });
    speakRef.current(sc.beats[i].say, {
      onProgress: (p) => {
        if (run === runRef.current) setState((s) => (s.id === sc.id && s.index === i ? { ...s, progress: p } : s));
      },
      onEnd: () => {
        if (run !== runRef.current) return;
        gapRef.current = setTimeout(() => run === runRef.current && play(i + 1), GAP_MS);
      },
    });
  }, []);

  // Cena nova (ou removida): corta a fala da anterior.
  useEffect(() => {
    stop();
  }, [scene?.id, stop]);

  // Quando a mídia inicial estiver pronta, começa a narrar.
  useEffect(() => {
    if (scene && ready && st.index === -1 && !st.finished) play(0);
  }, [scene, ready, st.index, st.finished, play]);

  useEffect(() => stop, [stop]);

  const jump = useCallback((i) => {
    const sc = sceneRef.current;
    if (!sc) return;
    play(Math.max(0, Math.min(sc.beats.length - 1, i)));
  }, [play]);

  const pause = useCallback(() => {
    stop();
    setState((s) => (s.id === sceneRef.current?.id ? { ...s, playing: false } : s));
  }, [stop]);

  const toggle = useCallback(() => {
    if (st.playing) pause();
    else play(st.finished ? 0 : Math.max(0, st.index));
  }, [st.playing, st.finished, st.index, play, pause]);

  const beat = scene && st.index >= 0 ? scene.beats[st.index] || null : null;

  const { revealed, focus } = useMemo(() => {
    const set = new Set();
    if (scene && st.index >= 0) {
      for (let i = 0; i <= st.index && i < scene.beats.length; i++) scene.beats[i].reveal.forEach((id) => set.add(id));
    }
    // Depois do último beat, nada fica "apagado": tudo vira explorável.
    return { revealed: set, focus: st.finished ? [] : beat?.focus || [] };
  }, [scene, st.index, st.finished, beat]);

  return {
    index: st.index,
    beat,
    progress: st.progress,
    playing: st.playing,
    finished: st.finished,
    revealed,
    focus,
    total: scene?.beats.length || 0,
    jump,
    next: () => jump(st.index + 1),
    prev: () => jump(st.index - 1),
    toggle,
    pause,
    stop,
  };
}
