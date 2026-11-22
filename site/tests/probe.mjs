// Scratch probe used while developing; not part of the capture set.
// node tests/probe.mjs <hash> <out.png> [width] [height] [waitMs] [js-to-eval]
import { chromium } from 'playwright';

const base = process.env.BASE ?? 'http://localhost:4180/rj-28-interceptor/';
const hash = process.argv[2] ?? '';
const out = process.argv[3] ?? 'tests/shots/_probe.png';
const w = Number(process.argv[4] ?? 1920);
const h = Number(process.argv[5] ?? 1080);
const wait = Number(process.argv[6] ?? 2500);
const js = process.argv[7];
const browser = await chromium.launch({ channel: 'msedge' });
const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: w < 500 ? 2 : 1, isMobile: w < 500, hasTouch: w < 500 });
page.on('console', (m) => !/kaspersky/.test(m.text()) && console.log('console', m.type(), m.text().slice(0, 400)));
page.on('pageerror', (e) => console.log('pageerror', e.message));
page.on('requestfailed', (r) => !/kaspersky/.test(r.url()) && console.log('failed', r.url(), r.failure()?.errorText));
page.on('response', (r) => r.status() >= 400 && console.log('http', r.status(), r.url()));
const t0 = Date.now();
await page.goto(base + hash);
try {
  await page.waitForSelector('.loader', { state: 'detached', timeout: 40000 });
  console.log('loader gone after', Date.now() - t0, 'ms');
} catch {
  console.log('loader still up');
}
await page.waitForTimeout(wait);
if (js) console.log('eval:', JSON.stringify(await page.evaluate(js)));
await page.waitForTimeout(js ? 800 : 0);
await page.screenshot({ path: out });
console.log(await page.evaluate(() => JSON.stringify({ ds: { ...document.body.dataset }, hash: location.hash, stats: window.rj28?.scene.stats?.() })));
await browser.close();
