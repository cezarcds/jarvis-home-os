// Cliente das notícias. Ajuste API_URL se o seu api.js usa outra variável.
// Servido pelo backend (porta 8000): mesma origem, URL relativa. Em `npm run dev` (5173): aponta para o backend.
const API_URL =
  import.meta.env.VITE_API_URL ||
  (typeof window !== "undefined" && window.location.port === "5173" ? "http://localhost:8000" : "");

// Espelho simplificado da detecção do backend. Serve SÓ para mostrar "Buscando notícias…"
// enquanto espera; quem decide de verdade é o backend.
const NEWS_HINT =
  /(not[ií]cias?|manchetes?|[uú]ltimas? (sobre|do|da|de|no|na)|o que (aconteceu|rolou|houve|saiu)|me atualiza|bom dia)/i;
export const looksLikeNews = (text) => NEWS_HINT.test(text || "");

export async function askJarvisWithNews(messages) {
  const res = await fetch(`${API_URL}/v1/chat/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) {
    let detail = `Erro ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail?.message || body?.detail || detail;
    } catch {
      /* mantém o detalhe padrão */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const data = await res.json();
  const answer = data?.choices?.[0]?.message?.content?.trim();
  if (!answer) throw new Error("Resposta vazia do Jarvis.");
  return { answer, news: data.news || null };
}

export async function fetchTopics() {
  const res = await fetch(`${API_URL}/news/topics`);
  if (!res.ok) throw new Error("topics");
  return (await res.json()).topics;
}

export async function fetchHeadlines(topic = "mercado", limit = 4) {
  const res = await fetch(`${API_URL}/news/feed?topic=${encodeURIComponent(topic)}&limit=${limit}`);
  if (!res.ok) throw new Error(`feed ${res.status}`);
  return res.json();
}

export function timeAgo(iso) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const min = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (min < 1) return "agora";
  if (min < 60) return `há ${min} min`;
  const h = Math.round(min / 60);
  if (h < 24) return `há ${h} h`;
  const d = Math.round(h / 24);
  return d === 1 ? "ontem" : `há ${d} dias`;
}
