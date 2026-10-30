const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function askJarvis(messages) {
  console.log("[JARVIS] POST /v1/chat/completions", messages);
  let res;
  try {
    res = await fetch(`${API_URL}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });
  } catch (err) {
    console.error("[JARVIS] Falha de rede (backend ligado na porta 8000?)", err);
    throw new Error("Sem conexão com o núcleo. Verifique se o backend está ativo.");
  }

  if (!res.ok) {
    const body = await res.text();
    console.error("[JARVIS] Erro HTTP", res.status, body);
    throw new Error(`Núcleo respondeu com erro ${res.status}.`);
  }

  const data = await res.json();
  console.log("[JARVIS] Resposta", data);
  const text = data?.choices?.[0]?.message?.content?.trim();
  if (!text) throw new Error("Resposta vazia do núcleo.");
  return text;
}

// Meteorologia em tempo real (Open-Meteo, sem chave). Coordenadas padrão: São Paulo.
export async function fetchWeather(lat = -23.55, lon = -46.63) {
  const url =
    `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}` +
    `&current=temperature_2m,relative_humidity_2m,wind_speed_10m&timezone=auto`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Clima HTTP ${res.status}`);
  const data = await res.json();
  return data.current;
}

// ---------- Assistente com rotinas ----------

async function request(path, options) {
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch (err) {
    console.error("[JARVIS] Falha de rede", path, err);
    throw new Error("Sem conexão com o núcleo. Verifique se o backend está ativo.");
  }
  if (!res.ok) {
    const body = await res.text();
    console.error("[JARVIS] Erro HTTP", res.status, path, body);
    let detail = "";
    try {
      const j = JSON.parse(body);
      if (typeof j.detail === "string") detail = j.detail;
      else if (Array.isArray(j.detail)) detail = j.detail.map((d) => d.msg).join("; ");
      else detail = j.detail?.message || "";
    } catch {
      /* corpo não era JSON */
    }
    throw new Error(detail || `Núcleo respondeu com erro ${res.status}.`);
  }
  return res.json();
}

// Voz/texto -> { kind, text, scene: { titulo, blocos, rotina } | null }
export function askAssistant(messages, sessionId) {
  console.log("[JARVIS] POST /v1/assistant", messages.at(-1));
  return request("/v1/assistant", {
    method: "POST",
    body: JSON.stringify({ messages, session_id: sessionId }),
  }).then((data) => {
    console.log("[JARVIS] Resposta", data);
    return data;
  });
}

export const listRoutines = () => request("/v1/routines");
export const listTools = () => request("/v1/tools");
export const createRoutine = (r) => request("/v1/routines", { method: "POST", body: JSON.stringify(r) });
export const updateRoutine = (id, r) => request(`/v1/routines/${id}`, { method: "PUT", body: JSON.stringify(r) });
export const deleteRoutine = (id) => request(`/v1/routines/${id}`, { method: "DELETE" });
export const runRoutine = (id) => request(`/v1/routines/${id}/run`, { method: "POST" });

// ---------- Motor de cenas (diretor visual) ----------

export async function askScene(messages, previous = null) {
  let res;
  try {
    res = await fetch(`${API_URL}/v1/scene`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, previous }),
    });
  } catch (err) {
    console.error("[JARVIS] Falha de rede (/v1/scene)", err);
    throw new Error("Sem conexão com o núcleo. Verifique se o backend está ativo.");
  }
  if (!res.ok) {
    console.error(`[JARVIS] Erro HTTP ${res.status}`, await res.text());
    throw new Error(`Núcleo respondeu com erro ${res.status}.`);
  }
  const scene = await res.json();
  if (!scene?.beats?.length) throw new Error("A cena veio vazia.");
  return scene;
}

// Resposta completa: { item, alternatives: [...], tried: [...] }.
// "alternatives" são candidatos reserva; "tried" só vem quando nada foi achado (diagnóstico).
export async function searchMediaAll(query, kind = "image") {
  const res = await fetch(`${API_URL}/v1/media/search?q=${encodeURIComponent(query)}&kind=${kind}`);
  if (!res.ok) throw new Error(`Mídia HTTP ${res.status}`);
  return res.json();
}

export async function searchMedia(query, kind = "image") {
  return (await searchMediaAll(query, kind)).item || null;
}