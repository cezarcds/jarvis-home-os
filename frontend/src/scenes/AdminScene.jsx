import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoutine, deleteRoutine, listRoutines, listTools, runRoutine, updateRoutine } from "../lib/api.js";

const EMPTY = () => ({
  id: "",
  nome: "",
  descricao: "",
  gatilhosTexto: "",
  tipo: "leitura",
  ativa: true,
  passos: [],
  tela: { cena: "briefing", titulo: "", blocos: [] },
  fala: { modo: "resumo", instrucao: "" },
});

const toDraft = (r) => ({
  ...r,
  gatilhosTexto: (r.gatilhos || []).join("\n"),
  tela: { cena: "briefing", titulo: r.tela?.titulo || "", blocos: r.tela?.blocos || [] },
  fala: { modo: r.fala?.modo || "resumo", instrucao: r.fala?.instrucao || "" },
});

const toPayload = (d) => ({
  id: d.id,
  nome: d.nome.trim(),
  descricao: d.descricao.trim(),
  gatilhos: d.gatilhosTexto.split("\n").map((g) => g.trim()).filter(Boolean),
  tipo: "leitura",
  ativa: d.ativa,
  passos: d.passos,
  tela: { cena: "briefing", titulo: d.tela.titulo.trim() || null, blocos: d.tela.blocos },
  fala: { modo: d.fala.modo, instrucao: d.fala.instrucao.trim() || null },
});

const input = "w-full bg-transparent border border-hud-cyan/30 px-2 py-1 text-xs outline-none focus:border-hud-cyan";
const btn = "px-3 py-1.5 border text-[11px] tracking-widest";

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-[10px] tracking-[0.25em] opacity-60 mb-1 uppercase">{label}</span>
      {children}
    </label>
  );
}

