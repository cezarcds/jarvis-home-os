import { placeWall, slotsFor, wallIds } from "../src/stage/wall.js";
import { visibleCallouts, placeCallouts, anchorFor } from "../src/stage/calloutsLogic.js";
import assert from "node:assert";
const area = { x: 18, y: 9, w: 64, h: 76, mode: "full" };
for (const mode of ["full", "half", "strip"]) for (let n = 1; n <= 4; n++) {
  const s = slotsFor(n, mode);
  assert.equal(s.length, n);
  for (const [x, y, w, h] of s) assert.ok(x >= -1e-9 && y >= -1e-9 && x + w <= 100.001 && y + h <= 100.001 && w > 5 && h > 5, `${mode}${n} ${[x,y,w,h]}`);
  // sem sobreposição
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
    const a = s[i], b = s[j]; const ox = Math.min(a[0]+a[2], b[0]+b[2]) - Math.max(a[0], b[0]); const oy = Math.min(a[1]+a[3], b[1]+b[3]) - Math.max(a[1], b[1]);
    assert.ok(!(ox > 0.01 && oy > 0.01), `sobrepõe ${mode}${n} ${i},${j}`);
  }
}
const p = placeWall(["a", "b", "c"], "c", area);
assert.equal(p.length, 3); const big = p.find((k) => k.id === "c"); assert.ok(big.featured && big.w > p[0].w); assert.deepEqual(p.map((k) => k.id), ["a", "b", "c"]);
assert.equal(placeWall([], null, area).length, 0); assert.equal(placeWall(["a","b","c","d","e","f"], "a", area).length, 4);
const scene = { media: [{ id: "m1" }, { id: "m2" }, { id: "m3" }] };
const ent = { m1: { status: "ready" }, m2: { status: "none" }, m3: { status: "loading" } };
assert.deepEqual(wallIds(scene, { show: ["m1", "m2", "m3"] }, ent), ["m1", "m3"]);
assert.deepEqual(wallIds(scene, { show: ["m2"] }, ent), ["m1", "m3"]);
assert.deepEqual(wallIds(scene, {}, ent), ["m1", "m3"]);
const cs = [{ text: "a", at: 0.1, side: "left" }, { text: "b", at: 0.5, side: "right" }, { text: "c", at: 0.8, side: "left" }];
assert.equal(visibleCallouts(cs, 0.0, false).length, 0); assert.equal(visibleCallouts(cs, 0.5, false).length, 2); assert.equal(visibleCallouts(cs, 0.1, true).length, 3);
const pl = placeCallouts(cs); assert.ok(pl[0].y < pl[2].y && pl[1].y === pl[0].y);
const a = anchorFor({ ...pl[0], target: "c" }, { cards: p }); assert.equal(a.x, big.x);
const a2 = anchorFor({ ...pl[1], target: null }, { cards: p }); assert.equal(a2.x, big.x + big.w);
assert.deepEqual(anchorFor({ ...pl[0], target: "n1" }, { cards: p, nodes: { n1: { x: 30, y: 40 } } }), { x: 30, y: 40 });
assert.deepEqual(anchorFor({ ...pl[0], target: null }, { cards: [], nodes: {} }), { x: 50, y: 46 });
console.log("wall + callouts: ok");
