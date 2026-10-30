// Cena mínima só com fala, usada quando o endpoint /v1/scene está indisponível.
export function simpleScene(answer, title = "Resposta") {
  const sentences = answer.trim().split(/(?<=[.!?])\s+/).filter(Boolean);
  const chunks = [];
  let cur = "";
  for (const s of sentences) {
    if (cur && cur.length + s.length > 260) { chunks.push(cur); cur = s; }
    else cur = `${cur} ${s}`.trim();
  }
  if (cur) chunks.push(cur);
  return {
    id: `simple-${Date.now()}`,
    title,
    kind: "concept",
    media: [], diagram: null, chart: null, geo: null,
    answer,
    beats: (chunks.length ? chunks : [answer]).slice(0, 8).map((say) => ({ say, layout: "title", caption: "", media: null, reveal: [], focus: [] })),
  };
}
