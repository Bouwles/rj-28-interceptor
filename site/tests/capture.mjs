// Builds the site, serves the build under the Pages base path, captures every
// screen at 1920x1080 and 390x844 into tests/shots/, and checks the live model.
//
//   node tests/capture.mjs                build, serve, capture, check
//   node tests/capture.mjs --no-build     reuse the existing dist/
//   node tests/capture.mjs --only=strip   capture shots whose name contains a string
//
// Uses the installed Microsoft Edge (Playwright channel `msedge`); no browser
// download is needed. Exits non-zero if the page logs a console error, a
// request fails, anything is fetched from another origin, or a check fails.

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

/** Checks on the built files themselves: nothing external, card metadata, data in step. */
function checkBuild() {
  const dist = join(site, 'dist');
  const html = readFileSync(join(dist, 'index.html'), 'utf8');
  expect(/og:image" content="https?:\/\/[^"]+\/rj-28-interceptor\/renders\/social_card\.jpg"/.test(html), 'og:image is an absolute URL under the base path');
  const texts = [html, ...readdirSync(join(dist, 'assets')).filter((f) => /\.(js|css)$/.test(f)).map((f) => readFileSync(join(dist, 'assets', f), 'utf8'))];
  for (const text of texts) {
    const fetched = text.match(/(?:src|href)=["']https?:\/\/[^"']+|url\(["']?https?:\/\/[^)"']+|(?:fetch|import)\(["'`]https?:\/\/[^"'`]+/g) ?? [];
    for (const m of fetched) if (!m.includes('/rj-28-interceptor/')) problems.push(`build references an external address: ${m}`);
  }
  const data = join(site, 'src', 'data');
  const spec = JSON.parse(readFileSync(join(data, 'spec.json'), 'utf8'));
  expect(parts.length === spec.part_count, `parts.json (${parts.length}) and spec.json (${spec.part_count}) agree on the part count`);
  expect(new Set(numbers).size === parts.length, 'part numbers are unique');
  if (existsSync(join(data, 'model.json'))) {
    const nodes = JSON.parse(readFileSync(join(data, 'model.json'), 'utf8')).files?.lod0?.part_nodes;
    expect(nodes === undefined || nodes === parts.length, `model.json (${nodes}) and parts.json (${parts.length}) agree on the part count`);
  }
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
    // Some desktop security suites inject a script into every plain-HTTP page on
    // the machine. It is not in the build (checked above), so it is noted only.
    if (INJECTED.test(url)) notes.add(`ignored a script injected by local security software (${new URL(url).host})`);
    else problems.push(`external request: ${url}`);
  });
}

async function open(context, hash = '', query = '') {
  const page = await context.newPage();
  watch(page);
  await page.goto(`${BASE}${query}${hash}`);
  await page.waitForSelector('.loader', { state: 'detached', timeout: 60000 });
  await page.evaluate(() => document.fonts.ready);
  return page;
}

/** Wait until the scene has finished whatever it is animating and drawn the settled frame. */
async function settled(page, lod, extra = 250) {
  await page.waitForFunction((want) => !window.rj28 || (window.rj28.state().lod === want && window.rj28.scene.idle()), lod, { timeout: 60000 });
  await page.evaluate(async () => {
    const imgs = [...document.images].filter((i) => i.src && !i.complete);
    await Promise.race([Promise.all(imgs.map((i) => new Promise((r) => ((i.onload = r), (i.onerror = r))))), new Promise((r) => setTimeout(r, 8000))]);
  });
  await page.waitForTimeout(extra);
}

async function go(page, hash, lod) {
  await page.evaluate((h) => (location.hash = h), hash);
  await page.waitForTimeout(120);
  await settled(page, lod);
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

  // ── Loading screen: hold one data file back so the drawing is mid-way ─────
  {
    const page = await context.newPage();
    let release;
    const gate = new Promise((r) => (release = r));
    await page.route('**/parts-*.json', async (route) => {
      await gate;
      await route.continue();
    });
    await page.goto(BASE);
    await page.waitForSelector('.loader .sheet-svg');
    await page.waitForTimeout(900);
    await shot(page, viewport, '00_loading');
    release();
    await page.waitForSelector('.loader', { state: 'detached', timeout: 60000 });
    await page.close();
  }

  // ── Model tab ─────────────────────────────────────────────────────────────
  const page = await open(context);
  await settled(page, lod, 500);
  await shot(page, viewport, '10_model_at_rest');
  await go(page, '#mount=stowed', lod); // any state in the address dismisses the title block
  await shot(page, viewport, '11_model_tree_and_actions');

  await go(page, '#mount=deployed', lod);
  await shot(page, viewport, '12_cannon_deployed');
  await go(page, '#mount=deployed&trav=-22', lod);
  await shot(page, viewport, '13_cannon_traversed');
  await go(page, '#mount=deployed&elev=38', lod);
  await shot(page, viewport, '14_cannon_elevated');
  // Stowing from there: catch the barrel on its way up.
  await page.evaluate(() => (location.hash = ''));
  await page.waitForTimeout(1300);
  await shot(page, viewport, '15_cannon_mid_travel');
  await settled(page, lod);
  await shot(page, viewport, '16_cannon_stowed');

  for (let stage = 0; stage <= 4; stage++) {
    await go(page, stage ? `#strip=${stage}` : '', lod);
    await shot(page, viewport, `20_strip_${stage}`);
    if (stage === 1) {
      // One frame part-way through the next stage coming off.
      await page.evaluate(() => (location.hash = '#strip=2'));
      await page.waitForTimeout(800);
      await shot(page, viewport, '21_strip_mid_transition');
    }
  }
  await go(page, '#strip=4&mount=deployed', lod);
  await shot(page, viewport, '22_strip_4_deployed');

  for (const pct of [50, 100]) {
    await go(page, `#explode=${pct}`, lod);
    await shot(page, viewport, `30_explode_${pct}`);
  }
  await go(page, '#explode=70&strip=2', lod);
  await shot(page, viewport, '31_explode_70_strip_2');

  await go(page, '#part=RJ28-15-027', lod);
  await shot(page, viewport, '40_part_selected');
  await go(page, '#part=RJ28-03-062&xray=1', lod);
  await shot(page, viewport, '41_xray_part_selected');
  await go(page, '#iso=11', lod);
  await shot(page, viewport, '42_assembly_isolated');

  if (phone) {
    await go(page, '', lod);
    await page.locator('.bb-drawer', { hasText: 'Actions' }).click();
    await page.waitForTimeout(400);
    await shot(page, viewport, '45_drawer_actions');
    await page.locator('.bb-drawer', { hasText: 'Parts' }).click();
    await page.waitForTimeout(400);
    await shot(page, viewport, '46_drawer_parts');
    await page.locator('.tree-close').click();
  } else {
    // Hover: outline and tag follow the pointer. Then a click selects, and the camera frames it.
    await go(page, '#mount=stowed', lod);
    const box = await page.locator('canvas.stage-canvas').boundingBox();
    const free = { x: 372 + (box.width - 744) / 2, y: box.height * 0.36 };
    await page.mouse.move(free.x, free.y);
    await page.mouse.move(free.x + 4, free.y + 2);
    await page.waitForTimeout(500);
    const hovered = await page.locator('.hover-tag .data').textContent();
    expect(/^RJ28-/.test(hovered ?? ''), `hover shows a part number by the pointer (got "${hovered}")`);
    await shot(page, viewport, '43_hover');
    await page.mouse.click(free.x + 4, free.y + 2);
    await page.waitForTimeout(300);
    const picked = await page.evaluate(() => window.rj28.state().selected);
    expect(picked === hovered, `clicking the hovered part selects it (${hovered} / ${picked})`);
    await page.keyboard.press('f');
    await settled(page, lod);
    await shot(page, viewport, '44_click_selected_and_framed');
    // Measure between two points on the chest.
    await go(page, '#mount=stowed', lod);
    await page.keyboard.press('0');
    await settled(page, lod);
    await page.keyboard.press('r');
    await page.mouse.click(free.x - 60, free.y);
    await page.mouse.click(free.x + 60, free.y);
    await page.waitForTimeout(400);
    const measured = await page.locator('.act-note.data').textContent();
    expect(/\d mm/.test(measured ?? ''), `measure reports a distance in millimetres (got "${measured}")`);
    await shot(page, viewport, '47_measure');
    await page.keyboard.press('r');
  }

  // ── Dossier: every station ────────────────────────────────────────────────
  await go(page, '#tab=dossier', lod);
  await shot(page, viewport, '50_dossier_00_title');
  const count = await page.locator('.tour-section').count();
  for (let i = 1; i < count; i++) {
    await page.evaluate(
      ([index, isPhone]) => {
        const el = document.querySelectorAll('.tour-section')[index];
        const panel = el.querySelector('.panel') ?? el;
        const top = panel.getBoundingClientRect().top + window.scrollY;
        window.scrollTo(0, top - (isPhone ? window.innerHeight * 0.52 : 150));
      },
      [i, phone],
    );
    await page.waitForTimeout(300);
    await settled(page, lod, 500);
    const label = (await page.locator('.tour-section').nth(i).getAttribute('aria-label')).toLowerCase().replace(/[^a-z]+/g, '-');
    await shot(page, viewport, `50_dossier_${String(i).padStart(2, '0')}_${label}`);
  }
  // The cannon section, further through: the barrel is on its way down.
  await page.evaluate(() => {
    const el = document.querySelectorAll('.tour-section')[6];
    window.scrollTo(0, el.offsetTop + el.offsetHeight * 0.3);
  });
  await settled(page, lod, 400);
  await shot(page, viewport, '51_dossier_06_mount_scrubbed');
  await page.evaluate(() => {
    const el = document.querySelectorAll('.tour-section')[7];
    window.scrollTo(0, el.offsetTop + el.offsetHeight * 0.45);
  });
  await settled(page, lod, 400);
  await shot(page, viewport, '52_dossier_07_armour_lifted');

  // ── Specification and blueprints ──────────────────────────────────────────
  await go(page, '#tab=spec', lod);
  await shot(page, viewport, '60_specification');
  await page.evaluate(() => document.getElementById('spec-joints').scrollIntoView());
  await page.waitForTimeout(200);
  await shot(page, viewport, '61_specification_joints');
  await page.evaluate(() => document.getElementById('spec-mass').scrollIntoView());
  await page.waitForTimeout(200);
  await shot(page, viewport, '62_specification_mass');
  await page.evaluate(() => {
    document.getElementById('spec-bom').scrollIntoView();
    document.querySelectorAll('.bom-asm')[14].open = true;
  });
  await page.waitForTimeout(300);
  await shot(page, viewport, '63_specification_bom');

  await go(page, '#tab=blueprints', lod);
  const ids = await page.evaluate(() => [...document.querySelectorAll('.sheet-index-item')].map((b) => b.dataset.id));
  for (const [i, id] of ids.entries()) {
    await go(page, `#tab=blueprints&sheet=${id}`, lod);
    await page.waitForFunction((n) => document.querySelector('.sheet-canvas svg')?.id?.endsWith(n) ?? true, String(i + 1).padStart(3, '0'));
    await page.waitForTimeout(500);
    await shot(page, viewport, `70_sheet_${String(i + 1).padStart(2, '0')}`);
  }
  await go(page, '#part=RJ28-15-031', lod);
  await page.keyboard.press('d');
  await page.waitForTimeout(900);
  await shot(page, viewport, '71_show_in_drawing');

  // ── Checks on the live model (desktop) ────────────────────────────────────
  if (!phone && !only) {
    await go(page, '', lod);
    const model = await page.evaluate(() => ({ count: window.rj28.scene.partCount(), numbers: window.rj28.scene.partNumbers(), stats: window.rj28.scene.stats() }));
    expect(model.count === parts.length, `GLB has ${model.count} part nodes, parts.json has ${parts.length}`);
    const have = new Set(model.numbers);
    const missing = numbers.filter((n) => !have.has(n));
    expect(missing.length === 0, `every part resolves to a node (missing: ${missing.slice(0, 5).join(', ')})`);
    const decals = new Set(parts.filter((p) => p.material_key === 'decal').map((p) => p.number));
    const unpickable = await page.evaluate((list) => list.filter((n) => !window.rj28.scene.pickable(n)), numbers.filter((n) => !decals.has(n)));
    expect(unpickable.length === 0, `every part is pickable at strip 0 (not: ${unpickable.slice(0, 5).join(', ')})`);
    console.log(`CHECK ${model.count} part nodes, ${numbers.length - decals.size} pickable, ${decals.size} markings selectable from the tree only`);

    // Keyboard map and the address.
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
    expect((await hash()) === '#mount=deployed', '0 resets the model but leaves the cannon where it is');
    for (const [key, tab] of [['2', 'dossier'], ['3', 'blueprints'], ['4', 'spec'], ['1', '']]) {
      await page.keyboard.press(key);
      const h = await hash();
      expect(tab ? h.includes(`tab=${tab}`) : !h.includes('tab='), `${key} opens the ${tab || 'model'} tab`);
    }
    // Stepping the tree reaches every part, and the scene follows the selection.
    await go(page, '#mount=stowed', lod);
    const seen = new Set();
    for (let i = 0; i < numbers.length; i++) {
      await page.keyboard.press('ArrowDown');
      seen.add(await page.evaluate(() => window.rj28.state().selected));
    }
    expect(seen.size === numbers.length, `stepping the tree reached ${seen.size} of ${numbers.length} parts`);
    console.log(`CHECK keyboard map, address sync, ${seen.size} of ${numbers.length} parts reachable from the tree`);

    // Frame pacing: turn the model for four seconds at full detail and resolution.
    await go(page, '', lod);
    const bench = await page.evaluate(() => window.rj28.scene.benchmark(4));
    console.log(
      `FRAME ${viewport.width}x${viewport.height} LOD${bench.lod} ${bench.triangles} triangles, ${bench.drawCalls} draw calls in the last pass: ` +
        `mean ${bench.frameMs.toFixed(1)} ms, worst ${bench.worstMs.toFixed(1)} ms, ${bench.cpuMs.toFixed(1)} ms of that issuing the frame, pixel ratio ${bench.pixelRatio.toFixed(2)}`,
    );
  }
  if (phone && !only) {
    await go(page, '', lod);
    const bench = await page.evaluate(() => window.rj28.scene.benchmark(3));
    console.log(`FRAME ${viewport.width}x${viewport.height} LOD${bench.lod} ${bench.triangles} triangles: mean ${bench.frameMs.toFixed(1)} ms, worst ${bench.worstMs.toFixed(1)} ms, pixel ratio ${bench.pixelRatio.toFixed(2)}`);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow <= 0, `no horizontal overflow on the phone (${overflow}px)`);
  }
  await page.close();

  // ── Static edition: no WebGL, or the model failed to load ─────────────────
  {
    const p = await open(context, '', '?static');
    await p.waitForTimeout(600);
    await shot(p, viewport, '80_static_model');
    await p.evaluate(() => (location.hash = '#tab=dossier&s=05'));
    await p.waitForTimeout(1500);
    await shot(p, viewport, '81_static_dossier');
    await p.close();
  }
  await context.close();
}

async function main() {
  if (!args.includes('--no-build')) {
    const built = spawnSync(process.execPath, [vite, 'build'], { cwd: site, stdio: 'inherit' });
    if (built.status !== 0) process.exit(built.status ?? 1);
  }
  if (!only) {
    // Keep the look-dev composites: they come from tests/lookdev.mjs.
    for (const f of existsSync(shots) ? readdirSync(shots) : []) if (!f.startsWith('lookdev_')) rmSync(join(shots, f));
  }
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