export default function AdminScene({ onClose, onRun, onToast }) {
  const [routines, setRoutines] = useState([]);
  const [tools, setTools] = useState([]);
  const [draft, setDraft] = useState(null);
  const [msg, setMsg] = useState({ text: "", warn: false });
  const [busy, setBusy] = useState(false);

  const flash = (text, warn = false) => setMsg({ text, warn });
  const toolMap = useMemo(() => Object.fromEntries(tools.map((t) => [t.nome, t])), [tools]);

  const reload = useCallback(async () => {
    try {
      const [rs, ts] = await Promise.all([listRoutines(), listTools()]);
      setRoutines(rs);
      setTools(ts);
    } catch (e) {
      flash(e.message, true);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const set = (patch) => setDraft((d) => ({ ...d, ...patch }));

  const addStep = (toolName) => {
    if (!toolName) return;
    const base = toolName.split(".").pop().replace(/[^a-z0-9_]/g, "_");
    const ids = new Set(draft.passos.map((s) => s.id));
    let id = base;
    for (let n = 2; ids.has(id); n++) id = `${base}_${n}`;
    set({ passos: [...draft.passos, { id, ferramenta: toolName, params: {} }] });
  };

  const setParam = (idx, name, value) => {
    const passos = draft.passos.map((s, i) => {
      if (i !== idx) return s;
      const params = { ...s.params };
      if (value === "" || value === null) delete params[name];
      else params[name] = value;
      return { ...s, params };
    });
    set({ passos });
  };

  const removeStep = (idx) => {
    const gone = draft.passos[idx].id;
    set({
      passos: draft.passos.filter((_, i) => i !== idx),
      tela: { ...draft.tela, blocos: draft.tela.blocos.filter((b) => b !== gone) },
    });
  };

  const move = (idx, dir) => {
    const j = idx + dir;
    if (j < 0 || j >= draft.passos.length) return;
    const passos = [...draft.passos];
    [passos[idx], passos[j]] = [passos[j], passos[idx]];
    set({ passos });
  };

  const showing = (id) => draft.tela.blocos.length === 0 || draft.tela.blocos.includes(id);
  const toggleBlock = (id) => {
    const current = draft.tela.blocos.length === 0 ? draft.passos.map((s) => s.id) : draft.tela.blocos;
    const next = current.includes(id) ? current.filter((b) => b !== id) : [...current, id];
    const ordered = draft.passos.map((s) => s.id).filter((x) => next.includes(x));
    set({ tela: { ...draft.tela, blocos: ordered.length === draft.passos.length ? [] : ordered } });
  };

  const save = async () => {
    if (!draft.nome.trim()) return flash("Dê um nome à rotina.", true);
    if (draft.passos.length === 0) return flash("Adicione pelo menos um passo.", true);
    setBusy(true);
    try {
      const payload = toPayload(draft);
      const saved = draft.id ? await updateRoutine(draft.id, payload) : await createRoutine(payload);
      setDraft(toDraft(saved));
      flash(`Rotina “${saved.nome}” salva.`);
      onToast?.(`Rotina salva: ${saved.nome}`);
      await reload();
    } catch (e) {
      flash(e.message, true);
    } finally {
      setBusy(false);
    }
  };

  const run = async () => {
    if (!draft.id) return flash("Salve a rotina antes de executar.", true);
    setBusy(true);
    flash("Executando…");
    try {
      onRun?.(await runRoutine(draft.id));
    } catch (e) {
      flash(e.message, true);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!draft.id || !window.confirm(`Apagar a rotina “${draft.nome}”?`)) return;
    try {
      await deleteRoutine(draft.id);
      setDraft(null);
      flash("Rotina apagada.");
      await reload();
    } catch (e) {
      flash(e.message, true);
    }
  };

  const toggleActive = async (r) => {
    try {
      await updateRoutine(r.id, { ...r, ativa: !r.ativa });
      await reload();
      if (draft?.id === r.id) set({ ativa: !r.ativa });
    } catch (e) {
      flash(e.message, true);
    }
  };

  return (
    <div className="blueprint h-full w-full flex flex-col text-hud-cyan" style={{ backgroundColor: "#030712" }}>
      <header className="px-8 py-4 flex items-center justify-between border-b border-hud-cyan/20">
        <div>
          <div className="text-[10px] tracking-[0.5em] opacity-60">JARVIS // ADMIN</div>
          <h1 className="text-2xl font-light">Rotinas</h1>
        </div>
        <div className="flex items-center gap-4">
          <span className={`text-xs ${msg.warn ? "text-hud-amber" : "opacity-70"}`}>{msg.text}</span>
          <button onClick={onClose} className={`${btn} border-hud-cyan/40 hover:bg-hud-cyan/10`}>FECHAR ✕</button>
        </div>
      </header>

      <div className="flex-1 min-h-0 flex">
        <aside className="w-72 shrink-0 border-r border-hud-cyan/20 p-4 overflow-y-auto space-y-2">
          <button onClick={() => setDraft(EMPTY())} className={`${btn} w-full border-hud-cyan hover:bg-hud-cyan/15`}>
            + NOVA ROTINA
          </button>
          {routines.map((r) => (
            <div
              key={r.id}
              className={`panel p-3 cursor-pointer ${draft?.id === r.id ? "border-hud-cyan" : ""} ${r.ativa ? "" : "opacity-50"}`}
              onClick={() => setDraft(toDraft(r))}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-cyan-100">{r.nome}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); toggleActive(r); }}
                  className="text-[10px] tracking-widest opacity-70 hover:opacity-100"
                  title="Ativar/desativar"
                >
                  {r.ativa ? "● ATIVA" : "○ OFF"}
                </button>
              </div>
              <div className="text-[11px] opacity-60 mt-1 line-clamp-2">{r.gatilhos.map((g) => `“${g}”`).join(" ")}</div>
            </div>
          ))}
        </aside>

        <main className="flex-1 min-w-0 overflow-y-auto p-6">
          {!draft ? (
            <div className="text-sm opacity-60 max-w-md">
              Selecione uma rotina ou crie uma nova. Você também pode pedir por voz: “Jarvis, crie uma rotina chamada
              fim de expediente que mostra a agenda de amanhã e os emails para responder”.
            </div>
          ) : (
            <div className="max-w-3xl space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <Field label="Nome"><input className={input} value={draft.nome} onChange={(e) => set({ nome: e.target.value })} /></Field>
                <Field label="Título da tela"><input className={input} value={draft.tela.titulo} placeholder="(igual ao nome)" onChange={(e) => set({ tela: { ...draft.tela, titulo: e.target.value } })} /></Field>
              </div>
              <Field label="Descrição (ajuda o Jarvis a entender quando usar)">
                <input className={input} value={draft.descricao} onChange={(e) => set({ descricao: e.target.value })} />
              </Field>
              <Field label="Gatilhos — uma frase por linha (frases com o mesmo sentido também funcionam)">
                <textarea rows={4} className={input} value={draft.gatilhosTexto} onChange={(e) => set({ gatilhosTexto: e.target.value })} />
              </Field>

              <div>
                <div className="text-[10px] tracking-[0.25em] opacity-60 mb-2 uppercase">Passos (fontes consultadas)</div>
                <div className="space-y-2">
                  {draft.passos.map((s, i) => {
                    const t = toolMap[s.ferramenta];
                    return (
                      <div key={s.id} className="panel p-3 space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="text-sm">
                            <span className="text-hud-cyan">{t?.rotulo || s.ferramenta}</span>
                            <span className="opacity-50 text-xs"> · {s.ferramenta} · id {s.id}</span>
                            {t && !t.disponivel && <span className="text-hud-amber text-xs"> · indisponível: {t.motivo}</span>}
                          </div>
                          <div className="flex gap-2 text-xs">
                            <button onClick={() => move(i, -1)} className="opacity-60 hover:opacity-100">↑</button>
                            <button onClick={() => move(i, 1)} className="opacity-60 hover:opacity-100">↓</button>
                            <button onClick={() => removeStep(i)} className="text-hud-amber">remover</button>
                          </div>
                        </div>
                        {t && t.params.length > 0 && (
                          <div className="grid grid-cols-3 gap-3">
                            {t.params.map((p) => (
                              <Field key={p.nome} label={p.nome}>
                                {p.tipo === "bool" ? (
                                  <input type="checkbox" checked={Boolean(s.params[p.nome] ?? p.default)} onChange={(e) => setParam(i, p.nome, e.target.checked)} />
                                ) : (
                                  <input
                                    className={input}
                                    type={p.tipo === "int" || p.tipo === "float" ? "number" : "text"}
                                    min={p.minimo ?? undefined}
                                    max={p.maximo ?? undefined}
                                    value={s.params[p.nome] ?? ""}
                                    placeholder={p.default != null ? String(p.default) : ""}
                                    title={p.descricao}
                                    onChange={(e) => setParam(i, p.nome, e.target.value)}
                                  />
                                )}
                              </Field>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                  <select className={input} value="" onChange={(e) => addStep(e.target.value)}>
                    <option value="" className="bg-black">+ adicionar passo…</option>
                    {tools.map((t) => (
                      <option key={t.nome} value={t.nome} className="bg-black">
                        {t.rotulo} ({t.nome}){t.disponivel ? "" : " — não configurada"}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {draft.passos.length > 0 && (
                <div>
                  <div className="text-[10px] tracking-[0.25em] opacity-60 mb-2 uppercase">Mostrar na tela</div>
                  <div className="flex flex-wrap gap-4 text-xs">
                    {draft.passos.map((s) => (
                      <label key={s.id} className="flex items-center gap-2">
                        <input type="checkbox" checked={showing(s.id)} onChange={() => toggleBlock(s.id)} />
                        {toolMap[s.ferramenta]?.rotulo || s.ferramenta}
                      </label>
                    ))}
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <Field label="Fala">
                  <select className={input} value={draft.fala.modo} onChange={(e) => set({ fala: { ...draft.fala, modo: e.target.value } })}>
                    <option value="resumo" className="bg-black">Resumo por IA (envia assunto/remetente ao provedor)</option>
                    <option value="template" className="bg-black">Frases fixas (nenhum dado vai para a IA)</option>
                    <option value="nenhuma" className="bg-black">Só tela, sem falar</option>
                  </select>
                </Field>
                <Field label="Instrução extra para o resumo (opcional)">
                  <input className={input} value={draft.fala.instrucao} onChange={(e) => set({ fala: { ...draft.fala, instrucao: e.target.value } })} />
                </Field>
              </div>

              <div className="flex gap-3 pt-2">
                <button disabled={busy} onClick={save} className={`${btn} border-hud-cyan hover:bg-hud-cyan/15`}>SALVAR</button>
                <button disabled={busy} onClick={run} className={`${btn} border-hud-cyan/50 hover:bg-hud-cyan/10`}>EXECUTAR AGORA</button>
                {draft.id && <button onClick={remove} className={`${btn} border-hud-amber/60 text-hud-amber hover:bg-hud-amber/10 ml-auto`}>APAGAR</button>}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
