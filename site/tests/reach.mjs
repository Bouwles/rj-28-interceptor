// Diagnostics: find right-arm angles that put the right fist in the left palm.
import { chromium } from 'playwright';
const browser = await chromium.launch({ channel: 'msedge' });
const page = await browser.newPage();
await page.goto('http://localhost:5199/rj-28-interceptor/#tab=model');
await page.waitForFunction(() => window.rj28?.scene && window.rj28.state().lod !== null, null, { timeout: 120000 });
const items = [['hand_L', 'wpitch_L'], ['hand_L', 'finger2a_L'], ['hand_L', 'finger1a_L'], ['hand_R', 'wpitch_R'], ['hand_R', 'finger2a_R'], ['hand_R', 'finger1a_R']];
const probe = (pose) => page.evaluate(([p, it]) => window.rj28.scene.debugProbe(p, it), [pose, items]);
const sub = (a, b) => a.map((v, i) => v - b[i]);
const add = (a, b, k = 1) => a.map((v, i) => v + b[i] * k);
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const len = (a) => Math.hypot(...a);
const norm = (a) => a.map((v) => v / len(a));
const dot = (a, b) => a.reduce((s, v, i) => s + v * b[i], 0);
const args = JSON.parse(process.argv[2]);
const L = args.L;
let R = args.R;
const gap = args.gap ?? 0.045;
const cost = async (r) => {
  const [w, k2, k1, wr, k2r] = await probe({ ...L, ...r });
  const n = norm(cross(sub(k2, w), sub(k1, k2)));
  const target = add(add(w, sub(k2, w), 0.55), n, gap);
  const d = len(sub(k2r, target));
  const align = dot(norm(sub(k2r, wr)), n); // -1 = fist driving straight into the palm
  return { d, align, c: d + 0.02 * (1 + align), target, k2r, n };
};
let best = await cost(R);
for (let step = 8; step > 0.2; step /= 2) {
  for (let pass = 0; pass < 4; pass++) {
    for (const j of Object.keys(R)) {
      for (const s of [-step, step]) {
        const tryR = { ...R, [j]: R[j] + s };
        const c = await cost(tryR);
        if (c.c < best.c) { best = c; R = tryR; }
      }
    }
  }
}
const mm = (v) => v.map((c) => Math.round(c * 1000)).join(',');
console.log('R', JSON.stringify(Object.fromEntries(Object.entries(R).map(([k, v]) => [k, Math.round(v)]))), 'miss mm', Math.round(best.d * 1000), 'align', best.align.toFixed(2), 'target', mm(best.target), 'normal', best.n.map((v) => v.toFixed(2)).join(','));
await browser.close();
