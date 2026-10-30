// Projeção Web Mercator + utilitários do mapa panorâmico ("Olho de Deus").
export const TILE = 256;
export const MAX_LAT = 85.0511;

export function project(lat, lon, zoom) {
  const scale = TILE * Math.pow(2, zoom);
  const x = ((lon + 180) / 360) * scale;
  const s = Math.sin((Math.max(-MAX_LAT, Math.min(MAX_LAT, lat)) * Math.PI) / 180);
  const y = (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * scale;
  return { x, y };
}

export function unproject(x, y, zoom) {
  const scale = TILE * Math.pow(2, zoom);
  const lon = (x / scale) * 360 - 180;
  const n = Math.PI - (2 * Math.PI * y) / scale;
  const lat = (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
  return { lat, lon };
}

/** Menor zoom que deixa todos os pontos visíveis no viewport. */
export function fitView(points, width, height, pad = 120) {
  if (!points.length) return { lat: 15, lon: 0, zoom: 1.6 };
  if (points.length === 1) return { lat: points[0].lat, lon: points[0].lon, zoom: 5 };
  const lats = points.map((p) => p.lat), lons = points.map((p) => p.lon);
  const bounds = { n: Math.max(...lats), s: Math.min(...lats), w: Math.min(...lons), e: Math.max(...lons) };
  let zoom = 1;
  for (let z = 1; z <= 12; z += 0.25) {
    const a = project(bounds.n, bounds.w, z), b = project(bounds.s, bounds.e, z);
    if (Math.abs(b.x - a.x) <= width - pad * 2 && Math.abs(b.y - a.y) <= height - pad * 2) zoom = z;
    else break;
  }
  const c = unproject(
    (project(bounds.n, bounds.w, zoom).x + project(bounds.s, bounds.e, zoom).x) / 2,
    (project(bounds.n, bounds.w, zoom).y + project(bounds.s, bounds.e, zoom).y) / 2,
    zoom,
  );
  return { lat: c.lat, lon: c.lon, zoom: Math.min(zoom, 8) };
}

export const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

/** Voo da câmera: interpola e "afasta" no meio da viagem em deslocamentos longos. */
export function flyFrame(from, to, t) {
  const e = easeInOut(t);
  const dist = Math.hypot(to.lat - from.lat, to.lon - from.lon);
  const bump = Math.min(2.2, dist / 40) * Math.sin(Math.PI * t);
  return {
    lat: from.lat + (to.lat - from.lat) * e,
    lon: from.lon + (to.lon - from.lon) * e,
    zoom: Math.max(1, from.zoom + (to.zoom - from.zoom) * e - bump),
  };
}

/** Caminho curvo (arco) entre dois pontos na tela. */
export function arcPath(a, b, lift = 0.22) {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
  const dx = b.x - a.x, dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const cx = mx - (dy / len) * len * lift, cy = my + (dx / len) * len * lift - len * lift * 0.5;
  return { d: `M${a.x},${a.y} Q${cx},${cy} ${b.x},${b.y}`, mid: { x: (a.x + 2 * cx + b.x) / 4, y: (a.y + 2 * cy + b.y) / 4 } };
}

/** Desloca o centro da câmera para baixo (em px), deixando o conteúdo na parte livre acima da legenda. */
export function shiftCenter(view, px) {
  const c = project(view.lat, view.lon, view.zoom);
  const n = unproject(c.x, c.y + px, view.zoom);
  return { ...view, lat: n.lat, lon: n.lon };
}
