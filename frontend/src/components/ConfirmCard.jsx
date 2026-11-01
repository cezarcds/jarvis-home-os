import React, { useEffect, useState } from "react";

// Cartão de confirmação de uma ação pendente (Fase 1). Mostra o texto EXATO que o backend vai
// executar e uma contagem regressiva; depois de `expira_em` o backend já descartou a ação.
// A confirmação é só por clique: voz sozinha não confirma.
export default function ConfirmCard({ pendente, onConfirm, onDeny, busy }) {
  const [resta, setResta] = useState(() => segundos(pendente));

  useEffect(() => {
    setResta(segundos(pendente));
    const t = setInterval(() => setResta(segundos(pendente)), 250);
    return () => clearInterval(t);
  }, [pendente]);

  if (!pendente) return null;
  const expirou = resta <= 0;
  return (
    <div
      role="alertdialog"
      aria-label="Confirmar ação"
      className={`panel p-4 w-full max-w-2xl text-sm space-y-3 border ${
        pendente.forte ? "border-hud-amber" : "border-hud-cyan/60"
      }`}
    >
      <div className={`tracking-[0.25em] text-xs ${pendente.forte ? "text-hud-amber" : "text-hud-cyan"}`}>
        {pendente.forte ? "CONFIRMAÇÃO FORTE" : "CONFIRMAR AÇÃO"} · {pendente.ferramenta}
      </div>
      <div className="text-cyan-100 leading-relaxed whitespace-pre-wrap break-words">{pendente.texto}</div>
      <div className="flex items-center justify-between text-xs">
        <span className="opacity-60">{expirou ? "Expirou." : `Expira em ${Math.ceil(resta)} s`}</span>
        <div className="flex gap-3">
          <button
            onClick={onDeny}
            disabled={busy}
            className="px-3 py-1 border border-hud-cyan/40 tracking-[0.2em] opacity-80 hover:opacity-100 disabled:opacity-30"
          >
            NEGAR
          </button>
          <button
            onClick={onConfirm}
            disabled={busy || expirou}
            className={`px-3 py-1 border tracking-[0.2em] disabled:opacity-30 ${
              pendente.forte ? "border-hud-amber text-hud-amber" : "border-hud-cyan text-hud-cyan"
            }`}
          >
            CONFIRMAR
          </button>
        </div>
      </div>
    </div>
  );
}

function segundos(p) {
  return p ? p.expira_em - Date.now() / 1000 : 0;
}
