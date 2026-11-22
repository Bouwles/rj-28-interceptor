// Holds the rig in given poses and photographs them, against a running dev server.
//
//   npx vite --port 5199 &
//   node tests/pose.mjs shots.json
//
// shots.json: [{ "name": "fist", "pose": { "elbow_pitch_L": 90 }, "cam": [azimuthDeg, elevationDeg, distanceM, targetY],
//                "hash": "strip=2", "clip": "fistbump", "at": 2.5 }]
// With `clip` the named movement is played and photographed `at` seconds in.

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const site = join(dirname(fileURLToPath(import.meta.url)), '..');
const list = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const BASE = 'http://localhost:5199/rj-28-interceptor/';
const browser = await chromium.launch({ channel: 'msedge', args: ['--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1100, height: 1000 }, deviceScaleFactor: 2 });
page.on('pageerror', (e) => console.log('PAGE ERROR', e.message));
page.on('console', (m) => m.type() === 'error' && console.log('CONSOLE', m.text()));
await page.goto(BASE + '#tab=model');
await page.waitForFunction(() => window.rj28?.state().lod === 0, null, { timeout: 120000 });
let hash = '';
for (const s of list) {
  if ((s.hash ?? '') !== hash) {
    hash = s.hash ?? '';
    await page.evaluate((h) => (location.hash = 'tab=model' + (h ? '&' + h : '')), hash);
    await page.waitForTimeout(2500);
  }
  const [az, el, dist, ty] = s.cam ?? [28, 7, 3.6, 1.0];
  const a = (az * Math.PI) / 180;
  const e = (el * Math.PI) / 180;
  const pos = [Math.sin(a) * Math.cos(e) * dist, ty + Math.sin(e) * dist, Math.cos(a) * Math.cos(e) * dist];
  if (s.free) await page.evaluate(() => (window.rj28.scene.debugCamera(null), window.rj28.scene.resetView()));
  else await page.evaluate(([p, t]) => window.rj28.scene.debugCamera(p, t, 50), [pos, [s.tx ?? 0, ty, 0]]);
  if (s.free) await page.waitForTimeout(1200);
  if (s.clip) {
    await page.evaluate((id) => window.rj28.scene.play(id), s.clip);
    await page.waitForTimeout((s.at ?? 1) * 1000);
  } else {
    await page.evaluate((p) => window.rj28.scene.debugPose(p), s.pose ?? {});
    await page.waitForFunction(() => window.rj28.scene.idle(), null, { timeout: 30000 });
    await page.waitForTimeout(200);
  }
  await page.screenshot({ path: join(site, 'tests', 'shots', `pose_${s.name}.png`), clip: s.clip_ ? { x: s.clip_[0], y: s.clip_[1], width: s.clip_[2], height: s.clip_[3] } : { x: 0, y: 60, width: 740, height: 940 }, scale: s.clip_ ? 'device' : 'css' });
  console.log('SHOT', `pose_${s.name}.png`);
  if (s.clip) await page.evaluate(() => (window.rj28.scene.play(null), window.rj28.scene.debugPose({})));
}
await browser.close();
