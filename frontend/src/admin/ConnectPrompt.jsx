import React from "react";
import { useConnectFlow } from "./useConnectFlow.js";

/**
 * Cartão que aparece quando o JARVIS responde com actions:[{type:"connect"}].
 * O clique do usuário é obrigatório: é ele que permite abrir o popup sem bloqueio
 * e também confirma que a autorização foi pedida por você.
 */
export default function ConnectPrompt({ actions, onConnected, onDismiss, onOpenAdmin }) {
  const { connect, cancel, busy, error } = useConnectFlow({ onConnected });
  const items = (actions || []).filter((a) => a?.type === "connect");
  if (!items.length) return null;

  return (
    <div className="adm-connect" role="alertdialog" aria-label="Conexão necessária">
      <div className="adm-connect-head">
        <span className="adm-kicker">CONEXÃO NECESSÁRIA</span>
        <button className="adm-x" onClick={() => { cancel(); onDismiss?.(); }} aria-label="Dispensar">×</button>
      </div>
      {items.map((a) => (
        <div className="adm-connect-row" key={a.provider}>
          <div>
            <strong>{a.label || a.provider}</strong>
            <p>
              {!a.configured
                ? "Faltam o Client ID e o secret desta conta."
                : a.reason === "reconnect"
                  ? "A autorização expirou. Autorize novamente."
                  : "Autorize o acesso somente leitura na janela do navegador."}
            </p>
          </div>
          {!a.configured ? (
            <button className="adm-btn" onClick={onOpenAdmin}>Abrir administração</button>
          ) : busy === a.provider ? (
            <button className="adm-btn adm-btn-ghost" onClick={cancel}>Aguardando… cancelar</button>
          ) : (
            <button className="adm-btn adm-btn-primary" onClick={() => connect(a.provider)} disabled={Boolean(busy)}>
              {a.reason === "reconnect" ? "Reconectar" : "Conectar"}
            </button>
          )}
        </div>
      ))}
      {error && <p className="adm-error">{error}</p>}
      <p className="adm-hint">Administração: Alt + Shift + A</p>
    </div>
  );
}
