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
