export async function resolveMedia(m, { searchAll, preload }) {
  const data = (await searchAll(m.query, m.kind)) || {};
  const candidates = [data.item, ...(data.alternatives || [])].filter(Boolean);

  for (const c of candidates) {
    if (c.kind !== "image") return { status: "ready", item: { ...c, caption: m.caption } };

    for (const url of new Set([c.url, c.fallback_url].filter(Boolean))) {
      try {
        await preload(url);
        return { status: "ready", item: { ...c, url, caption: m.caption } };
      } catch {
        /* tenta a próxima URL / o próximo candidato */
      }
    }
  }
  return { status: "none", item: null, tried: data.tried || [] };
}