import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  adminLogin, adminLogout, adminOverview, adminSetup, adminStatus,
  revokeConnection, saveCredentials, saveScopes,
} from "./connectionsApi.js";
import { useConnectFlow } from "./useConnectFlow.js";

const STATUS_LABEL = { connected: "CONECTADO", reconnect: "RECONECTAR", disconnected: "DESCONECTADO" };
const fmt = (sec) => (sec ? new Date(sec * 1000).toLocaleString("pt-BR") : "—");
const shortScope = (s) => s.replace("https://www.googleapis.com/auth/", "");

function ProviderCard({ provider: p, token, reload, flow, setNotice, setError, onUnauthorized }) {
  const [clientId, setClientId] = useState("");
  const [secret, setSecret] = useState("");
  const [extra, setExtra] = useState(() => p.optional_scopes.filter((o) => o.enabled).map((o) => o.scope));
  const [confirming, setConfirming] = useState(false);
  const [copied, setCopied] = useState(false);

  const guard = async (fn, okMsg) => {
    setError(""); setNotice("");
    try { await fn(); if (okMsg) setNotice(okMsg); await reload(); }
    catch (e) { if (e.status === 401) onUnauthorized(); else setError(e.message); }
  };

  const toggle = (scope) => setExtra((cur) => (cur.includes(scope) ? cur.filter((s) => s !== scope) : [...cur, scope]));
  const copyRedirect = async () => {
    try { await navigator.clipboard.writeText(p.redirect_uri); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* sem permissão */ }
  };

  return (
    <article className="adm-card">
      <header className="adm-card-head">
        <div>
          <h3>{p.label}</h3>
          <span className={`adm-chip adm-${p.status}`}>{STATUS_LABEL[p.status] || p.status}</span>
        </div>
        <div className="adm-actions">
          {p.configured && (
            <button className="adm-btn adm-btn-primary" disabled={Boolean(flow.busy)} onClick={() => flow.connect(p.id)}>
              {flow.busy === p.id ? "Aguardando…" : p.status === "connected" ? "Reautorizar" : p.status === "reconnect" ? "Reconectar" : "Conectar"}
            </button>
          )}
          {flow.busy === p.id && <button className="adm-btn adm-btn-ghost" onClick={flow.cancel}>Cancelar</button>}
          {p.status !== "disconnected" && (confirming ? (
            <button className="adm-btn adm-btn-danger" onClick={() => guard(() => revokeConnection(token, p.id), "Conexão revogada e token apagado.")}>
              Confirmar revogação
            </button>
          ) : (
            <button className="adm-btn adm-btn-ghost" onClick={() => setConfirming(true)}>Revogar</button>
          ))}
        </div>
      </header>

      <dl className="adm-meta">
        <div><dt>Conta</dt><dd>{p.account || "—"}</dd></div>
        <div><dt>Conectada em</dt><dd>{fmt(p.connected_at)}</dd></div>
        <div><dt>Última sincronização</dt><dd>{fmt(p.last_sync)}</dd></div>
        <div><dt>Credenciais</dt><dd>{p.configured ? `${p.client_id_masked} (${p.credentials_source === "env" ? ".env" : "painel"})` : "não configuradas"}</dd></div>
      </dl>

      <details className="adm-details" open={!p.configured}>
        <summary>Credenciais OAuth</summary>
        <p className="adm-hint">
          No Google Cloud, crie um cliente OAuth do tipo “Aplicativo da Web” e cadastre este URI de redirecionamento:
        </p>
        <div className="adm-copy">
          <code>{p.redirect_uri}</code>
          <button className="adm-btn adm-btn-ghost" onClick={copyRedirect}>{copied ? "Copiado" : "Copiar"}</button>
        </div>
        <label>Client ID<input value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder={p.client_id_masked || "xxxx.apps.googleusercontent.com"} autoComplete="off" spellCheck="false" /></label>
        <label>Client secret<input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder={p.configured ? "(deixe em branco para remover)" : "GOCSPX-…"} autoComplete="new-password" /></label>
        <button className="adm-btn" disabled={clientId.trim().length < 5}
          onClick={() => guard(async () => { await saveCredentials(token, p.id, clientId.trim(), secret.trim()); setClientId(""); setSecret(""); }, "Credenciais salvas (criptografadas).")}>
          Salvar credenciais
        </button>
      </details>

      <details className="adm-details">
        <summary>Escopos ({p.granted_scopes.length || p.base_scopes.length})</summary>
        <p className="adm-hint">Somente leitura. Escopos extras só valem depois de reautorizar a conta.</p>
        <ul className="adm-scopes">
          {(p.granted_scopes.length ? p.granted_scopes : p.base_scopes).map((s) => <li key={s}><code>{shortScope(s)}</code></li>)}
        </ul>
        {p.optional_scopes.length > 0 && (
          <>
            <div className="adm-checks">
              {p.optional_scopes.map((o) => (
                <label key={o.scope} className="adm-check">
                  <input type="checkbox" checked={extra.includes(o.scope)} onChange={() => toggle(o.scope)} /> {o.label}
                </label>
              ))}
            </div>
            <button className="adm-btn" onClick={() => guard(() => saveScopes(token, p.id, extra), "Escopos salvos. Reautorize a conta para aplicar.")}>Salvar escopos</button>
          </>
        )}
      </details>
    </article>
  );
}

