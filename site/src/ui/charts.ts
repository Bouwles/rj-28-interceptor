// Small figures for the tour panels: spec tables, bar charts, the height
// ladder, the knee moment-arm plot and the design-note block. Plain marks in
// the text colours; the accent is not used here.

import { num, trim1 } from '../data/format';
import type { DesignNote } from '../data/types';
import { h, s, type Child } from './dom';

export type SpecRow = [label: string, value: Child, wrap?: boolean] | null | undefined | false | '';

export function specTable(rows: SpecRow[], caption?: string): HTMLElement {
  const dl = h(
    'dl.spec',
    null,
    rows.map((r) => r && h('div', null, h('dt', null, r[0]), h(r[2] ? 'dd.wrap' : 'dd', null, r[1]))),
  );
  return caption ? h('section.block', null, h('h3.cap', null, caption), dl) : dl;
}

export interface BarRow {
  label: string;
  value: number;
  /** Extra right-hand column, e.g. a part count. */
  extra?: string;
}

/** Horizontal bars on a common scale, as a real table so the values are readable without the bars. */
export function barChart(
  caption: string,
  rows: BarRow[],
  opts: { unit: string; digits: number; extraHead?: string; valueHead: string },
): HTMLElement {
  const max = Math.max(...rows.map((r) => r.value), 1e-9);
  return h(
    'section.block',
    null,
    h('h3.cap', null, caption),
    h(
      'table.bars',
      null,
      h(
        'thead.sr-only',
        null,
        h('tr', null, h('th', null, 'Item'), h('th', null, 'Share'), opts.extraHead && h('th', null, opts.extraHead), h('th', null, opts.valueHead)),
      ),
      h(
        'tbody',
        null,
        rows.map((r) =>
          h(
            'tr',
            null,
            h('th', { scope: 'row' }, r.label),
            h('td.bar', { 'aria-hidden': 'true' }, h('i', { style: { width: `${Math.max(0.4, (r.value / max) * 100).toFixed(2)}%` } })),
            opts.extraHead && h('td.data.faint', null, r.extra ?? ''),
            h('td.data', null, num(r.value, opts.digits), h('span.unit', null, ` ${opts.unit}`)),
          ),
        ),
      ),
    ),
  );
}

/** Heights from the floor, drawn to scale down a vertical rule. */
export function heightLadder(caption: string, rows: { label: string; mm: number }[]): HTMLElement {
  const sorted = [...rows].sort((a, b) => b.mm - a.mm);
  const top = sorted[0]?.mm ?? 1;
  return h(
    'section.block',
    null,
    h('h3.cap', null, caption),
    h(
      'ol.ladder',
      null,
      sorted.map((r) =>
        h(
          'li',
          { style: { top: `${((1 - r.mm / top) * 100).toFixed(3)}%` } },
          h('span.ladder-label', null, r.label),
          h('span.data', null, num(r.mm, 0), h('span.unit', null, ' mm')),
        ),
      ),
    ),
  );
}

/** Knee actuator moment arm against flexion: five measured points joined by straight segments. */
export function momentArmPlot(caption: string, points: Record<string, number>): HTMLElement {
  const pts = Object.entries(points)
    .map(([k, v]) => ({ x: Number(k), y: v }))
    .sort((a, b) => a.x - b.x);
  const xMax = pts[pts.length - 1]?.x ?? 1;
  const yTop = Math.ceil(Math.max(...pts.map((p) => p.y)) / 20) * 20;
  const px = (x: number) => (x / xMax) * 100;
  const py = (y: number) => (1 - y / yTop) * 100;
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${px(p.x).toFixed(2)} ${py(p.y).toFixed(2)}`).join('');
  const grid: string[] = [];
  for (let y = 0; y <= yTop; y += 20) grid.push(`M0 ${py(y)}H100`);
  return h(
    'section.block',
    null,
    h('h3.cap', null, caption),
    h(
      'figure.plot',
      null,
      h(
        'div.plot-area',
        null,
        s(
          'svg',
          { viewBox: '0 0 100 100', preserveAspectRatio: 'none', 'aria-hidden': 'true' },
          s('path.plot-grid', { d: grid.join('') }),
          s('path.plot-line', { d: line }),
        ),
        pts.map((p) =>
          h(
            'span.plot-pt',
            { style: { left: `${px(p.x)}%`, top: `${py(p.y)}%` } },
            h('span.data', null, trim1(p.y)),
          ),
        ),
        Array.from({ length: yTop / 20 + 1 }, (_, i) => i * 20).map((y) =>
          h('span.plot-y.data', { style: { top: `${py(y)}%` } }, String(y)),
        ),
      ),
      h(
        'div.plot-x',
        null,
        pts.map((p) => h('span.data', { style: { left: `${px(p.x)}%` } }, `${trim1(p.x)}°`)),
      ),
      h('figcaption', null, 'Moment arm in mm against knee flexion.'),
    ),
  );
}

/** A design note: the calculation written out line by line, then the conclusion. */
export function designNote(note: DesignNote, index: number): HTMLElement {
  return h(
    'section.note',
    null,
    h('header', null, h('span.cap', null, `Design note ${index + 1}`), h('h3', null, note.title)),
    h(
      'ol.note-working',
      null,
      // The data writes multiplication as a plain "x"; set it as a multiplication sign.
      note.working.map((line) => h('li', null, line.replace(/ x /g, ' × '))),
    ),
    h('p.note-verdict', null, note.verdict),
  );
}
