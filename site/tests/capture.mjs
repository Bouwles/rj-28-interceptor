// Builds the site, serves the build under the Pages base path, captures every
// screen at 1920x1080 and 390x844 into tests/shots/, and checks the live model.
//
//   node tests/capture.mjs                build, serve, capture, check
//   node tests/capture.mjs --no-build     reuse the existing dist/
//   node tests/capture.mjs --only=strip   capture shots whose name contains a string
//
// Uses the installed Microsoft Edge (Playwright channel `msedge`). Exits
// non-zero if the page logs a console error, a request fails, anything is
// fetched from another origin, or a check fails.

import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const site = join(dirname(fileURLToPath(import.meta.url)), '..');
const shots = join(site, 'tests', 'shots');
const args = process.argv.slice(2);
const only = args.find((a) => a.startsWith('--only='))?.slice(7);
const PORT = 4179;
const BASE = `http://localhost:${PORT}/rj-28-interceptor/`;
const vite = join(site, 'node_modules', 'vite', 'bin', 'vite.js');
const parts = JSON.parse(readFileSync(join(site, 'src', 'data', 'parts.json'), 'utf8'));
const numbers = parts.map((p) => p.number).sort();

const VIEWPORTS = [
  { name: 'desktop', width: 1920, height: 1080, deviceScaleFactor: 1, isMobile: false },
  { name: 'phone', width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
];

const problems = [];
const notes = new Set();
const INJECTED = /^https?:\/\/[^/]*kaspersky-labs\.com\//;
const expect = (ok, what) => ok || problems.push(`check: ${what}`);

function checkBuild() {
  const dist = join(site, 'dist');
  const html = readFileSync(join(dist, 'index.html'), 'utf8');
  expect(/og:image" content="https?:\/\/[^"]+\/rj-28-interceptor\/renders\/social_card\.jpg"/.test(html), 'og:image is an absolute URL under the base path');
  const texts = [html, ...readdirSync(join(dist, 'assets')).filter((f) => /\.(js|css)$/.test(f)).map((f) => readFileSync(join(dist, 'assets', f), 'utf8'))];
  for (const text of texts) {
    const fetched = text.match(/(?:src|href)=["']https?:\/\/[^"']+|url\(["']?https?:\/\/[^)"']+|(?:fetch|import)\(["'`]https?:\/\/[^"'`]+/g) ?? [];
    for (const m of fetched) if (!m.includes('/rj-28-interceptor/')) problems.push(`build references an external address: ${m}`);
  }
  const spec = JSON.parse(readFileSync(join(site, 'src', 'data', 'spec.json'), 'utf8'));
  expect(parts.length === spec.part_count, `parts.json (${parts.length}) and spec.json (${spec.part_count}) agree on the part count`);
}

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

function watch(page) {
  page.on('console', (msg) => {
    if ((msg.type() === 'error' || msg.type() === 'warning') && !INJECTED.test(msg.location()?.url ?? '')) problems.push(`console ${msg.type()}: ${msg.text()}`);
  });
  page.on('pageerror', (err) => problems.push(`page error: ${err.message}`));
  page.on('requestfailed', (req) => INJECTED.test(req.url()) || problems.push(`request failed: ${req.url()} ${req.failure()?.errorText ?? ''}`));
  page.on('response', (res) => res.status() >= 400 && problems.push(`HTTP ${res.status()}: ${res.url()}`));
  page.on('request', (req) => {
    const url = req.url();
    if (url.startsWith(`http://localhost:${PORT}/`) || url.startsWith('data:') || url.startsWith('blob:')) return;
    // Some desktop security suites inject a script into every plain-HTTP page; it is not in the build.
    if (INJECTED.test(url)) notes.add(`ignored a script injected by local security software (${new URL(url).host})`);
    else problems.push(`external request: ${url}`);
  });
}

/** Wait until the model is in, has finished whatever it is animating, and images have decoded. */
async function settled(page, lod, extra = 250) {
  await page.waitForFunction((want) => window.rj28 && window.rj28.state().lod === want && window.rj28.scene.idle(), lod, { timeout: 90000 });
  await page.evaluate(async () => {
    const imgs = [...document.images].filter((i) => i.src && !i.complete && i.loading !== 'lazy');
    await Promise.race([Promise.all(imgs.map((i) => new Promise((r) => ((i.onload = r), (i.onerror = r))))), new Promise((r) => setTimeout(r, 8000))]);
  });
  await page.waitForTimeout(extra);
}

async function go(page, hash, lod) {
  await page.evaluate((h) => (location.hash = h), hash);
  await page.waitForTimeout(150);
  await settled(page, lod, 600);
}

async function shot(page, viewport, name) {
  if (only && !name.includes(only)) return;
  await page.screenshot({ path: join(shots, `${viewport.name}_${name}.png`) });
  console.log(`SHOT ${viewport.name}_${name}.png`);
}

async function capture(browser, viewport) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: viewport.deviceScaleFactor,
    isMobile: viewport.isMobile,
    hasTouch: viewport.hasTouch ?? false,
  });
  const phone = viewport.name === 'phone';
  const lod = phone ? 1 : 0;
  const page = await context.newPage();
  watch(page);

  // ── Introduction ──────────────────────────────────────────────────────────
  await page.goto(BASE);
  await page.waitForSelector('.hero h1');
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => document.querySelector('.hero-image img').complete);
  await page.waitForTimeout(500);
  await shot(page, viewport, '01_intro');
  for (const [i, sel] of ['.feature:nth-child(1)', '.feature:nth-child(2)', '.feature:nth-child(4)', '.closing'].entries()) {
    await page.evaluate((s) => document.querySelector(s).scrollIntoView({ block: 'center' }), sel);
    await page.waitForFunction(() => [...document.images].filter((im) => im.getBoundingClientRect().top < innerHeight && im.getBoundingClientRect().bottom > 0).every((im) => im.complete));
    await page.waitForTimeout(400);
    await shot(page, viewport, `02_intro_section_${i + 1}`);
  }

  // ── Model ─────────────────────────────────────────────────────────────────
  await page.evaluate(() => document.querySelector('.intro-page').scrollTo(0, 0));
  await page.locator('.hero .btn-primary').click();
  await settled(page, lod, 900);
  await shot(page, viewport, '10_model_at_rest');
  await go(page, '#tab=model&mount=deployed', lod);
  await shot(page, viewport, '11_cannon_deployed');
  await go(page, '#tab=model&mount=deployed&trav=-22', lod);
  await shot(page, viewport, '12_cannon_traversed');
  await page.evaluate(() => (location.hash = '#tab=model'));
  await page.waitForTimeout(1200);
  await shot(page, viewport, '13_cannon_mid_travel');
  await settled(page, lod);
  for (const stage of [1, 2, 3, 4]) {
    await go(page, `#tab=model&strip=${stage}`, lod);
    await shot(page, viewport, `20_strip_${stage}`);
    if (stage === 1) {
      await page.evaluate(() => (location.hash = '#tab=model&strip=2'));
      await page.waitForTimeout(800);
      await shot(page, viewport, '21_strip_mid_transition');
    }
  }
  await go(page, '#tab=model&strip=4&mount=deployed', lod);
  await shot(page, viewport, '22_strip_4_deployed');
  for (const pct of [50, 100]) {
    await go(page, `#tab=model&explode=${pct}`, lod);
    await shot(page, viewport, `30_explode_${pct}`);
  }
  await go(page, '#tab=model&part=RJ28-15-027', lod);
  await shot(page, viewport, '40_part_selected');
  await go(page, '#tab=model&part=RJ28-03-062&xray=1', lod);
  await shot(page, viewport, '41_xray_part_selected');
  await go(page, '#tab=model', lod);
  if (phone) {
    await page.locator('.stage-btn-actions').click();
    await page.waitForTimeout(400);
    await shot(page, viewport, '45_controls_sheet');
    await page.locator('.stage-btn-actions').click();
    await page.locator('.stage-btn-parts').click();
    await page.waitForTimeout(400);
    await shot(page, viewport, '46_parts_sheet');
    await page.locator('.stage-btn-parts').click();
  } else {
    await page.locator('.stage-btn-parts').click();
    await page.locator('.tree-search').fill('trunnion');
    await settled(page, lod, 400);
    await shot(page, viewport, '42_parts_list_search');
    await page.locator('.tree-search').fill('');
    await page.locator('.tree-close').click();
    await settled(page, lod, 400);
    // Hover shows the part under the pointer; a click selects it.
    const box = await page.locator('canvas.stage-canvas').boundingBox();
    const at = { x: (box.width - 360) / 2, y: box.height * 0.42 };
    await page.mouse.move(at.x, at.y);
    await page.mouse.move(at.x + 4, at.y + 2);
    await page.waitForTimeout(500);
    const hovered = await page.locator('.hover-tag .data').textContent();
    expect(/^RJ28-/.test(hovered ?? ''), `hover shows a part number by the pointer (got "${hovered}")`);
    await shot(page, viewport, '43_hover');
    await page.mouse.click(at.x + 4, at.y + 2);
    await page.waitForTimeout(300);
    const picked = await page.evaluate(() => window.rj28.state().selected);
    expect(picked === hovered, `clicking the hovered part selects it (${hovered} / ${picked})`);
    await page.keyboard.press('Escape');
    await page.keyboard.press('?');
    await page.waitForTimeout(300);
    await shot(page, viewport, '44_keys');
    await page.keyboard.press('Escape');
  }

  // ── Blueprints and specification ──────────────────────────────────────────
  await go(page, '#tab=blueprints', lod);
  const ids = await page.evaluate(() => [...document.querySelectorAll('.sheet-index-item')].map((b) => b.dataset.id));
  for (const [i, id] of ids.entries()) {
    await go(page, `#tab=blueprints&sheet=${id}`, lod);
    await page.waitForFunction((n) => document.querySelector('.sheet-canvas svg')?.id?.endsWith(n) ?? true, String(i + 1).padStart(3, '0'));
    await page.waitForTimeout(500);
    await shot(page, viewport, `50_sheet_${String(i + 1).padStart(2, '0')}`);
  }
  await go(page, '#tab=model&part=RJ28-15-031', lod);
  await page.keyboard.press('d');
  await page.waitForTimeout(900);
  await shot(page, viewport, '51_show_in_drawing');
  await go(page, '#tab=spec', lod);
  await shot(page, viewport, '60_specification');
  for (const id of ['joints', 'mass', 'notes']) {
    await page.evaluate((x) => document.getElementById(`spec-${x}`).scrollIntoView(), id);
    await page.waitForTimeout(200);
    await shot(page, viewport, `61_specification_${id}`);
  }
  await page.evaluate(() => {
    document.getElementById('spec-bom').scrollIntoView();
    document.querySelectorAll('.bom-asm')[14].open = true;
  });
  await page.waitForTimeout(300);
  await shot(page, viewport, '62_specification_bom');

  // ── Checks on the live model ──────────────────────────────────────────────
  if (!only) {
    await go(page, '#tab=model', lod);
    if (!phone) {
      const model = await page.evaluate(() => ({ count: window.rj28.scene.partCount(), numbers: window.rj28.scene.partNumbers() }));
      expect(model.count === parts.length, `GLB has ${model.count} part nodes, parts.json has ${parts.length}`);
      const have = new Set(model.numbers);
      expect(numbers.every((n) => have.has(n)), 'every part resolves to a node');
      const decals = new Set(parts.filter((p) => p.material_key === 'decal').map((p) => p.number));
      const unpickable = await page.evaluate((list) => list.filter((n) => !window.rj28.scene.pickable(n)), numbers.filter((n) => !decals.has(n)));
      expect(unpickable.length === 0, `every part is pickable at strip 0 (not: ${unpickable.slice(0, 5).join(', ')})`);
      console.log(`CHECK ${model.count} part nodes, ${numbers.length - decals.size} pickable, ${decals.size} markings selectable from the list only`);
      const hash = async () => {
        await page.waitForTimeout(90);
        return page.evaluate(() => location.hash);
      };
      await page.keyboard.press('ArrowDown');
      expect((await hash()).includes(`part=${numbers[0]}`), 'arrow down selects the first part');
      await page.keyboard.press('m');
      expect((await hash()).includes('mount=deployed'), 'M deploys the cannon');
      await page.keyboard.press(']');
      expect((await hash()).includes('strip=1'), '] takes a layer off');
      await page.keyboard.press('[');
      expect(!(await hash()).includes('strip='), '[ puts it back');
      await page.keyboard.press('x');
      expect((await hash()).includes('xray=1'), 'X turns x-ray on');
      await page.keyboard.press('e');
      expect((await hash()).includes('explode=50'), 'E explodes to assemblies apart');
      await page.keyboard.press('0');
      expect((await hash()) === '#tab=model&mount=deployed', '0 resets the model but leaves the cannon where it is');
      for (const [key, tab] of [['2', 'blueprints'], ['3', 'spec'], ['1', 'model']]) {
        await page.keyboard.press(key);
        expect((await hash()).includes(`tab=${tab}`), `${key} opens ${tab}`);
      }
      await go(page, '#tab=model', lod);
      const seen = new Set();
      for (let i = 0; i < numbers.length; i++) {
        await page.keyboard.press('ArrowDown');
        seen.add(await page.evaluate(() => window.rj28.state().selected));
      }
      expect(seen.size === numbers.length, `stepping the list reached ${seen.size} of ${numbers.length} parts`);
      console.log(`CHECK keyboard map, address sync, ${seen.size} of ${numbers.length} parts reachable`);
      await go(page, '#tab=model', lod);
    }
    const bench = await page.evaluate(() => window.rj28.scene.benchmark(4));
    console.log(
      `FRAME ${viewport.width}x${viewport.height} LOD${bench.lod} ${bench.triangles} triangles, ${bench.drawCalls} draw calls: ` +
        `mean ${bench.frameMs.toFixed(1)} ms, worst ${bench.worstMs.toFixed(1)} ms, pixel ratio ${bench.pixelRatio.toFixed(2)}${bench.reduced ? ', floor mirror off while moving' : ''}`,
    );
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow <= 0, `no horizontal overflow (${overflow}px)`);
  }
  await page.close();

  // ── Without WebGL: the stand-in drawing ───────────────────────────────────
  {
    const p = await context.newPage();
    watch(p);
    await p.goto(`${BASE}?static#tab=model&part=RJ28-15-006`);
    await p.waitForSelector('.boxmodel path');
    await p.waitForTimeout(600);
    await shot(p, viewport, '80_static_model');
    await p.close();
  }
  await context.close();
}

async function main() {
  if (!args.includes('--no-build')) {
    const built = spawnSync(process.execPath, [vite, 'build'], { cwd: site, stdio: 'inherit' });
    if (built.status !== 0) process.exit(built.status ?? 1);
  }
  if (!only) for (const f of existsSync(shots) ? readdirSync(shots) : []) if (!f.startsWith('lookdev_')) rmSync(join(shots, f));
  mkdirSync(shots, { recursive: true });

  const server = spawn(process.execPath, [vite, 'preview', '--port', String(PORT), '--strictPort'], { cwd: site, stdio: 'ignore' });
  let browser;
  try {
    await waitForServer();
    checkBuild();
    browser = await chromium.launch({ channel: 'msedge' });
    for (const viewport of VIEWPORTS) await capture(browser, viewport);
  } finally {
    await browser?.close();
    server.kill();
  }

  for (const n of notes) console.log(`NOTE ${n}`);
  const unique = [...new Set(problems)];
  if (unique.length) {
    console.error(`\n${unique.length} problem(s):`);
    for (const p of unique) console.error(`  ${p}`);
    process.exit(1);
  }
  console.log('\nCapture complete: console clean, no failed or external requests, all checks passed.');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
