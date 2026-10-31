import { useCallback, useEffect, useRef, useState } from "react";

const PER_PAGE = 3;     // cartões por vez
const STEP_MS = 6000;   // troca de "trecho"
const OUT_MS = 450;     // duração da saída
const LINGER_MS = 9000; // quanto fica depois que o Jarvis termina de falar
const MAX_MS = 60000;   // teto de segurança (ex.: sem voz)

/**
 * Controla os cartões de notícia: entram, trocam de trecho em trecho e saem.
 * news: payload do backend ({items, kind, topic...}) ou null.
 * speaking: true enquanto o Jarvis fala (os cartões ficam até ele terminar + LINGER_MS).
 */
export function useNewsMural(news, { speaking, onDismiss } = {}) {
  const items = news?.items ?? [];
  const pages = Math.max(1, Math.ceil(items.length / PER_PAGE));
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const [phase, setPhase] = useState("in");
  const wasSpeaking = useRef(false);
  const timers = useRef([]);
  const dismissRef = useRef(onDismiss);
  dismissRef.current = onDismiss;

  const later = (fn, ms) => {
    const id = setTimeout(fn, ms);
    timers.current.push(id);
    return id;
  };

  const close = useCallback(() => {
    setPhase("out");
    later(() => {
      setOpen(false);
      dismissRef.current?.();
    }, OUT_MS);
  }, []);

  // Chegou notícia nova (ou limpou): reinicia.
  useEffect(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    wasSpeaking.current = false;
    setPage(0);
    setPhase("in");
    setOpen(items.length > 0);
    if (items.length > 0) later(close, MAX_MS);
    return () => timers.current.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [news]);

  // Troca de trecho.
  useEffect(() => {
    if (!open || pages < 2) return undefined;
    const id = setInterval(() => {
      setPhase("out");
      later(() => {
        setPage((p) => (p + 1) % pages);
        setPhase("in");
      }, OUT_MS);
    }, STEP_MS);
    return () => clearInterval(id);
  }, [open, pages]);

  // Fecha um tempo depois que o Jarvis para de falar.
  useEffect(() => {
    if (!open) return undefined;
    if (speaking) {
      wasSpeaking.current = true;
      return undefined;
    }
    if (!wasSpeaking.current) return undefined;
    const id = setTimeout(close, LINGER_MS);
    return () => clearTimeout(id);
  }, [open, speaking, close]);

  const start = page * PER_PAGE;
  const visible = open ? items.slice(start, start + PER_PAGE) : [];
  const nextStart = ((page + 1) % pages) * PER_PAGE;
  const upcoming = open && pages > 1 ? items.slice(nextStart, nextStart + 2) : [];

  return { visible, upcoming, phase, page, pages, close };
}
