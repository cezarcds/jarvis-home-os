// Token de sessão do backend (Fase 0). O backend recusa rotas sem ele (401).
// - HUD compilado: o backend embute <meta name="jarvis-token"> no index.html.
// - Modo dev (vite, porta 5173), ou depois de um 401 (token trocado): o token vem de
//   GET /session/bootstrap, que só responde a navegador (Origin da allowlist ou mesma origem).
// O token nunca vai para localStorage nem para serviços externos: use authFetch só com o backend.
import { API_URL } from "./api.js";

export const TOKEN_HEADER = "X-Jarvis-Token";

let tokenPromise = null;
let useMeta = true; // o meta vale só até o primeiro 401; depois ele pode estar velho

function metaToken() {
  return document.querySelector('meta[name="jarvis-token"]')?.content || "";
}

async function loadToken() {
  const fromMeta = useMeta ? metaToken() : "";
  if (fromMeta) return fromMeta;
  let res;
  try {
    res = await fetch(`${API_URL}/session/bootstrap`);
  } catch {
    throw new Error("Sem conexão com o núcleo. Verifique se o backend está ativo.");
  }
  if (!res.ok) throw new Error(`O núcleo recusou a sessão (erro ${res.status}).`);
  return (await res.json()).token;
}

export function getToken() {
  if (!tokenPromise) {
    tokenPromise = loadToken().catch((err) => {
      tokenPromise = null; // tenta de novo na próxima chamada
      throw err;
    });
  }
  return tokenPromise;
}

export function resetToken() {
  tokenPromise = null;
  useMeta = false;
}

// fetch para o backend com o token. Se vier 401 (token trocado ou backend recriou o arquivo),
// busca o token de novo (pelo bootstrap, já que o meta é de quando a página carregou) e tenta
// mais uma vez.
export async function authFetch(url, options = {}) {
  const send = async () => {
    const token = await getToken();
    return fetch(url, { ...options, headers: { ...(options.headers || {}), [TOKEN_HEADER]: token } });
  };
  let res = await send();
  if (res.status === 401) {
    resetToken();
    res = await send();
  }
  return res;
}
