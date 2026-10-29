import { useCallback, useEffect, useRef, useState } from "react";
import { getConnections, startAuth } from "./connectionsApi.js";

const POLL_MS = 1000;
const GIVE_UP_MS = 5 * 60 * 1000;

/**
 * Abre a autenticação num popup REAL do navegador (o Google não aceita login em
 * janela embutida) e espera o backend gravar o token.
 *
 * Detalhes importantes:
 * - window.open precisa rodar de forma síncrona dentro do clique; por isso o popup
 *   abre em branco e só depois recebe a URL.
 * - Não usamos popup.closed para decidir nada: páginas de login com COOP fazem o
 *   navegador reportar "closed" enquanto o usuário ainda está digitando.
 *   O sinal confiável é o backend: connected_at muda quando o token é salvo.
 */
export function useConnectFlow({ onConnected } = {}) {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");
  const timer = useRef(null);
  const onConnectedRef = useRef(onConnected);
  onConnectedRef.current = onConnected;

  const stop = useCallback(() => {
    clearInterval(timer.current);
    timer.current = null;
  }, []);

  useEffect(() => stop, [stop]);

  const snapshot = async (provider) => {
    const { connections } = await getConnections();
    return connections.find((c) => c.provider === provider) || null;
  };

  const connect = useCallback(async (provider) => {
    setError("");
    const popup = window.open("", "jarvis-auth", "popup=yes,width=520,height=740");
    if (!popup) {
      setError("O navegador bloqueou o popup. Permita popups para este site e tente de novo.");
      return;
    }
    setBusy(provider);
    let before = null;
    try {
      before = (await snapshot(provider))?.connected_at ?? null;
      const { authorize_url } = await startAuth(provider);
      popup.location.href = authorize_url;
    } catch (e) {
      popup.close();
      setBusy(null);
      setError(e.message);
      return;
    }
    stop();
    const startedAt = Date.now();
    timer.current = setInterval(async () => {
      if (Date.now() - startedAt > GIVE_UP_MS) {
        stop();
        setBusy(null);
        setError("Tempo esgotado sem concluir a autorização.");
        return;
      }
      try {
        const now = await snapshot(provider);
        if (now?.status === "connected" && now.connected_at !== before) {
          stop();
          setBusy(null);
          try { popup.close(); } catch { /* já fechou */ }
          onConnectedRef.current?.(provider);
        }
      } catch { /* backend ocupado: tenta no próximo ciclo */ }
    }, POLL_MS);
  }, [stop]);

  const cancel = useCallback(() => {
    stop();
    setBusy(null);
  }, [stop]);

  return { connect, cancel, busy, error, setError };
}
