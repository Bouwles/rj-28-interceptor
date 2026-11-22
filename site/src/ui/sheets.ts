import { isolate, openSheet, select, selectAndInspect, setTab, type App } from '../app/context';
import { bestPlace } from '../data';
import { num, pad2 } from '../data/format';
import type { Sheet, SheetPlace } from '../data/types';
import { clearNode, fill, h, s } from './dom';
import { prepareSheet, type PreparedSheet } from './svg-inline';

const cache = new Map<string, Promise<string>>();

export function sheetText(sheet: Sheet): Promise<string> {
  let p = cache.get(sheet.url);
  if (!p) {
    p = fetch(sheet.url).then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.text();
    });
    p.catch(() => cache.delete(sheet.url));
    cache.set(sheet.url, p);
  }
  return p;
}

/** Seed the cache with text the loader already fetched. */
export function primeSheet(sheet: Sheet, text: string): void {
  cache.set(sheet.url, Promise.resolve(text));
}

interface ViewState {
  cx: number; // sheet units at the centre of the viewport
  cy: number;
  k: number; // CSS pixels per sheet unit
}

interface Target {
  key: string; // part number or assembly id
  place: SheetPlace;
  area: number;
}

const isAssemblyKey = (key: string) => /^\d\d$/.test(key);

/**
 * Sheet viewer. Pan and zoom move the SVG viewBox, not a CSS transform, so the
 * browser redraws the vector line work at every scale and it stays sharp.
 * Picking uses the part places recorded in sheets.json: the smallest box under
 * the pointer wins, so a screw inside a housing can still be picked.
 */
