// Look-development check: the live model from the cameras of three offline
// hero renders, saved beside those renders as tests/shots/lookdev_<name>.png.
//
//   node tests/lookdev.mjs [--no-build] [--only=knee] [--look='{"exposure":0.8}']
//
// Left half: the offline render. Right half: the web render, same camera.
// `--look` overrides tuning constants for one run, to try values quickly.

import { spawn, spawnSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const site = join(dirname(fileURLToPath(import.meta.url)), '..');
const shots = join(site, 'tests', 'shots');
const args = process.argv.slice(2);
const only = args.find((a) => a.startsWith('--only='))?.slice(7);
const look = args.find((a) => a.startsWith('--look='))?.slice(7);
const PORT = 4178;
const BASE = `http://localhost:${PORT}/rj-28-interceptor/`;
const vite = join(site, 'node_modules', 'vite', 'bin', 'vite.js');

// Offline cameras, in the model's own axes (mm, Z up, robot faces −Y), 36 mm sensor.
const HEROES = [
  { name: 'front_deployed', loc: [2250, -3800, 1150], target: [-20, -80, 1005], lens: 75, size: [960, 1200], hash: '#tab=model&mount=deployed', patches: [['pauldron-top', 655, 292, 40, 14], ['chest', 420, 380, 70, 50], ['thigh', 420, 760, 50, 70], ['shin', 590, 950, 40, 60], ['toe-top', 340, 1140, 40, 12], ['barrel', 300, 215, 30, 14], ['floor', 150, 1050, 80, 40], ['backdrop', 100, 150, 80, 80]] },
  { name: 'rear_stowed', loc: [-2550, 3650, 1520], target: [-40, 70, 1085], lens: 75, size: [900, 1200], hash: '#tab=model', patches: [['pack', 540, 560, 60, 30], ['thigh-guard', 480, 800, 50, 20], ['barrel', 500, 180, 20, 80], ['floor', 150, 1000, 80, 40], ['backdrop', 100, 150, 80, 80]] },
  { name: 'knee', loc: [1150, 840, 640], target: [176, 30, 505], lens: 105, size: [1200, 900], hash: '#tab=model', patches: [['thigh-armour', 600, 150, 60, 60], ['bearing-ring', 580, 330, 14, 30], ['shin', 580, 720, 60, 60], ['backdrop', 60, 300, 60, 60]] },
];
const gltf = ([x, y, z]) => [x / 1000, z / 1000, -y / 1000];

async function waitForServer() {
  for (let i = 0; i < 80; i++) {
    try {
      if ((await fetch(BASE)).ok) return;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error('preview server did not start');
}

if (!args.includes('--no-build')) {
  const built = spawnSync(process.execPath, [vite, 'build'], { cwd: site, stdio: 'inherit' });
  if (built.status !== 0) process.exit(built.status ?? 1);
}
mkdirSync(shots, { recursive: true });
const server = spawn(process.execPath, [vite, 'preview', '--port', String(PORT), '--strictPort'], { cwd: site, stdio: 'ignore' });
let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ channel: 'msedge' });
  for (const hero of HEROES) {
    if (only && !hero.name.includes(only)) continue;
    const [w, h] = hero.size;
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    page.on('pageerror', (e) => console.log('pageerror', e.message));
    page.on('console', (m) => m.type() === 'error' && !/kaspersky/.test(m.text()) && console.log('console error', m.text()));
    await page.goto(BASE + (look ? `?look=${encodeURIComponent(look)}` : '') + hero.hash);

    await page.addStyleTag({ content: '.left-col,.side-panel,.site-header,.stage-buttons,.model-status,.hover-tag{display:none !important}' });
    await page.waitForFunction(() => window.rj28?.state().lod === 0, null, { timeout: 60000 });
    await page.evaluate(([pos, target, lens]) => window.rj28.scene.debugCamera(pos, target, lens), [gltf(hero.loc), gltf(hero.target), hero.lens]);
    await page.waitForFunction(() => window.rj28.scene.idle(), null, { timeout: 30000 });
    await page.waitForTimeout(300);
    const web = (await page.locator('canvas.stage-canvas').screenshot()).toString('base64');
    // Lay the offline render and the web render side by side on one sheet.
    await page.setViewportSize({ width: w * 2, height: h });
    await page.setContent(
      `<body style="margin:0;display:flex;background:#000"><img src="${BASE}renders/${hero.name}.jpg" style="width:${w}px;height:${h}px;object-fit:cover"><img src="data:image/png;base64,${web}" style="width:${w}px;height:${h}px"></body>`,
    );
    await page.waitForFunction(() => [...document.images].every((i) => i.complete));
    // Mean sRGB value of matching patches in the two halves: offline / web.
    const patches = await page.evaluate(
      ([pw, ph, list]) => {
        const out = [];
        for (const [name, x, y, sw, sh] of list) {
          const pair = [...document.images].map((img) => {
            const c = document.createElement('canvas');
            c.width = pw;
            c.height = ph;
            const g = c.getContext('2d');
            // Same crop as object-fit: cover.
            const s = Math.max(pw / img.naturalWidth, ph / img.naturalHeight);
            g.drawImage(img, (pw - img.naturalWidth * s) / 2, (ph - img.naturalHeight * s) / 2, img.naturalWidth * s, img.naturalHeight * s);
            const d = g.getImageData(x, y, sw, sh).data;
            let t = 0;
            for (let i = 0; i < d.length; i += 4) t += (d[i] + d[i + 1] + d[i + 2]) / 3;
            return Math.round(t / (d.length / 4));
          });
          out.push(`${name} ${pair[0]}/${pair[1]}`);
        }
        return out.join('  ');
      },
      [w, h, hero.patches ?? []],
    );
    if (patches) console.log(`PATCH ${hero.name}: ${patches}`);
    await page.screenshot({ path: join(shots, `lookdev_${hero.name}.png`) });
    console.log(`SHOT lookdev_${hero.name}.png`);
    await page.close();
  }
} finally {
  await browser?.close();
  server.kill();
}