export default function AdminPanel({ open, onClose }) {
  const [phase, setPhase] = useState("loading"); // loading | setup | login | ready | error
  const [token, setToken] = useState(null);
  const [overview, setOverview] = useState(null);
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [attempt, setAttempt] = useState(0);
  const tokenRef = useRef(null);
  tokenRef.current = token;

  const load = useCallback(async (tk) => {
    const data = await adminOverview(tk);
    setOverview(data);
    setPhase("ready");
  }, []);

  const unauthorized = useCallback(() => {
    setToken(null); setOverview(null); setPhase("login"); setError("Sessão expirada. Entre novamente.");
  }, []);

  const reload = useCallback(async () => {
    try { await load(tokenRef.current); } catch (e) { if (e.status === 401) unauthorized(); else setError(e.message); }
  }, [load, unauthorized]);

  const flow = useConnectFlow({ onConnected: () => { setNotice("Conta conectada."); reload(); } });

  useEffect(() => {
    if (!open) return;
    setError(""); setNotice(""); setPw(""); setPw2("");
    (async () => {
      try {
        const s = await adminStatus(tokenRef.current);
        if (s.authenticated && tokenRef.current) await load(tokenRef.current);
        else setPhase(s.password_set ? "login" : "setup");
      } catch (e) { setPhase("error"); setError(e.message); }
    })();
  }, [open, load, attempt]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const submitSetup = async (e) => {
    e.preventDefault(); setError("");
    if (pw !== pw2) return setError("As senhas não conferem.");
    try { const { token: tk } = await adminSetup(pw); setToken(tk); setPw(""); setPw2(""); await load(tk); }
    catch (err) { setError(err.message); }
  };
  const submitLogin = async (e) => {
    e.preventDefault(); setError("");
    try { const { token: tk } = await adminLogin(pw); setToken(tk); setPw(""); await load(tk); }
    catch (err) { setError(err.message); }
  };
  const logout = async () => {
    try { await adminLogout(token); } catch { /* sessão já inválida */ }
    setToken(null); setOverview(null); setPhase("login"); setNotice("");
  };

  return (
    <div className="adm-overlay" role="dialog" aria-modal="true" aria-label="Administração do JARVIS" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className="adm-panel">
        <header className="adm-top">
          <div>
            <span className="adm-kicker">JARVIS // ADMINISTRAÇÃO</span>
            <h2>Conexões</h2>
          </div>
          <div className="adm-actions">
            {phase === "ready" && <button className="adm-btn adm-btn-ghost" onClick={logout}>Sair</button>}
            <button className="adm-btn adm-btn-ghost" onClick={onClose}>Fechar · Esc</button>
          </div>
        </header>

        {error && <p className="adm-error" role="alert">{error}</p>}
        {notice && <p className="adm-ok" role="status">{notice}</p>}
        {flow.error && <p className="adm-error" role="alert">{flow.error}</p>}

        {phase === "loading" && <p className="adm-hint">Carregando…</p>}
        {phase === "error" && <button className="adm-btn" onClick={() => { setPhase("loading"); setAttempt((a) => a + 1); }}>Tentar de novo</button>}

        {phase === "setup" && (
          <form className="adm-form" onSubmit={submitSetup}>
            <p>Primeiro acesso: defina uma senha local para proteger esta tela (mínimo 8 caracteres).</p>
            <label>Nova senha<input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus autoComplete="new-password" /></label>
            <label>Repita a senha<input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} autoComplete="new-password" /></label>
            <button className="adm-btn adm-btn-primary" type="submit" disabled={pw.length < 8}>Definir senha</button>
          </form>
        )}

        {phase === "login" && (
          <form className="adm-form" onSubmit={submitLogin}>
            <label>Senha<input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus autoComplete="current-password" /></label>
            <button className="adm-btn adm-btn-primary" type="submit" disabled={!pw}>Entrar</button>
          </form>
        )}

        {phase === "ready" && overview && (
          <>
            {overview.providers.map((p) => (
              <ProviderCard key={p.id} provider={p} token={token} reload={reload} flow={flow}
                setNotice={setNotice} setError={setError} onUnauthorized={unauthorized} />
            ))}
            <section className="adm-audit">
              <h3>Registro recente</h3>
              {overview.audit.length === 0 ? <p className="adm-hint">Nada registrado ainda.</p> : (
                <ul>{overview.audit.slice(0, 10).map((a, i) => (
                  <li key={i}><time>{fmt(a.ts)}</time> <code>{a.event}</code> {a.detail}</li>
                ))}</ul>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
