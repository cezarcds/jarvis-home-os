import React, { useState } from "react";

const COLORS = { STANDBY: "#06b6d4", LISTENING: "#f59e0b", PROCESSING: "#06b6d4", SPEAKING: "#22d3ee" };

function Block({ title, children, className = "" }) {
  return (
    <section className={`panel p-4 ${className}`}>
      <div className="text-[10px] tracking-[0.3em] text-hud-cyan/70 mb-3 uppercase">// {title}</div>
      {children}
    </section>
  );
}

function relTime(iso) {
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `${min} min`;
  if (min < 1440) return `${Math.round(min / 60)} h`;
  return `${Math.round(min / 1440)} d`;
}

function Agenda({ data }) {
  if (data.vazio && data.dias.length <= 1)
    return <div className="text-sm text-cyan-100/80">Agenda livre. Nenhum compromisso.</div>;
  return (
    <div className="space-y-4">
      {data.dias.map((d) => (
        <div key={d.data}>
          {data.dias.length > 1 && <div className="text-xs text-hud-cyan/70 mb-1">{d.rotulo}</div>}
          {d.eventos.length === 0 ? (
            <div className="text-xs opacity-50">livre</div>
          ) : (
            <ul className="space-y-2">
              {d.eventos.map((e, i) => (
                <li key={i} className="flex gap-3 text-sm">
                  <span className="w-24 shrink-0 tabular-nums text-hud-cyan">
                    {e.dia_todo ? "dia todo" : `${e.inicio}–${e.fim}`}
                  </span>
                  <span className="text-cyan-100">
                    {e.titulo}
                    {e.local && <span className="block text-xs opacity-60">{e.local}</span>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

function Emails({ data }) {
  return (
    <div>
      {data.total_nao_lidos != null && (
        <div className="text-xs text-hud-amber mb-2">{data.total_nao_lidos} não lidos na caixa de entrada</div>
      )}
      {data.itens.length === 0 ? (
        <div className="text-sm text-cyan-100/80">Nada por aqui.</div>
      ) : (
        <ul className="space-y-3">
          {data.itens.map((m) => (
            <li key={m.id} className="text-sm">
              <div className="flex justify-between gap-3">
                <a href={m.link} target="_blank" rel="noopener noreferrer" className="text-cyan-100 hover:underline">
                  {m.nao_lido && <span className="text-hud-amber">● </span>}
                  {m.de}
                </a>
                <span className="text-xs opacity-50 shrink-0">{relTime(m.data)}</span>
              </div>
              <div className="text-hud-cyan">{m.assunto}</div>
              {m.trecho && <div className="text-xs opacity-60 line-clamp-1">{m.trecho}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Clima({ data }) {
  return (
    <div className="flex items-center gap-5">
      <div className="text-5xl font-light text-hud-cyan">{data.temperatura}°</div>
      <div className="text-sm space-y-0.5">
        <div className="text-cyan-100 capitalize">{data.descricao}</div>
        <div className="opacity-70">
          Máx {data.maxima}° · Mín {data.minima}° · Chuva {data.chuva_prob}%
        </div>
        <div className="opacity-70">
          Umidade {data.umidade}% · Vento {data.vento} km/h
        </div>
      </div>
    </div>
  );
}

function Metricas({ data }) {
  return (
    <div className="grid grid-cols-3 gap-3">
      {data.itens.map((m) => (
        <div key={m.rotulo}>
          <div className="text-3xl font-light text-hud-cyan tabular-nums">{m.valor.toLocaleString("pt-BR")}</div>
          <div className="text-xs opacity-70">{m.rotulo}</div>
          {m.variacao_pct != null && (
            <div className={`text-xs ${m.variacao_pct >= 0 ? "text-cyan-300" : "text-hud-amber"}`}>
              {m.variacao_pct >= 0 ? "▲" : "▼"} {Math.abs(m.variacao_pct)}%
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Rascunho({ data, onSend }) {
  const r = data.rotina;
  const verbo = { criar: "Criar", atualizar: "Atualizar", apagar: "Apagar", ativar: "Ativar", desativar: "Desativar" }[data.acao];
  return (
    <div className="text-sm space-y-3">
      <div className="text-hud-amber">
        {verbo} {r ? "rotina" : `rotina “${data.alvo}”`}
      </div>
      {r && (
        <>
          <div className="text-lg text-hud-cyan">{r.nome}</div>
          <div>
            <span className="opacity-60">Gatilhos: </span>
            {r.gatilhos.map((g) => `“${g}”`).join(", ")}
          </div>
          <div>
            <span className="opacity-60">Consulta: </span>
            {data.passos.join(" → ")}
          </div>
        </>
      )}
      {data.faltando?.length > 0 && (
        <div className="text-hud-amber text-xs">Ainda sem integração: {data.faltando.join(", ")}</div>
      )}
      <div className="flex gap-3 pt-1">
        <button onClick={() => onSend("confirma")} className="px-4 py-1.5 border border-hud-cyan text-hud-cyan hover:bg-hud-cyan/15 text-xs tracking-widest">
          CONFIRMAR
        </button>
        <button onClick={() => onSend("cancela")} className="px-4 py-1.5 border border-hud-amber/60 text-hud-amber hover:bg-hud-amber/10 text-xs tracking-widest">
          CANCELAR
        </button>
      </div>
    </div>
  );
}

function Rotinas({ data }) {
  return (
    <ul className="space-y-2 text-sm">
      {data.itens.map((r) => (
        <li key={r.id} className={r.ativa ? "" : "opacity-40"}>
          <span className="text-hud-cyan">{r.nome}</span>
          <span className="opacity-60"> — {r.gatilhos.map((g) => `“${g}”`).join(", ")}</span>
        </li>
      ))}
    </ul>
  );
}

function renderBlock(b, onSend) {
  switch (b.type) {
    case "agenda": return <Agenda data={b.data} />;
    case "emails": return <Emails data={b.data} />;
    case "clima": return <Clima data={b.data} />;
    case "metricas": return <Metricas data={b.data} />;
    case "rascunho": return <Rascunho data={b.data} onSend={onSend} />;
    case "rotinas": return <Rotinas data={b.data} />;
    case "rotina": return <div className="text-sm text-cyan-100">Rotina “{b.data.rotina.nome}” pronta para uso.</div>;
    case "erro": return <div className="text-sm text-hud-amber">{b.data.mensagem}</div>;
    case "texto": return <div className="text-sm text-cyan-100">{b.data.texto}</div>;
    default: return <pre className="text-xs opacity-70">{JSON.stringify(b.data, null, 2)}</pre>;
  }
}

const WIDE = new Set(["agenda", "rascunho"]);

export default function BriefingScene({ data, status, userText, reply, onMic, onClose, onSend }) {
  const [typed, setTyped] = useState("");
  const color = COLORS[status] || COLORS.STANDBY;
  const hoje = new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" });

  const submit = (e) => {
    e.preventDefault();
    if (!typed.trim()) return;
    onSend(typed.trim());
    setTyped("");
  };

  return (
    <div className="blueprint h-full w-full flex flex-col text-hud-cyan" style={{ backgroundColor: "#030712" }}>
      <header className="px-8 py-4 flex items-end justify-between border-b border-hud-cyan/20">
        <div>
          <div className="text-[10px] tracking-[0.5em] opacity-60">JARVIS // {data?.rotina?.nome?.toUpperCase() || "BRIEFING"}</div>
          <h1 className="text-3xl font-light" style={{ textShadow: "0 0 18px rgba(6,182,212,0.5)" }}>
            {data?.titulo || "Briefing"}
          </h1>
        </div>
        <div className="flex items-center gap-6">
          <span className="text-xs tracking-[0.3em] opacity-70 capitalize">{hoje}</span>
          <button onClick={onClose} className="text-xs tracking-[0.3em] border border-hud-cyan/40 px-3 py-1 hover:bg-hud-cyan/10">
            FECHAR ✕
          </button>
        </div>
      </header>

      <main className="flex-1 min-h-0 overflow-y-auto px-8 py-6">
        <div className="grid gap-5 max-w-6xl mx-auto" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
          {(data?.blocos || []).map((b) => (
            <Block key={b.id || b.type} title={b.title} className={WIDE.has(b.type) ? "md:col-span-2" : ""}>
              {renderBlock(b, onSend)}
            </Block>
          ))}
        </div>
      </main>

      <footer className="px-8 py-4 border-t border-hud-cyan/20 flex items-center gap-5">
        <button
          onClick={onMic}
          aria-label="Falar"
          className="shrink-0 rounded-full flex items-center justify-center text-[9px] tracking-widest transition"
          style={{
            width: 64, height: 64, border: `2px solid ${color}`, color,
            background: `radial-gradient(circle, ${color}33, transparent 70%)`,
            boxShadow: `0 0 ${status === "STANDBY" ? 14 : 30}px ${color}`,
            animation: status === "LISTENING" || status === "SPEAKING" ? "pulse-ring 0.9s ease-in-out infinite" : "none",
          }}
        >
          {status === "STANDBY" ? "FALAR" : status}
        </button>
        <div className="flex-1 min-w-0 text-sm space-y-1">
          {userText && <div className="text-hud-cyan/60 truncate">&gt; {userText}</div>}
          <div className="text-cyan-100 line-clamp-2">{reply}</div>
        </div>
        <form onSubmit={submit} className="shrink-0">
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder="ou digite um comando…"
            className="w-64 bg-transparent border border-hud-cyan/30 px-3 py-2 text-xs outline-none focus:border-hud-cyan"
          />
        </form>
      </footer>
    </div>
  );
}
