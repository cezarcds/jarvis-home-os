import React, { useEffect, useRef } from "react";

const CYAN = "6,182,212";
const AMBER = "245,158,11";

// Gera pontos de uma curva fechada/aberta já em coordenadas 3D (raio 1).
function meridian(lonRad, n = 48) {
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const lat = -Math.PI / 2 + (Math.PI * i) / n;
    pts.push([Math.cos(lat) * Math.cos(lonRad), Math.sin(lat), Math.cos(lat) * Math.sin(lonRad)]);
  }
  return pts;
}
function parallel(latRad, n = 64) {
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const lon = (Math.PI * 2 * i) / n;
    pts.push([Math.cos(latRad) * Math.cos(lon), Math.sin(latRad), Math.cos(latRad) * Math.sin(lon)]);
  }
  return pts;
}
function ring(radius, n = 96) {
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const a = (Math.PI * 2 * i) / n;
    pts.push([Math.cos(a) * radius, 0, Math.sin(a) * radius]);
  }
  return pts;
}

function rotate(p, ax, ay, az = 0) {
  const [x0, y0, z0] = p;
  // Y
  let x = x0 * Math.cos(ay) + z0 * Math.sin(ay);
  let z = -x0 * Math.sin(ay) + z0 * Math.cos(ay);
  let y = y0;
  // X
  const y1 = y * Math.cos(ax) - z * Math.sin(ax);
  const z1 = y * Math.sin(ax) + z * Math.cos(ax);
  y = y1;
  z = z1;
  // Z
  const x2 = x * Math.cos(az) - y * Math.sin(az);
  const y2 = x * Math.sin(az) + y * Math.cos(az);
  return [x2, y2, z];
}

export default function HologramCanvas() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const speed = reduced ? 0.15 : 1;

    // Geometria estática
    const meridians = Array.from({ length: 12 }, (_, i) => meridian((Math.PI * i) / 12 * 2));
    const parallels = [-60, -40, -20, 0, 20, 40, 60].map((d) => parallel((d * Math.PI) / 180));
    const rings = [
      { pts: ring(1.35), tiltX: 1.1, tiltZ: 0.2, spin: 0.25, amber: false },
      { pts: ring(1.6), tiltX: 0.5, tiltZ: -0.5, spin: -0.18, amber: false },
      { pts: ring(1.85), tiltX: 1.4, tiltZ: 0.9, spin: 0.1, amber: false },
    ];
    const particles = Array.from({ length: 220 }, () => {
      const u = Math.random() * 2 - 1;
      const a = Math.random() * Math.PI * 2;
      const r = 1.05 + Math.random() * 0.9;
      const s = Math.sqrt(1 - u * u);
      return { p: [s * Math.cos(a) * r, u * r, s * Math.sin(a) * r], tw: Math.random() * 6 };
    });

    let w = 0;
    let h = 0;
    let dpr = 1;

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const project = (p, R, cx, cy) => {
      const f = 3.2;
      const k = f / (f - p[2]);
      return [cx + p[0] * R * k, cy + p[1] * R * k, p[2]];
    };

    const drawPoly = (pts, rotFn, R, cx, cy, rgb, baseAlpha, width) => {
      ctx.lineWidth = width;
      let prev = null;
      for (const p of pts) {
        const q = project(rotFn(p), R, cx, cy);
        if (prev) {
          const depth = (q[2] + prev[2]) / 2; // ~ -1..1
          const a = baseAlpha * (0.25 + 0.75 * ((depth + 1.5) / 3));
          ctx.strokeStyle = `rgba(${rgb},${a.toFixed(3)})`;
          ctx.beginPath();
          ctx.moveTo(prev[0], prev[1]);
          ctx.lineTo(q[0], q[1]);
          ctx.stroke();
        }
        prev = q;
      }
    };

    let raf;
    const start = performance.now();

    const frame = (now) => {
      const t = ((now - start) / 1000) * speed;
      ctx.clearRect(0, 0, w, h);

      const cx = w / 2;
      const cy = h * 0.46;
      const R = Math.min(w, h) * 0.26;
      const ay = t * 0.35;
      const ax = 0.35 + Math.sin(t * 0.2) * 0.08;

      // Halo central
      const g = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 1.9);
      g.addColorStop(0, `rgba(${CYAN},0.14)`);
      g.addColorStop(1, `rgba(${CYAN},0)`);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);

      // Globo wireframe
      const globeRot = (p) => rotate(p, ax, ay);
      meridians.forEach((m) => drawPoly(m, globeRot, R, cx, cy, CYAN, 0.55, 1));
      parallels.forEach((m) => drawPoly(m, globeRot, R, cx, cy, CYAN, 0.45, 1));

      // Anéis orbitais
      rings.forEach((r, i) => {
        const rot = (p) => rotate(p, r.tiltX + Math.sin(t * 0.15 + i) * 0.05, t * r.spin, r.tiltZ);
        drawPoly(r.pts, rot, R, cx, cy, CYAN, 0.5, 1);
      });

      // Satélites âmbar no primeiro e terceiro anel
      [0, 2].forEach((idx, n) => {
        const r = rings[idx];
        const a = t * (0.9 - n * 0.5) + n * 2;
        const rad = idx === 0 ? 1.35 : 1.85;
        const p0 = [Math.cos(a) * rad, 0, Math.sin(a) * rad];
        const p = rotate(p0, r.tiltX + Math.sin(t * 0.15 + idx) * 0.05, t * r.spin, r.tiltZ);
        const q = project(p, R, cx, cy);
        ctx.fillStyle = `rgba(${AMBER},0.95)`;
        ctx.shadowColor = `rgba(${AMBER},0.9)`;
        ctx.shadowBlur = 12;
        ctx.beginPath();
        ctx.arc(q[0], q[1], 3.2, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
      });

      // Partículas
      for (const pt of particles) {
        const p = rotate(pt.p, ax * 0.6, ay * 0.5 + t * 0.05);
        const q = project(p, R, cx, cy);
        const tw = 0.5 + 0.5 * Math.sin(t * 1.5 + pt.tw);
        const a = (0.15 + 0.5 * ((q[2] + 2) / 4)) * (0.4 + 0.6 * tw);
        ctx.fillStyle = `rgba(${CYAN},${a.toFixed(3)})`;
        ctx.fillRect(q[0], q[1], 1.6, 1.6);
      }

      // Base: elipses projetadas no "chão" do holograma
      const baseY = cy + R * 1.55;
      for (let i = 0; i < 3; i++) {
        const pulse = (t * 0.4 + i / 3) % 1;
        const rx = R * (0.7 + pulse * 1.1);
        ctx.strokeStyle = `rgba(${CYAN},${(0.35 * (1 - pulse)).toFixed(3)})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.ellipse(cx, baseY, rx, rx * 0.22, 0, 0, Math.PI * 2);
        ctx.stroke();
      }

      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />;
}
