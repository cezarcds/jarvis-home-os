import assert from "node:assert";
import { ICONS } from "../src/stage/icons.js";
import { markGeometry, roughEllipse, roughLine, roughArrow, rng, hashStr, targetRect } from "../src/stage/handDrawn.js";
import { pointsFromAlpha, samplePoints, makeParticles, stepParticles, formedRatio } from "../src/stage/particles.js";

const ok = (d) => typeof d === "string" && d.length > 4 && !/NaN|Infinity|undefined/.test(d) && /^M/.test(d);
// ícones
assert.equal(Object.keys(ICONS).length, 35);
for (const [k, list] of Object.entries(ICONS)) { assert.ok(list.length >= 1, k); for (const d of list) assert.ok(ok(d), `${k}: ${d}`); }
// determinismo
assert.equal(roughEllipse(100, 100, 40, 30, 7), roughEllipse(100, 100, 40, 30, 7));
assert.notEqual(roughEllipse(100, 100, 40, 30, 7), roughEllipse(100, 100, 40, 30, 8));
assert.ok(ok(roughLine(0, 0, 200, 10, 3)));
const ar = roughArrow([0, 0], [200, 120], 5); assert.ok(ok(ar.shaft) && ok(ar.head));
assert.equal(hashStr("a"), hashStr("a")); const r = rng(1); const v = r(); assert.ok(v >= 0 && v < 1);
// geometria das marcas
const size = { w: 1400, h: 800 };
const cards = [{ id: "m1", x: 20, y: 12, w: 36, h: 70 }, { id: "m2", x: 58, y: 12, w: 22, h: 34 }];
const nodes = { reator: { x: 30, y: 50 }, vapor: { x: 70, y: 50 } };
const ctx = { cards, nodes, size };
const inb = (x, y) => x >= 0 && y >= 0 && x <= size.w && y <= size.h;
const g1 = markGeometry({ type: "circle", target: "m1", label: "aqui", at: 0.2 }, ctx, "s"); assert.ok(ok(g1.paths[0].d)); assert.equal(g1.label.text, "aqui"); assert.ok(inb(g1.label.x, g1.label.y));
assert.equal(markGeometry({ type: "circle", target: "naoexiste", at: 0.2 }, ctx), null);
const g2 = markGeometry({ type: "underline", target: "vapor", at: 0.3 }, ctx); assert.equal(g2.paths.length, 2);
const g3 = markGeometry({ type: "arrow", from: "m1", target: "m2", label: "olha", at: 0.4 }, ctx); assert.ok(ok(g3.paths[0].d) && g3.paths[1].role === "head");
const g3b = markGeometry({ type: "arrow", from: null, target: "m2", at: 0.4 }, ctx); assert.ok(ok(g3b.paths[0].d));
assert.equal(markGeometry({ type: "arrow", from: "naoexiste", target: "m2", at: 0.4 }, ctx), null);
const g4 = markGeometry({ type: "bracket", targets: ["m1", "m2"], label: "ideia formada", at: 0.5 }, ctx); assert.ok(ok(g4.paths[0].d)); assert.equal(g4.label.rot, -90);
assert.equal(markGeometry({ type: "bracket", targets: ["m1", "zz"], at: 0.5 }, ctx), null);
const g5 = markGeometry({ type: "icon", target: "reator", icon: "bolt", label: "energia", at: 0.6 }, ctx); assert.equal(g5.icon.name, "bolt"); assert.ok(inb(g5.icon.x, g5.icon.y) && inb(g5.icon.x + g5.icon.size, g5.icon.y + g5.icon.size));
const gEdge = markGeometry({ type: "icon", target: "m1", icon: "bolt", at: 0.1 }, { cards: [{ id: "m1", x: 0, y: 0, w: 10, h: 10 }], nodes: {}, size }); assert.ok(gEdge.icon.x >= 0 && gEdge.icon.y >= 0);
assert.ok(targetRect("vapor", ctx).kind === "node");
// partículas: um "T" sintético
const W = 60, H = 40, data = new Uint8ClampedArray(W * H * 4);
const paint = (x, y) => { data[(y * W + x) * 4 + 3] = 255; };
for (let x = 5; x < 55; x++) for (let y = 5; y < 12; y++) paint(x, y);
for (let x = 27; x < 35; x++) for (let y = 12; y < 36; y++) paint(x, y);
const pts = pointsFromAlpha(data, W, H, 2); assert.ok(pts.length > 100);
assert.ok(pts.every(([x, y]) => data[(y * W + x) * 4 + 3] > 128));
const { points, step } = samplePoints(data, W, H, 60, 2); assert.ok(points.length <= 60 || step >= 14); assert.ok(step > 2);
const s = makeParticles(pts, [100, 50], 1400, 800, rng(2)); assert.equal(s.n, pts.length);
let t = 0; let alive = true;
for (let i = 0; i < 180 && alive; i++) { t += 1 / 60; alive = stepParticles(s, 1 / 60, "form", t); }
assert.ok(formedRatio(s, 8) > 0.9, `formou ${formedRatio(s, 8)}`);
for (let i = 0; i < s.n; i++) assert.ok(Number.isFinite(s.x[i]) && Number.isFinite(s.y[i]));
t = 0; alive = true; let frames = 0;
while (alive && frames < 200) { t += 1 / 60; alive = stepParticles(s, 1 / 60, "dissolve", t); frames++; }
assert.ok(!alive && frames < 120, `dissolve em ${frames} quadros`);
console.log("quadro + partículas: ok");
