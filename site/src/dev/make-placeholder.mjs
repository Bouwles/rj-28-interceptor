// Writes a stand-in drawing set so the sheet viewer still works in a checkout
// where the real set has not been exported: `npm run placeholder`.
//
// It follows the contract of the exported sheets (line classes, `--ink` and
// `--paper`, `<g data-part>` groups, `.bal` balloons, and a sheets.json whose
// `parts` map a part number or assembly id to places) but is drawn from the
// part bounding boxes in parts.json only. Output stays in src/dev/placeholder/
// and is left out of the build whenever src/data/sheets.json exists.

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const data = join(here, '..', 'data');
const out = join(here, 'placeholder');
const parts = JSON.parse(readFileSync(join(data, 'parts.json'), 'utf8'));
const spec = JSON.parse(readFileSync(join(data, 'spec.json'), 'utf8'));

const W = 420;
const H = 297;
const f = (n) => Number(n.toFixed(2));

const STYLE =
  'svg{--ink:#000;--paper:#fff}.paper{fill:var(--paper)}' +
  'path,line,circle,polyline,rect{fill:none;stroke:var(--ink);stroke-linecap:round;stroke-linejoin:round}' +
  '.vis{stroke-width:.38}.det{stroke-width:.15}.hid{stroke-width:.15;stroke-dasharray:1.8 .9}' +
  '.ctr{stroke-width:.13;stroke-dasharray:6 1.1 .7 1.1}.dim{stroke-width:.15}.frame{stroke-width:.7}' +
  '.rule{stroke-width:.25}.bal circle{fill:var(--paper);stroke-width:.25}.bal{cursor:pointer}' +
  'text{fill:var(--ink);stroke:none;font-family:"IBM Plex Mono",monospace;font-size:2.7px}';

function sheet(number, title, scale, body) {
  const x = W - 160;
  const y = H - 40;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}mm" height="${H}mm" id="${number}">
