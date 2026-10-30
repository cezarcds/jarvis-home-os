import { useEffect, useState } from "react";
import { searchMedia } from "../lib/api.js";

const PRELOAD_TIMEOUT = 9000;
const FIRST_MEDIA_WAIT = 3200; // quanto esperar a 1ª imagem antes de começar a narrar

function preloadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const t = setTimeout(() => reject(new Error("timeout")), PRELOAD_TIMEOUT);
    img.onload = () => { clearTimeout(t); resolve(img); };
    img.onerror = () => { clearTimeout(t); reject(new Error("erro")); };
    img.src = url;
  });
}

/**
 * Busca em paralelo a mídia pedida pelo diretor. Cada item vira
 * { status: "loading" | "ready" | "none", item }.
 * `ready` indica que a narração já pode começar.
 */
export function useMediaResolver(scene) {
  // O estado carrega o id da cena a que pertence: evita usar resultados da cena anterior.
  const [state, setState] = useState({ sceneId: null, entries: {}, waited: false });

  useEffect(() => {
    if (!scene?.media?.length) {
      setState({ sceneId: scene?.id ?? null, entries: {}, waited: false });
      return;
    }
    let cancelled = false;
    const sceneId = scene.id;
    const init = {};
    scene.media.forEach((m) => (init[m.id] = { status: "loading", item: null }));
    setState({ sceneId, entries: init, waited: false });
    const waitTimer = setTimeout(
      () => !cancelled && setState((s) => (s.sceneId === sceneId ? { ...s, waited: true } : s)),
      FIRST_MEDIA_WAIT,
    );

    scene.media.forEach(async (m) => {
      let result = { status: "none", item: null };
      try {
        const item = await searchMedia(m.query, m.kind);
        if (item) {
          if (item.kind === "image") await preloadImage(item.url);
          result = { status: "ready", item: { ...item, caption: m.caption } };
        }
      } catch (err) {
        console.warn("[JARVIS] Mídia indisponível:", m.query, err.message);
      }
      if (!cancelled) {
        setState((s) => (s.sceneId === sceneId ? { ...s, entries: { ...s.entries, [m.id]: result } } : s));
      }
    });

    return () => { cancelled = true; clearTimeout(waitTimer); };
  }, [scene?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!scene) return { entries: {}, ready: false };
  if (!scene.media?.length) return { entries: {}, ready: true };
  if (state.sceneId !== scene.id) return { entries: {}, ready: false };
  const first = state.entries[scene.media[0].id];
  return { entries: state.entries, ready: state.waited || (first && first.status !== "loading") };
}
