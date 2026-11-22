import { spec } from '../data';
import { megabytes } from '../data/format';
import type { LoadProgress } from '../loader/assets';
import { h, prefersReducedMotion } from './dom';
import { prepareSheet } from './svg-inline';

/** Shortest time the drawing takes to complete, so a cached load still reads as a drawing being made. */
const MIN_DRAW_MS = 1300;
const GEOMETRY = 'path, line, polyline, polygon, rect, circle, ellipse';

interface Stroke {
  el: SVGGeometryElement | SVGTextElement;
  length: number; // 0 → revealed by opacity instead of by stroke
}

export interface LoaderScreen {
  el: HTMLElement;
  /** Give it the general-arrangement sheet to draw. */
  setDrawing(svgText: string, title: string): void;
  setProgress(p: LoadProgress): void;
  /** Everything is in: finish the drawing, then clear the screen. */
  finish(): Promise<void>;
}

/**
 * Loading screen: the general-arrangement sheet draws itself, and how much of
 * it is drawn is how much has arrived. The figure is bytes received over bytes
 * to fetch, both real.
 */
export function createLoader(): LoaderScreen {
  const reduced = prefersReducedMotion();
  const sheetBox = h('div.loader-sheet', { 'aria-hidden': 'true' });
  const sheetName = h('span.tb-val');
  const file = h('span.tb-val.data', null, '—');
  const bytes = h('span.tb-val.data', null, '—');
  const rule = h('i');
  const el = h(
    'div.loader',
    { role: 'status', 'aria-label': 'Loading' },
    sheetBox,
    h(
      'div.loader-strip',
      null,
      h('div.tb-cell.tb-title', null, h('span.cap', null, 'Designation'), h('span.tb-val.tb-name', null, spec.designation)),
      h('div.tb-cell.loader-sheetname', null, h('span.cap', null, 'Drawing'), sheetName),
      h('div.tb-cell.loader-file', null, h('span.cap', null, 'Receiving'), file),
      h('div.tb-cell.loader-bytes', null, h('span.cap', null, 'Received, MB'), bytes),
    ),
    h('div.loader-rule', { 'aria-hidden': 'true' }, rule),
  );

  let strokes: Stroke[] = [];
  let target = 0;
  let shown = 0;
  let done = 0; // strokes[0..done) are fully drawn
  let last = performance.now();
  let raf = 0;
  let finished: (() => void) | null = null;

  const WINDOW = () => Math.max(12, strokes.length * 0.06);

  function paint(): void {
    rule.style.transform = `scaleX(${shown.toFixed(4)})`;
    const n = strokes.length;
    if (!n) return;
    const win = WINDOW();
    const head = shown * (n + win);
    for (let i = done; i < n && i <= head; i++) {
      const st = strokes[i]!;
      const local = Math.min(1, (head - i) / win);
      if (st.length > 0) {
        (st.el as SVGElement).style.strokeDashoffset = String(st.length * (1 - local));
        if (local >= 1) (st.el as SVGElement).style.fillOpacity = '';
      } else {
        (st.el as SVGElement).style.opacity = String(local);
      }
      if (local >= 1 && i === done) done += 1;
    }
  }

  function settle(): void {
    for (const st of strokes) {
      const style = (st.el as SVGElement).style;
      style.strokeDasharray = '';
      style.strokeDashoffset = '';
      style.fillOpacity = '';
      style.opacity = '';
    }
    strokes = [];
  }

  function tick(now: number): void {
    const dt = Math.min(64, now - last);
    last = now;
    if (reduced) shown = target;
    else shown = Math.min(target, shown + dt / MIN_DRAW_MS);
    paint();
    if (shown >= 1 && finished) {
      settle();
      const resolve = finished;
      finished = null;
      window.setTimeout(resolve, reduced ? 0 : 240);
      return;
    }
    raf = requestAnimationFrame(tick);
  }
  raf = requestAnimationFrame(tick);

  return {
    el,
    setDrawing(svgText, title) {
      const prepared = prepareSheet(svgText);
      if (!prepared) return;
      sheetName.textContent = title;
      sheetBox.appendChild(prepared.svg);
      if (reduced) return;
      const list: Stroke[] = [];
      const nodes = prepared.svg.querySelectorAll<SVGGeometryElement | SVGTextElement>(`${GEOMETRY}, text`);
      for (const node of nodes) {
        if (node.classList.contains('sheet-paper') || node.closest('defs, clipPath, pattern, marker, mask')) continue;
        const style = (node as SVGElement).style;
        let length = 0;
        if (!(node instanceof SVGTextElement)) {
          const cs = getComputedStyle(node);
          const dashed = cs.strokeDasharray !== 'none' && cs.strokeDasharray !== '';
          if (cs.stroke !== 'none' && !dashed) {
            try {
              length = node.getTotalLength();
            } catch {
              length = 0;
            }
          }
        }
        if (length > 0) {
          style.strokeDasharray = `${length} ${length}`;
          style.strokeDashoffset = String(length);
          style.fillOpacity = '0';
        } else {
          style.opacity = '0';
        }
        list.push({ el: node, length });
      }
      strokes = list;
      done = 0;
      paint();
    },
    setProgress(p) {
      target = p.total > 0 ? Math.min(1, p.loaded / p.total) : 0;
      file.textContent = p.current || (p.filesDone < p.filesTotal ? '—' : 'complete');
      bytes.textContent = p.total > 0 ? `${megabytes(p.loaded)} / ${megabytes(p.total)}` : '—';
    },
    finish() {
      target = 1;
      return new Promise<void>((resolve) => {
        finished = () => {
          cancelAnimationFrame(raf);
          el.classList.add('loader-out');
          window.setTimeout(
            () => {
              el.remove();
              resolve();
            },
            reduced ? 0 : 380,
          );
        };
      });
    },
  };
}