<title>${number} ${title}</title>
<style>${STYLE}</style>
<rect class="paper" width="${W}" height="${H}"/>
<path class="frame" d="M10 10H${W - 10}V${H - 10}H10Z"/>
${body}
<path class="rule" d="M${x} ${y}H${W - 10}M${x} ${y}V${H - 10}M${x} ${y + 10}H${W - 10}M${x} ${y + 20}H${W - 10}"/>
<text x="${x + 3}" y="${y + 6.5}">${spec.designation}</text>
<text x="${x + 3}" y="${y + 16.5}">${title.toUpperCase()}</text>
<text x="${x + 3}" y="${y + 26.5}">${number}  SCALE ${scale}  STAND-IN, BOUNDING BOXES ONLY</text>
</svg>
`;
}

const rect = (x, y, w, h) => `M${f(x)} ${f(y)}h${f(w)}v${f(h)}h${f(-w)}z`;
const klass = (p) => (p.material_class === 'armour' ? 'vis' : p.material_class === 'structure' || p.material_class === 'actuator' ? 'det' : 'hid');
const drawn = (p) => p.count === 1 && p.material_class !== 'harness' && p.material_key !== 'decal';

function balloon(attr, value, label, bx, by, tx, ty) {
  return `<g class="bal" ${attr}="${value}" data-item="${label}"><path class="dim" d="M${f(tx)} ${f(ty)}L${f(bx)} ${f(by)}"/><circle class="rule" cx="${f(bx)}" cy="${f(by)}" r="4.2"/><text x="${f(bx)}" y="${f(by + 0.95)}" text-anchor="middle">${label}</text></g>`;
}

// Sheet 1: front and right side at 1:10, one balloon per assembly.
function generalArrangement() {
  const k = 0.1;
  const floor = 245;
  const views = { 's1-front': { ox: 120, u: (p) => p[0] }, 's1-right': { ox: 290, u: (p) => -p[1] } };
  const index = {};
  let body = '';
  for (const [id, v] of Object.entries(views)) {
    body += `<g id="${id}" class="view">`;
    for (const p of parts) {
      const u1 = v.u(p.bbox_min);
      const u2 = v.u(p.bbox_max);
      const x = v.ox + Math.min(u1, u2) * k;
      const w = Math.abs(u2 - u1) * k;
      const y = floor - p.bbox_max[2] * k;
      const h = (p.bbox_max[2] - p.bbox_min[2]) * k;
      (index[p.number] ??= []).push({ v: id, x: f(x + w / 2), y: f(y + h / 2), w: f(w), h: f(h) });
      if (drawn(p)) body += `<g data-part="${p.number}"><path class="${klass(p)}" d="${rect(x, y, w, h)}"/></g>`;
    }
    body += `<path class="vis" d="M${v.ox - 60} ${floor}h120"/><path class="ctr" d="M${v.ox} ${floor - 212}V${floor + 6}"/></g>`;
  }
  const groups = new Map();
  for (const p of parts) {
    const g = groups.get(p.assembly) ?? { x: 0, z: 0, n: 0 };
    g.x += (p.bbox_min[0] + p.bbox_max[0]) / 2;
    g.z += (p.bbox_min[2] + p.bbox_max[2]) / 2;
    g.n += 1;
    groups.set(p.assembly, g);
  }
  const sides = { left: [], right: [] };
  for (const [id, g] of [...groups].sort()) (g.x / g.n < 0 ? sides.left : sides.right).push({ id, x: g.x / g.n, z: g.z / g.n });
  for (const [side, list] of Object.entries(sides)) {
    list.sort((a, b) => b.z - a.z);
    list.forEach((b, i) => {
      const bx = side === 'left' ? 38 : 202;
      const by = 40 + i * (190 / Math.max(1, list.length - 1));
      const tx = views['s1-front'].ox + b.x * k;
      const ty = floor - b.z * k;
      body += balloon('data-assembly', b.id, b.id, bx, by, tx, ty);
      (index[b.id] ??= []).push({ v: 's1-front', x: bx, y: f(by), w: 8.4, h: 8.4, b: 1, tx: f(tx), ty: f(ty) });
    });
  }
  return { svg: sheet('RJ28-GA-001', 'General arrangement', '1:10', body), parts: index };
}

// Sheet 3: the mount from the right at 1:4, a balloon on each of the heaviest parts.
function mount() {
  const k = 0.25;
  const list = parts.filter((p) => p.assembly === '15');
  const [, y0, z0] = spec.mount.trunnion;
  const index = {};
  let body = '<g id="s3-right" class="view">';
  for (const p of list) {
    const x = 190 - (p.bbox_max[1] - y0) * k;
    const w = (p.bbox_max[1] - p.bbox_min[1]) * k;
    const y = 170 - (p.bbox_max[2] - z0) * k;
    const h = (p.bbox_max[2] - p.bbox_min[2]) * k;
    index[p.number] = [{ v: 's3-right', x: f(x + w / 2), y: f(y + h / 2), w: f(w), h: f(h) }];
    if (drawn(p)) body += `<g data-part="${p.number}"><path class="${p.mass_kg > 0.3 ? 'vis' : 'det'}" d="${rect(x, y, w, h)}"/></g>`;
  }
  body += `<path class="ctr" d="M120 170h140M190 20v190"/><circle class="ctr" cx="190" cy="170" r="${f(spec.mount.bore_rise * k)}"/></g>`;
  const heavy = list.filter(drawn).sort((a, b) => b.mass_kg - a.mass_kg).slice(0, 12);
  heavy.sort((a, b) => index[a.number][0].y - index[b.number][0].y);
  heavy.forEach((p, i) => {
    const at = index[p.number][0];
    const bx = i % 2 === 0 ? 70 : 320;
    const by = 36 + Math.floor(i / 2) * 34;
    const label = p.number.slice(-3);
    body += balloon('data-part', p.number, label, bx, by, at.x, at.y);
    index[p.number].push({ v: 's3-right', x: bx, y: by, w: 8.4, h: 8.4, b: 1, tx: at.x, ty: at.y });
  });
  return { svg: sheet('RJ28-GA-003', 'Interceptor cannon and mount', '1:4', body), parts: index };
}

mkdirSync(out, { recursive: true });
const ga = generalArrangement();
const mt = mount();
writeFileSync(join(out, 'RJ28-GA-001.svg'), ga.svg);
writeFileSync(join(out, 'RJ28-GA-003.svg'), mt.svg);
writeFileSync(
  join(out, 'sheets.json'),
  JSON.stringify({
    note: 'Stand-in set written by src/dev/make-placeholder.mjs, in the shape of the exported sheets.json.',
    sheets: [
      { id: 'ga-001', number: 'RJ28-GA-001', title: 'General arrangement', file: 'RJ28-GA-001.svg', width: W, height: H, scale: '1:10', parts: ga.parts },
      { id: 'ga-003', number: 'RJ28-GA-003', title: 'Interceptor cannon and mount', file: 'RJ28-GA-003.svg', width: W, height: H, scale: '1:4', parts: mt.parts },
    ],
  }),
);
console.log(`stand-in sheets written to ${out}`);
