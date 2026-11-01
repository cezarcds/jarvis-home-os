import React, { useCallback, useEffect, useState } from "react";
import {
  ativarTarefa, estadoTarefas, executarTarefa, getTarefa, importarTarefas, listTarefas,
  liberarItem, pausarAgendador, retomarAgendador, simularTarefa,
} from "../lib/api.js";

// Tela mínima das tarefas do agente (Fase 2): estado do agendador, lista, última execução,
// "rodar agora", "simular" (dry-run) e liberar item incerto. A criação é por JSON em
// ~/.jarvis/tarefas/*.json (por conversa só na Fase 5).
const COR = {
  ok: "text-emerald-300", falhou: "text-red-300", pausada: "text-hud-amber", cancelada: "text-hud-amber",
  interrompida: "text-hud-amber", perdida: "text-hud-amber", em_andamento: "text-hud-cyan",
};
const fmt = (ts) => (ts ? new Date(ts * 1000).toLocaleString("pt-BR") : "—");

export default function TarefasPanel({ onClose }) {
  const [tarefas, setTarefas] = useState([]);
  const [estado, setEstado] = useState(null);
  const [aberta, setAberta] = useState(null); // detalhe da tarefa aberta
  const [plano, setPlano] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const recarregar = useCallback(async () => {
    try {
      const [l, e] = await Promise.all([listTarefas(), estadoTarefas()]);
      setTarefas(l.tarefas);
      setEstado(e);
    } catch (err) {
      setMsg(err.message);
    }
  }, []);

  useEffect(() => {
    recarregar();
    const t = setInterval(recarregar, 5000);
    return () => clearInterval(t);
  }, [recarregar]);

  const agir = async (fn, ok) => {
    setBusy(true);
    setMsg("");
    try {
      await fn();
      if (ok) setMsg(ok);
      await recarregar();
    } catch (err) {
      setMsg(err.message);
    } finally {
      setBusy(false);
    }
  };

  const abrir = (id) => agir(async () => { setAberta(await getTarefa(id)); setPlano(null); });

  return (
    <div className="fixed inset-0 z-40 bg-black/70 flex items-center justify-center p-6" role="dialog" aria-label="Tarefas">
      <div className="panel w-full max-w-3xl max-h-[85vh] overflow-auto p-5 text-sm space-y-4">
        <div className="flex items-center justify-between text-xs tracking-[0.3em]">
          <span>TAREFAS DO AGENTE</span>
          <button onClick={onClose} className="opacity-70 hover:opacity-100" title="Fechar">FECHAR ×</button>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className={estado?.pausado ? "text-hud-amber" : "text-emerald-300"}>
            ● Agendador {estado ? (estado.pausado ? "PAUSADO" : "ativo") : "…"}
          </span>
          {estado?.pausado ? (
            <button disabled={busy} onClick={() => agir(retomarAgendador, "Agendador retomado.")} className="px-2 py-1 border border-hud-cyan/50">RETOMAR</button>
          ) : (
            <button disabled={busy} onClick={() => agir(pausarAgendador, "Agendador pausado.")} className="px-2 py-1 border border-hud-amber/60 text-hud-amber">PAUSAR</button>
          )}
          <button disabled={busy} onClick={() => agir(async () => { const r = await importarTarefas(); setMsg(`${r.resultados.filter((x) => x.ok).length} importada(s) de ${r.pasta}` + r.resultados.filter((x) => !x.ok).map((x) => ` · ${x.arquivo}: ${x.erro}`).join("")); })} className="px-2 py-1 border border-hud-cyan/40">
            IMPORTAR JSON
          </button>
          {msg && <span className="opacity-80 break-words">{msg}</span>}
        </div>

        {tarefas.length === 0 && (
          <div className="opacity-60 text-xs">
            Nenhuma tarefa. Coloque um arquivo .json em <code>~/.jarvis/tarefas/</code> e use IMPORTAR JSON.
          </div>
        )}

        <ul className="space-y-2">
          {tarefas.map((t) => (
            <li key={t.id} className="border border-hud-cyan/25 p-3 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button onClick={() => abrir(t.id)} className="text-left">
                  <span className="text-cyan-100">{t.nome}</span>{" "}
                  <span className="opacity-50 text-xs">({t.id})</span>
                </button>
                <div className="flex gap-2 text-xs">
                  <button disabled={busy} onClick={() => agir(async () => setPlano({ id: t.id, ...(await simularTarefa(t.id)) }))} className="px-2 py-1 border border-hud-cyan/40">SIMULAR</button>
                  <button disabled={busy || !t.contrato_aprovado} title={t.contrato_aprovado ? "" : "Contrato não aprovado"} onClick={() => agir(() => executarTarefa(t.id), "Execução iniciada.")} className="px-2 py-1 border border-hud-cyan disabled:opacity-30">RODAR AGORA</button>
                  <button disabled={busy} onClick={() => agir(() => ativarTarefa(t.id, !t.ativa))} className="px-2 py-1 border border-hud-cyan/40">{t.ativa ? "DESATIVAR" : "ATIVAR"}</button>
                </div>
              </div>
              <div className="text-xs opacity-70 flex flex-wrap gap-x-4">
                <span>{t.agenda ? `${t.agenda.cron} (${t.agenda.fuso})` : "só manual"}</span>
                <span>{t.ativa ? "ativa" : "inativa"}</span>
                <span className={t.contrato_aprovado ? "" : "text-hud-amber"}>{t.contrato_aprovado ? "contrato aprovado" : "contrato NÃO aprovado"}</span>
              </div>
              {t.ultima_execucao && (
                <div className="text-xs">
                  Última: <span className={COR[t.ultima_execucao.estado] || ""}>{t.ultima_execucao.estado}</span> · {fmt(t.ultima_execucao.inicio)}
                  {t.ultima_execucao.motivo && <div className="opacity-80 break-words">{t.ultima_execucao.motivo}</div>}
                </div>
              )}
            </li>
          ))}
        </ul>

        {plano && (
          <div className="border border-hud-cyan/40 p-3 space-y-2 text-xs">
            <div className="tracking-[0.2em]">SIMULAÇÃO · {plano.id} — {plano.rodaria_sem_pausar ? "rodaria até o fim" : "PARARIA (veja abaixo)"}</div>
            {plano.passos.map((p) => (
              <div key={p.id} className={p.permitido && !p.exige_confirmacao ? "" : "text-hud-amber"}>
                {p.id} → {p.ferramenta} (nível {p.nivel ?? "?"}){p.motivo ? ` — ${p.motivo}` : ""}
              </div>
            ))}
            <div className="opacity-60">{plano.aviso}</div>
          </div>
        )}

        {aberta && (
          <div className="border border-hud-cyan/25 p-3 space-y-2 text-xs">
            <div className="tracking-[0.2em]">ITENS JÁ ENVIADOS / INCERTOS · {aberta.id}</div>
            {aberta.itens.length === 0 && <div className="opacity-60">Nenhum item registrado.</div>}
            {aberta.itens.map((i) => (
              <div key={i.chave} className="flex items-center justify-between gap-2">
                <span className="break-all">
                  <span className={i.estado === "ok" ? "text-emerald-300" : "text-hud-amber"}>{i.estado === "ok" ? "enviado" : "INCERTO"}</span>{" "}
                  {i.chave.split(":").slice(2).join(":")}
                </span>
                {i.estado !== "ok" && (
                  <button disabled={busy} onClick={() => agir(async () => { await liberarItem(aberta.id, i.chave); setAberta(await getTarefa(aberta.id)); }, "Item liberado.")} className="px-2 py-1 border border-hud-amber/60 text-hud-amber shrink-0" title="Só depois de conferir que NÃO foi enviado">
                    LIBERAR
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