export function buildSheetViewer(app: App): HTMLElement {
  const { store } = app;
  const sheets = app.sheets?.sheets ?? [];

  let current: { sheet: Sheet; prepared: PreparedSheet; targets: Target[]; sx: number; sy: number } | null = null;
  let view: ViewState = { cx: 0, cy: 0, k: 1 };
  let fitK = 1;
  let loadToken = 0;
  let hoverKey: string | null = null;
  const marker = s('rect.sheet-marker');

  const indexButtons = sheets.map((sh, i) =>
    h(
      'button.sheet-index-item',
      { type: 'button', dataset: { id: sh.id }, onclick: () => openSheet(app, sh.id) },
      h('span.data', null, `${pad2(i + 1)}  ${sh.number}`),
      h('span', null, sh.title),
      sh.scale ? h('span.data.sheet-scale', null, sh.scale) : null,
    ),
  );
  const zoomOut = h('output.tool-readout.data', { 'aria-label': 'Zoom' });
  const canvas = h('div.sheet-canvas', { tabindex: '0', role: 'img', 'aria-label': 'Drawing sheet' });
  const message = h('p.sheet-message', { hidden: true });
  const callout = h('div.sheet-callout', { hidden: true, 'aria-live': 'polite' });

  const viewer = h(
    'section.sheets',
    { hidden: true, role: 'region', 'aria-label': 'Drawing sheets' },
    h(
      'aside.sheets-index',
      null,
      h('h2.cap', null, 'Drawing set'),
      h('ol', null, indexButtons.map((b) => h('li', null, b))),
      app.sheets?.pdfUrl ? h('a.btn', { href: app.sheets.pdfUrl, download: '' }, 'Download the set, PDF') : null,
      h('p.advice', null, 'Drag to pan, scroll to zoom. Pick a part or a balloon to select it.'),
      app.sheets?.placeholder
        ? h('p.advice', null, 'Stand-in sheets drawn from part bounding boxes. The exported drawing set replaces them.')
        : null,
    ),
    h(
      'div.sheets-main',
      null,
      h(
        'div.sheets-bar',
        null,
        h(
          'div.seg',
          { role: 'group', 'aria-label': 'Zoom' },
          h('button.btn', { type: 'button', 'aria-label': 'Zoom out', onclick: () => zoomBy(1 / 1.5) }, '−'),
          h('button.btn', { type: 'button', 'aria-label': 'Zoom in', onclick: () => zoomBy(1.5) }, '+'),
          h('button.btn', { type: 'button', onclick: () => fit() }, 'Fit', h('kbd', null, '0')),
        ),
        zoomOut,
      ),
      canvas,
      message,
      callout,
    ),
  );

  // ── View ──────────────────────────────────────────────────────────────────
  function apply(): void {
    if (!current) return;
    const w = canvas.clientWidth;
    const hgt = canvas.clientHeight;
    if (!w || !hgt) return;
    const vw = w / view.k;
    const vh = hgt / view.k;
    current.prepared.svg.setAttribute('viewBox', `${view.cx - vw / 2} ${view.cy - vh / 2} ${vw} ${vh}`);
    zoomOut.textContent = `${num((view.k / fitK) * 100, 0)}%`;
  }

  function measureFit(): void {
    if (!current) return;
    const { box } = current.prepared;
    const pad = canvas.clientWidth < 600 ? 12 : 32;
    fitK = Math.min((canvas.clientWidth - pad * 2) / box.width, (canvas.clientHeight - pad * 2) / box.height);
    if (!(fitK > 0)) fitK = 1;
  }

  function fit(): void {
    if (!current) return;
    measureFit();
    const { box } = current.prepared;
    view = { cx: box.x + box.width / 2, cy: box.y + box.height / 2, k: fitK };
    apply();
  }

  function zoomAt(factor: number, clientX?: number, clientY?: number): void {
    if (!current) return;
    const rect = canvas.getBoundingClientRect();
    const px = (clientX ?? rect.left + rect.width / 2) - rect.left - rect.width / 2;
    const py = (clientY ?? rect.top + rect.height / 2) - rect.top - rect.height / 2;
    const k = Math.min(fitK * 64, Math.max(fitK * 0.5, view.k * factor));
    // Keep the sheet point under the pointer where it is.
    view.cx += px / view.k - px / k;
    view.cy += py / view.k - py / k;
    view.k = k;
    apply();
  }
  const zoomBy = (factor: number) => zoomAt(factor);

  function pan(dxPx: number, dyPx: number): void {
    view.cx -= dxPx / view.k;
    view.cy -= dyPx / view.k;
    apply();
  }

  /** Pointer position in the units of sheets.json. */
  function toSheet(clientX: number, clientY: number): [number, number] | null {
    if (!current) return null;
    const rect = canvas.getBoundingClientRect();
    const ux = view.cx + (clientX - rect.left - rect.width / 2) / view.k;
    const uy = view.cy + (clientY - rect.top - rect.height / 2) / view.k;
    const { box } = current.prepared;
    return [(ux - box.x) / current.sx, (uy - box.y) / current.sy];
  }

  function hit(clientX: number, clientY: number): Target | null {
    const pt = toSheet(clientX, clientY);
    if (!pt || !current) return null;
    const slack = 3 / (view.k * current.sx); // three pixels of forgiveness for thin parts
    let assembly: Target | null = null;
    for (const t of current.targets) {
      const { x, y, w, h: hh } = t.place;
      if (Math.abs(pt[0] - x) > w / 2 + slack || Math.abs(pt[1] - y) > hh / 2 + slack) continue;
      if (t.place.balloon || !isAssemblyKey(t.key)) return t; // sorted smallest first
      assembly ??= t;
    }
    return assembly;
  }

  function groupsFor(key: string): NodeListOf<Element> {
    const attr = isAssemblyKey(key) ? 'data-assembly' : 'data-part';
    return current!.prepared.svg.querySelectorAll(`[${attr}="${CSS.escape(key)}"]`);
  }

  function mark(cls: string, key: string | null): void {
    if (!current) return;
    for (const el of current.prepared.svg.querySelectorAll(`.${cls}`)) el.classList.remove(cls);
    if (key) for (const el of groupsFor(key)) el.classList.add(cls);
  }

  function focusOn(): void {
    if (!current) return;
    const { sheet, prepared, sx, sy } = current;
    const focus = store.get().sheetFocus;
    const key = focus?.part ?? focus?.assembly ?? null;
    mark('is-selected', key ?? store.get().selected);
    marker.remove();
    const at = key ? bestPlace(sheet.places.get(key)) : null;
    if (!at) {
      fit();
      return;
    }
    measureFit();
    const { box } = prepared;
    const w = Math.max(at.w, 2) * sx;
    const hgt = Math.max(at.h, 2) * sy;
    // Show the part with its surroundings: about a quarter of the viewport.
    const k = Math.min((canvas.clientWidth * 0.24) / w, (canvas.clientHeight * 0.24) / hgt);
    view = { cx: box.x + at.x * sx, cy: box.y + at.y * sy, k: Math.min(fitK * 12, Math.max(fitK * 1.4, k)) };
    const pad = Math.max(w, hgt) * 0.12 + 1.2;
    marker.setAttribute('x', String(view.cx - w / 2 - pad));
    marker.setAttribute('y', String(view.cy - hgt / 2 - pad));
    marker.setAttribute('width', String(w + pad * 2));
    marker.setAttribute('height', String(hgt + pad * 2));
    prepared.svg.appendChild(marker);
    apply();
  }

  // ── Loading a sheet ───────────────────────────────────────────────────────
  async function show(sheet: Sheet): Promise<void> {
    const token = ++loadToken;
    message.hidden = true;
    hideCallout();
    try {
      const prepared = prepareSheet(await sheetText(sheet));
      if (token !== loadToken) return;
      if (!prepared) throw new Error('not an SVG drawing');
      clearNode(canvas);
      canvas.appendChild(prepared.svg);
      prepared.svg.setAttribute('preserveAspectRatio', 'none');
      canvas.setAttribute('aria-label', `Sheet ${sheet.number}: ${sheet.title}`);
      const targets: Target[] = [];
      for (const [key, places] of sheet.places) {
        for (const place of places) targets.push({ key, place, area: place.w * place.h });
      }
      targets.sort((a, b) => a.area - b.area);
      current = {
        sheet,
        prepared,
        targets,
        sx: sheet.width > 0 ? prepared.box.width / sheet.width : 1,
        sy: sheet.height > 0 ? prepared.box.height / sheet.height : 1,
      };
      hoverKey = null;
      focusOn();
    } catch (err) {
      if (token !== loadToken) return;
      current = null;
      clearNode(canvas);
      message.hidden = false;
      message.textContent = `Sheet ${sheet.number} could not be loaded (${err instanceof Error ? err.message : 'error'}).`;
    }
  }

  // ── Picking ───────────────────────────────────────────────────────────────
  function hideCallout(): void {
    callout.hidden = true;
    clearNode(callout);
  }

  function pick(target: Target | null): void {
    if (!target) {
      hideCallout();
      return;
    }
    const part = app.catalog.byNumber.get(target.key);
    const assembly = part ? undefined : app.catalog.byAssembly.get(target.key);
    if (part) {
      select(app, part.number);
      mark('is-selected', part.number);
      fill(
        callout,
        h('span.data.callout-no', null, part.number),
        h('span.callout-name', null, part.name),
        h('button.btn', { type: 'button', onclick: () => selectAndInspect(app, part.number) }, 'Show in model'),
      );
      callout.hidden = false;
    } else if (assembly) {
      mark('is-selected', assembly.id);
      fill(
        callout,
        h('span.data.callout-no', null, assembly.id),
        h('span.callout-name', null, `${assembly.name}, ${assembly.parts.length} parts`),
        h(
          'button.btn',
          {
            type: 'button',
            onclick: () => {
              const iso = store.get().isolated;
              if (!(iso?.kind === 'assembly' && iso.id === assembly.id)) isolate(app, { kind: 'assembly', id: assembly.id });
              setTab(app, 'model');
            },
          },
          'Show in model',
        ),
      );
      callout.hidden = false;
    } else {
      hideCallout();
    }
  }

  // ── Pointer: drag to pan, wheel or pinch to zoom, click to pick ───────────
  const pointers = new Map<number, { x: number; y: number }>();
  let moved = 0;
  let pinch = 0;
  let hoverFrame = 0;
  const clearHover = () => {
    if (hoverKey) mark('is-hover', null);
    hoverKey = null;
    app.hover.set({ part: null, clientX: 0, clientY: 0 });
  };
  canvas.addEventListener('pointerdown', (e) => {
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 1) moved = 0;
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = Math.hypot(a!.x - b!.x, a!.y - b!.y);
    }
  });
  canvas.addEventListener('pointermove', (e) => {
    const prev = pointers.get(e.pointerId);
    if (!prev) {
      // Not dragging: show what is under the pointer.
      if (e.pointerType !== 'mouse' || hoverFrame) return;
      const { clientX, clientY } = e;
      hoverFrame = requestAnimationFrame(() => {
        hoverFrame = 0;
        const t = hit(clientX, clientY);
        const key = t?.key ?? null;
        if (key !== hoverKey) {
          mark('is-hover', key);
          hoverKey = key;
        }
        canvas.classList.toggle('pickable', !!key);
        app.hover.set({ part: key && !isAssemblyKey(key) ? key : null, clientX, clientY });
      });
      return;
    }
    const dx = e.clientX - prev.x;
    const dy = e.clientY - prev.y;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    moved += Math.abs(dx) + Math.abs(dy);
    if (pointers.size === 1) {
      if (moved > 4) {
        if (!canvas.hasPointerCapture(e.pointerId)) canvas.setPointerCapture(e.pointerId);
        canvas.classList.add('dragging');
        clearHover();
        pan(dx, dy);
      }
    } else if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const d = Math.hypot(a!.x - b!.x, a!.y - b!.y);
      if (pinch > 0) zoomAt(d / pinch, (a!.x + b!.x) / 2, (a!.y + b!.y) / 2);
      pinch = d;
    }
  });
  const release = (e: PointerEvent) => {
    const wasClick = pointers.size === 1 && moved <= 4 && e.type === 'pointerup';
    pointers.delete(e.pointerId);
    canvas.classList.remove('dragging');
    if (wasClick) pick(hit(e.clientX, e.clientY));
  };
  canvas.addEventListener('pointerup', release);
  canvas.addEventListener('pointercancel', release);
  canvas.addEventListener('pointerleave', clearHover);
  canvas.addEventListener(
    'wheel',
    (e) => {
      e.preventDefault();
      const unit = e.deltaMode === 1 ? 16 : 1;
      zoomAt(Math.exp(-e.deltaY * unit * 0.0016), e.clientX, e.clientY);
    },
    { passive: false },
  );
  viewer.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const step = 80;
    switch (e.key) {
      case '+':
      case '=':
        zoomBy(1.5);
        break;
      case '-':
      case '_':
        zoomBy(1 / 1.5);
        break;
      case '0':
        fit();
        break;
      case 'ArrowLeft':
        pan(step, 0);
        break;
      case 'ArrowRight':
        pan(-step, 0);
        break;
      case 'ArrowUp':
        pan(0, step);
        break;
      case 'ArrowDown':
        pan(0, -step);
        break;
      case 'PageDown':
      case 'PageUp': {
        const i = sheets.findIndex((x) => x.id === store.get().sheet);
        const next = sheets[i + (e.key === 'PageDown' ? 1 : -1)];
        if (next) openSheet(app, next.id);
        break;
      }
      default:
        return;
    }
    e.preventDefault();
  });
  new ResizeObserver(() => {
    if (!current) return;
    const ratio = view.k / fitK;
    measureFit();
    view.k = fitK * ratio;
    apply();
  }).observe(canvas);

  // ── Store ─────────────────────────────────────────────────────────────────
  if (!sheets.length) {
    message.hidden = false;
    message.textContent = 'The drawing set is not in this build.';
  }
  store.watch(
    (st) => [st.tab === 'blueprints', st.sheet, st.sheetFocus] as const,
    ([shown, id]) => {
      const sheet = shown ? (sheets.find((x) => x.id === id) ?? sheets[0]) : undefined;
      viewer.hidden = !shown;
      for (const b of indexButtons) {
        if (sheet && b.dataset.id === sheet.id) {
          b.setAttribute('aria-current', 'true');
          b.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        } else b.removeAttribute('aria-current');
      }
      if (!sheet) {
        clearHover();
        return;
      }
      // Coming back to a sheet that is already drawn only needs it re-aimed.
      if (current?.sheet.id === sheet.id) focusOn();
      else void show(sheet);
    },
  );

  return viewer;
}
