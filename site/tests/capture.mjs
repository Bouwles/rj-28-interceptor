// Builds the site, serves the build under the Pages base path, and captures
// every screen that exists at 1920x1080 and 390x844 into tests/shots/.
//
//   node tests/capture.mjs            build, serve, capture
//   node tests/capture.mjs --no-build reuse the existing dist/
//   node tests/capture.mjs --only=inspect   capture shots whose name contains a string
//
// Uses the installed Microsoft Edge (Playwright channel `msedge`); no browser
// download is needed. Exits non-zero if the page logs a console error, a
// request fails, or anything is fetched from another origin.

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

const VIEWPORTS = [
  { name: 'desktop', width: 1920, height: 1080, deviceScaleFactor: 1, isMobile: false },
  { name: 'phone', width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitForServer() {
  for (let i = 0; i < 80; i++) {
    try {
      const res = await fetch(BASE);
      if (res.ok) return;
    } catch {
      // not up yet
    }
    await sleep(150);
  }
  throw new Error('preview server did not start');
}

const problems = [];
const notes = new Set();
const INJECTED = /^https?:\/\/[^/]*kaspersky-labs\.com\//;

/** Checks on the built files themselves: nothing external, card metadata, data in step. */
function checkBuild() {
  const dist = join(site, 'dist');
  const html = readFileSync(join(dist, 'index.html'), 'utf8');
  if (!/og:image" content="https?:\/\/[^"]+\/rj-28-interceptor\/renders\/social_card\.jpg"/.test(html)) {
    problems.push('og:image is not an absolute URL under the base path');
  }
  const texts = [html, ...readdirSync(join(dist, 'assets')).filter((f) => /\.(js|css)$/.test(f)).map((f) => readFileSync(join(dist, 'assets', f), 'utf8'))];
  for (const text of texts) {
    // Any URL that is fetched: src/href attributes, CSS url(), fetch/import of an absolute address.
    const fetched = text.match(/(?:src|href)=["']https?:\/\/[^"']+|url\(["']?https?:\/\/[^)"']+|(?:fetch|import)\(["'`]https?:\/\/[^"'`]+/g) ?? [];
    for (const m of fetched) {
      // The page's own canonical address is the one absolute link it carries.
      if (!m.includes('/rj-28-interceptor/')) problems.push(`build references an external address: ${m}`);
    }
  }
  const data = join(site, 'src', 'data');
  const parts = JSON.parse(readFileSync(join(data, 'parts.json'), 'utf8'));
  const spec = JSON.parse(readFileSync(join(data, 'spec.json'), 'utf8'));
  if (parts.length !== spec.part_count) problems.push(`parts.json has ${parts.length} parts, spec.json says ${spec.part_count}`);
  if (new Set(parts.map((p) => p.number)).size !== parts.length) problems.push('part numbers are not unique');
  if (existsSync(join(data, 'model.json'))) {
    const model = JSON.parse(readFileSync(join(data, 'model.json'), 'utf8'));
    const nodes = model.files?.lod0?.part_nodes;
    if (nodes !== undefined && nodes !== parts.length) problems.push(`GLB has ${nodes} part nodes, parts.json has ${parts.length}`);
  }
}

async function open(context, hash = '', query = '') {
  const page = await context.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') problems.push(`console ${msg.type()}: ${msg.text()}`);
  });
  page.on('pageerror', (err) => problems.push(`page error: ${err.message}`));
  page.on('requestfailed', (req) => problems.push(`request failed: ${req.url()} ${req.failure()?.errorText ?? ''}`));
  page.on('response', (res) => {
    if (res.status() >= 400) problems.push(`HTTP ${res.status()}: ${res.url()}`);
  });
  page.on('request', (req) => {
    const url = req.url();
    if (url.startsWith(`http://localhost:${PORT}/`) || url.startsWith('data:') || url.startsWith('blob:')) return;
    // Some desktop security suites inject a script into every plain-HTTP page
    // on the machine. It is not in the build (checked below), so it is noted
    // and not counted against the site.
    if (INJECTED.test(url)) notes.add(`ignored a script injected by local security software (${new URL(url).host})`);
    else problems.push(`external request: ${url}`);
  });
  await page.goto(`${BASE}${query}${hash}`);
  await page.waitForSelector('.loader', { state: 'detached', timeout: 30000 });
  await page.evaluate(() => document.fonts.ready);
  return page;
}

async function settle(page, ms = 700) {
  // Images still decoding would be captured as blanks.
  // Lazy images outside the viewport never load, so they are not waited for.
  await page.evaluate(async () => {
    const imgs = [...document.images].filter((i) => i.src && !i.complete && i.loading !== 'lazy');
    const loaded = Promise.all(imgs.map((i) => new Promise((r) => ((i.onload = r), (i.onerror = r)))));
    await Promise.race([loaded, new Promise((r) => setTimeout(r, 8000))]);
  });
  await page.waitForTimeout(ms);
}

async function shot(page, viewport, name) {
  if (only && !name.includes(only)) return;
  const file = join(shots, `${viewport.name}_${name}.png`);
  await page.screenshot({ path: file });
  console.log(`SHOT ${viewport.name}_${name}.png`);
}

async function capture(browser, viewport) {
  const { name: _n, ...size } = viewport;
  const context = await browser.newContext({
    viewport: { width: size.width, height: size.height },
    deviceScaleFactor: size.deviceScaleFactor,
    isMobile: size.isMobile,
    hasTouch: size.hasTouch ?? false,
    reducedMotion: 'no-preference',
  });
  const phone = viewport.name === 'phone';

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
    await page.waitForSelector('.loader', { state: 'detached', timeout: 30000 });
    await page.close();
  }

  // ── Tour: every section, at the point where its panel is being read ──────
  {
    const page = await open(context);
    await settle(page, 900);
    await shot(page, viewport, '01_tour_00_title');
    const count = await page.locator('.tour-section').count();
    for (let i = 1; i < count; i++) {
      await page.evaluate(
        ([index, isPhone]) => {
          const el = document.querySelectorAll('.tour-section')[index];
          const panel = el.querySelector('.panel') ?? el;
          const top = panel.getBoundingClientRect().top + window.scrollY;
          // Desktop: panel near the top of the stage. Phone: panel risen to mid-screen, plate still in view.
          window.scrollTo(0, top - (isPhone ? window.innerHeight * 0.52 : 150));
        },
        [i, phone],
      );
      await settle(page, 900);
      const id = String(i).padStart(2, '0');
      const label = (await page.locator('.tour-section').nth(i).getAttribute('aria-label')).toLowerCase().replace(/[^a-z]+/g, '-');
      await shot(page, viewport, `01_tour_${id}_${label}`);
    }
    // The long panels: capture what is below the fold too.
    for (const i of [1, 5, 7]) {
      await page.evaluate((index) => {
        const panel = document.querySelectorAll('.tour-section')[index].querySelector('.panel');
        const r = panel.getBoundingClientRect();
        window.scrollTo(0, r.bottom + window.scrollY - window.innerHeight + 90);
      }, i);
      await settle(page, 700);
      await shot(page, viewport, `01_tour_${String(i).padStart(2, '0')}_lower`);
    }
    await page.close();
  }

  // ── Inspector ─────────────────────────────────────────────────────────────
  {
    const page = await open(context, '#mode=inspect');
    await settle(page);
    await shot(page, viewport, '02_inspect_empty');
    if (phone) {
      await page.locator('.bb-drawer').click();
      await page.waitForTimeout(400);
      await shot(page, viewport, '02_inspect_drawer');
      await page.locator('.tree-search').fill('actuator');
      await page.waitForTimeout(300);
      await shot(page, viewport, '02_inspect_drawer_search');
      await page.locator('.tree-close').click();
    } else {
      await page.locator('.tree-search').fill('trunnion');
      await page.waitForTimeout(300);
      await shot(page, viewport, '02_inspect_search');
      await page.locator('.tree-search').fill('');
    }
    await page.close();
  }
  {
    const page = await open(context, '#mode=inspect&part=RJ28-15-006&mount=deployed');
    await settle(page);
    await shot(page, viewport, '02_inspect_selected_deployed');
    await page.close();
  }
  {
    const page = await open(context, '#mode=inspect&part=RJ28-03-062&xray=1');
    await settle(page);
    await shot(page, viewport, '02_inspect_xray');
    await page.close();
  }
  if (!phone) {
    const page = await open(context, '#mode=inspect&part=RJ28-11-004');
    await page.keyboard.press('r');
    const box = await page.locator('.stage-boxes .boxmodel').first().boundingBox();
    await page.mouse.click(box.x + box.width * 0.36, box.y + box.height * 0.3);
    await page.mouse.click(box.x + box.width * 0.64, box.y + box.height * 0.3);
    await settle(page, 300);
    await shot(page, viewport, '02_inspect_measure');
    await page.keyboard.press('Escape');
    await page.keyboard.press('?');
    await page.waitForTimeout(300);
    await shot(page, viewport, '02_help');
    await page.close();
  }

  // ── Exploded view ─────────────────────────────────────────────────────────
  for (const pct of [50, 100]) {
    const page = await open(context, `#mode=explode&explode=${pct}`);
    await settle(page, 900);
    await shot(page, viewport, `03_explode_${pct}`);
    await page.close();
  }

  // ── Blueprint: each snap view ─────────────────────────────────────────────
  for (const view of ['front', 'side', 'rear', 'top', 'iso']) {
    const page = await open(context, `#mode=blueprint&view=${view}${view === 'side' ? '&mount=deployed' : ''}`);
    await settle(page);
    await shot(page, viewport, `04_blueprint_${view}`);
    await page.close();
  }

  // ── Sheet viewer: every sheet, then "show in drawing" ─────────────────────
  {
    const page = await open(context, '#mode=blueprint');
    const ids = await page.evaluate(() => [...document.querySelectorAll('.sheet-index-item')].map((b) => b.dataset.id));
    await page.close();
    for (const [i, id] of ids.entries()) {
      const p = await open(context, `#mode=blueprint&sheet=${id}`);
      await p.waitForSelector('.sheet-canvas svg');
      await settle(p, 900);
      await shot(p, viewport, `05_sheet_${String(i + 1).padStart(2, '0')}`);
      await p.close();
    }
  }
  {
    const page = await open(context, '#mode=inspect&part=RJ28-15-031');
    await page.keyboard.press('d');
    await page.waitForSelector('.sheet-canvas svg');
    await settle(page, 900);
    await shot(page, viewport, '05_sheet_show_in_drawing');
    if (!phone) {
      // Zoom in and pick a part on the sheet.
      const box = await page.locator('.sheet-canvas').boundingBox();
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.wheel(0, -600);
      await page.waitForTimeout(300);
      await page.mouse.click(box.x + box.width / 2 + 60, box.y + box.height / 2 + 20);
      await page.waitForTimeout(300);
      await page.mouse.move(box.x + box.width / 2 - 90, box.y + box.height / 2 - 40);
      await page.waitForTimeout(300);
      await shot(page, viewport, '05_sheet_zoom_pick');
    }
    await page.close();
  }

  // ── Reduced motion, and the forced static edition ─────────────────────────
  {
    const reduced = await browser.newContext({
      viewport: { width: size.width, height: size.height },
      deviceScaleFactor: size.deviceScaleFactor,
      isMobile: size.isMobile,
      hasTouch: size.hasTouch ?? false,
      reducedMotion: 'reduce',
    });
    const page = await open(reduced, '#s=06', '?static');
    await settle(page);
    await shot(page, viewport, '06_static_reduced_motion_s06');
    await reduced.close();
  }

  // ── Behaviour: keyboard map, address sync, every part reachable ───────────
  if (!phone && !only) {
    const page = await open(context, '#mode=inspect');
    const hash = async () => {
      await page.waitForTimeout(80);
      return page.evaluate(() => location.hash);
    };
    const expect = (ok, what) => ok || problems.push(`behaviour: ${what}`);
    const parts = JSON.parse(readFileSync(join(site, 'src', 'data', 'parts.json'), 'utf8'))
      .map((p) => p.number)
      .sort();

    await page.keyboard.press('ArrowDown');
    expect((await hash()).includes(`part=${parts[0]}`), 'arrow down selects the first part');
    await page.keyboard.press('m');
    expect((await hash()).includes('mount=deployed'), 'M deploys the mount');
    await page.keyboard.press('x');
    expect((await hash()).includes('xray=1'), 'X turns x-ray on');
    await page.keyboard.press('e');
    expect(/mode=explode.*explode=50/.test(await hash()), 'E opens the exploded view at 50%');
    await page.keyboard.press('b');
    expect((await hash()).includes('mode=blueprint'), 'B opens blueprint');
    await page.keyboard.press('d');
    expect((await hash()).includes('sheet='), 'D shows the selected part in a drawing');
    await page.keyboard.press('Escape');
    expect(!(await hash()).includes('sheet='), 'Esc closes the sheet viewer');
    await page.keyboard.press('Escape');
    expect(!(await hash()).includes('part='), 'Esc clears the selection');
    await page.keyboard.press('t');
    expect(!(await hash()).includes('mode='), 'T returns to the tour');

    // An edited address is applied without a reload.
    await page.evaluate((n) => (location.hash = `#mode=inspect&part=${n}`), parts[parts.length - 1]);
    await page.waitForTimeout(150);
    expect((await page.locator('.detail-no').textContent()) === parts[parts.length - 1], 'a part link selects that part');

    // Step through the whole tree: every part in parts.json must be reachable.
    await page.evaluate(() => (location.hash = '#mode=inspect'));
    await page.waitForTimeout(150);
    const seen = new Set();
    for (let i = 0; i < parts.length; i++) {
      await page.keyboard.press('ArrowDown');
      seen.add(await page.evaluate(() => document.querySelector('.detail-no')?.textContent));
    }
    expect(seen.size === parts.length && parts.every((n) => seen.has(n)), `stepping the tree reached ${seen.size} of ${parts.length} parts`);
    const count = await page.locator('.tree-count').textContent();
    expect(count.replace(/,/g, '').startsWith(`${parts.length} parts`), `tree count reads "${count}"`);
    console.log(`CHECK keyboard map, address sync, ${seen.size} of ${parts.length} parts selectable`);
    await page.close();
  }

  // ── No horizontal scroll anywhere in the tour ─────────────────────────────
  {
    const page = await open(context);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (overflow > 0) problems.push(`${viewport.name}: page is ${overflow}px wider than the viewport`);
    await page.close();
  }

  await context.close();
}

async function main() {
  if (!args.includes('--no-build')) {
    const built = spawnSync(process.execPath, [vite, 'build'], { cwd: site, stdio: 'inherit' });
    if (built.status !== 0) process.exit(built.status ?? 1);
  }
  if (!only) rmSync(shots, { recursive: true, force: true });
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
  console.log('\nCapture complete: console clean, no failed or external requests.');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
