import { API_URL } from "../lib/api.js";

export class ApiError extends Error {
  constructor(message, status = 0, code = "") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request(path, { method = "GET", token, body } = {}) {
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers: {
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { "X-Jarvis-Admin": token } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Sem conexão com o núcleo. Verifique se o backend está ativo.");
  }
  let data = null;
  try { data = await res.json(); } catch { /* corpo vazio */ }
  if (!res.ok) {
    const d = data?.detail;
    const message = typeof d === "string" ? d : d?.message || `Erro ${res.status}.`;
    throw new ApiError(message, res.status, d?.code || "");
  }
  return data;
}

// ---- público (HUD) ----
export const getConnections = () => request("/connections");
export const startAuth = (provider) => request(`/auth/${provider}/start`, { method: "POST" });

// ---- admin (token só fica na memória do React, nunca em localStorage) ----
export const adminStatus = (token) => request("/admin/status", { token });
export const adminSetup = (password) => request("/admin/setup", { method: "POST", body: { password } });
export const adminLogin = (password) => request("/admin/login", { method: "POST", body: { password } });
export const adminLogout = (token) => request("/admin/logout", { method: "POST", token });
export const adminOverview = (token) => request("/admin/overview", { token });
export const saveCredentials = (token, provider, client_id, client_secret) =>
  request(`/admin/providers/${provider}/credentials`, { method: "PUT", token, body: { client_id, client_secret: client_secret || null } });
export const saveScopes = (token, provider, scopes) =>
  request(`/admin/providers/${provider}/scopes`, { method: "PUT", token, body: { scopes } });
export const revokeConnection = (token, provider) =>
  request(`/connections/${provider}/revoke`, { method: "POST", token });
