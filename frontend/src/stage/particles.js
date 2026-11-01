// Palavra que se forma de partículas: matemática pura (sem canvas nem React), para poder ser testada.

/** Pontos [x, y] onde há tinta (alpha alto) numa grade de `step` px. `data` é o RGBA de um ImageData. */
export function pointsFromAlpha(data, w, h, step = 4) {
  const pts = [];
  for (let y = 0; y < h; y += step) {
    for (let x = 0; x < w; x += step) {
      if (data[(y * w + x) * 4 + 3] > 128) pts.push([x, y]);
    }
  }
  return pts;
}

/** Escolhe a grade mais fina que não passe de `max` partículas (palavras grandes ganham grade maior). */
export function samplePoints(data, w, h, max = 3200, startStep = 3) {
  let step = startStep;
  let pts = pointsFromAlpha(data, w, h, step);
  while (pts.length > max && step < 14) {
    step += 1;
    pts = pointsFromAlpha(data, w, h, step);
  }
  return { points: pts, step };
}

/**
 * Cria as partículas. Elas nascem espalhadas numa roda em volta do palco, com um giro, e vão para os
 * pontos da palavra. Tudo em Float32Array para o laço de animação não gerar lixo.
 */
export function makeParticles(points, offset, W, H, rand) {
  const n = points.length;
  const s = {
    n,
    x: new Float32Array(n), y: new Float32Array(n),
    vx: new Float32Array(n), vy: new Float32Array(n),
    tx: new Float32Array(n), ty: new Float32Array(n),
    delay: new Float32Array(n), size: new Float32Array(n), alpha: new Float32Array(n),
    ox: new Float32Array(n), oy: new Float32Array(n), // direção de dispersão
  };
  const R = Math.max(W, H) * 0.62;
  for (let i = 0; i < n; i++) {
    s.tx[i] = points[i][0] + offset[0];
    s.ty[i] = points[i][1] + offset[1];
    const a = rand() * Math.PI * 2;
    const r = R * (0.55 + rand() * 0.55);
    s.x[i] = W / 2 + Math.cos(a) * r;
    s.y[i] = H / 2 + Math.sin(a) * r;
    // giro: velocidade perpendicular ao raio
    s.vx[i] = -Math.sin(a) * 260 * (0.5 + rand());
    s.vy[i] = Math.cos(a) * 260 * (0.5 + rand());
    s.delay[i] = rand() * 0.42;
    s.size[i] = 0.7 + rand() * 0.9;
    s.alpha[i] = 0;
    const d = rand() * Math.PI * 2;
    s.ox[i] = Math.cos(d);
    s.oy[i] = Math.sin(d);
  }
  return s;
}

/**
 * Um passo de animação. `t` = segundos desde o início da fase.
 * mode "form": mola até o alvo; "hold": treme de leve no lugar; "dissolve": dispersa e apaga.
 * Devolve true enquanto ainda há o que desenhar.
 */
export function stepParticles(s, dt, mode, t) {
  const k = 38;              // rigidez da mola
  const damp = Math.pow(0.0009, dt); // amortecimento independente do FPS
  let alive = false;
  for (let i = 0; i < s.n; i++) {
    if (mode === "dissolve") {
      const f = Math.max(0, 1 - t / 0.75);
      s.x[i] += s.ox[i] * (120 + s.size[i] * 140) * dt;
      s.y[i] += s.oy[i] * (120 + s.size[i] * 140) * dt - 40 * dt;
      s.alpha[i] = Math.min(s.alpha[i], f);
      if (s.alpha[i] > 0.01) alive = true;
      continue;
    }
    if (t < s.delay[i]) { alive = true; continue; }
    const ax = (s.tx[i] - s.x[i]) * k;
    const ay = (s.ty[i] - s.y[i]) * k;
    s.vx[i] = (s.vx[i] + ax * dt) * damp;
    s.vy[i] = (s.vy[i] + ay * dt) * damp;
    s.x[i] += s.vx[i] * dt;
    s.y[i] += s.vy[i] * dt;
    const target = mode === "hold" ? 0.95 : 1;
    s.alpha[i] += (target - s.alpha[i]) * Math.min(1, dt * 7);
    alive = true;
  }
  return alive;
}

/** Quanto das partículas já chegou perto do alvo (0..1): serve para saber quando a palavra "fechou". */
export function formedRatio(s, tol = 6) {
  if (!s.n) return 1;
  let ok = 0;
  for (let i = 0; i < s.n; i++) {
    if (Math.abs(s.x[i] - s.tx[i]) < tol && Math.abs(s.y[i] - s.ty[i]) < tol) ok++;
  }
  return ok / s.n;
}
