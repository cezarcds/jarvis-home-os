import { useEffect, useRef, useState } from "react";

/**
 * Guarda por um instante o que estava na tela no trecho anterior, para sair com animação
 * em vez de sumir de repente. `items` é o que está visível agora; `key` identifica o trecho.
 * O relógio da saída não pode depender de re-renderizações (o progresso da fala re-renderiza o
 * tempo todo), por isso o timer fica numa ref.
 */
export function useLeaving(key, items, ms = 600) {
  const [leaving, setLeaving] = useState(null);
  const prev = useRef({ key, items });
  const timer = useRef(null);
  useEffect(() => {
    if (prev.current.key !== key) {
      const old = prev.current;
      prev.current = { key, items };
      clearTimeout(timer.current);
      if (old.items.length) {
        setLeaving(old);
        timer.current = setTimeout(() => setLeaving(null), ms);
      } else {
        setLeaving(null);
      }
    } else {
      prev.current = { key, items };
    }
  }, [key, items, ms]);
  useEffect(() => () => clearTimeout(timer.current), []);
  return leaving;
}
