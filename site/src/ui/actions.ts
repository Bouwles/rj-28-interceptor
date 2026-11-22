import {
  resetModel,
  setElevation,
  setExplode,
  setStrip,
  setTraverse,
  STRIP_MAX,
  toggleMeasure,
  toggleXray,
  type App,
} from '../app/context';
import { spec } from '../data';
import { kg, mm, num } from '../data/format';
import { h } from './dom';
import { mountToggle } from './shell';

const signedDeg = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${num(Math.abs(v), 1)}°`;

interface Slider {
  row: HTMLElement;
  input: HTMLInputElement;
  out: HTMLOutputElement;
}

function slider(id: string, label: string, min: number, max: number, step: number, scale: string[]): Slider {
  const input = h('input.slider', { type: 'range', id, min: String(min), max: String(max), step: String(step) });
  const out = h('output.act-value.data', { for: id });
  const row = h(
    'div.act-slider',
    null,
    h('label.cap', { for: id }, label),
    out,
    h('div.slider-wrap', null, input, h('div.slider-scale', { 'aria-hidden': 'true' }, scale.map((s) => h('span.cap', null, s)))),
  );
  return { row, input, out };
}

/**
 * Action panel on the model tab: what can be done to the machine, laid out
 * like the schedule of a drawing. Cannon, strip-down, explode, view.
 */
export function buildActions(app: App): HTMLElement {
  const { store } = app;
  const live = () => store.get().presentation === 'live';

  // ── Cannon ────────────────────────────────────────────────────────────────
  const m = spec.mount;
  const trav = slider('act-trav', 'Traverse', -m.traverse, m.traverse, 0.5, [signedDeg(-m.traverse), signedDeg(0), signedDeg(m.traverse)]);
  const elev = slider('act-elev', 'Elevation', m.elevation[0], m.elevation[1], 0.5, [signedDeg(m.elevation[0]), '', signedDeg(m.elevation[1])]);
  trav.input.addEventListener('input', () => setTraverse(app, Number(trav.input.value)));
  elev.input.addEventListener('input', () => setElevation(app, Number(elev.input.value)));
  const cannonNote = h('p.act-note');
  const clearance =
    m.min_clearance_mm !== undefined
      ? h(
          'dl.act-facts',
          null,
          h('div', null, h('dt', null, 'Least clearance through the travel'), h('dd.data', null, mm(m.min_clearance_mm))),
          m.required_clearance_mm !== undefined ? h('div', null, h('dt', null, 'Required'), h('dd.data', null, mm(m.required_clearance_mm))) : null,
        )
      : null;
  const cannon = h(
    'section.act',
    { 'aria-labelledby': 'act-cannon' },
    h('h3', { id: 'act-cannon' }, 'Cannon'),
    h('div.act-row', null, mountToggle(app), h('kbd', null, 'M')),
    trav.row,
    elev.row,
    cannonNote,
    clearance,
  );
  const paintCannon = () => {
    const s = store.get();
    const pose = app.mountPose.get();
    const deployed = s.mount === 'deployed';
    const usable = deployed && live();
    // While the mount is moving the figures follow it; at rest they are the set angles.
    const e = pose ? pose.elevationDeg : deployed ? s.elevation : m.elevation[1];
    const t = pose ? pose.traverseDeg : deployed ? s.traverse : 0;
    elev.out.textContent = signedDeg(Math.abs(e) < 0.05 ? 0 : e);
    trav.out.textContent = signedDeg(Math.abs(t) < 0.05 ? 0 : t);
    if (document.activeElement !== elev.input) elev.input.value = String(deployed ? s.elevation : m.elevation[1]);
    if (document.activeElement !== trav.input) trav.input.value = String(deployed ? s.traverse : 0);
    elev.input.disabled = !usable;
    trav.input.disabled = !usable || s.elevation > 0;
    cannonNote.textContent = !live()
      ? 'The sliders drive the 3D model.'
      : !deployed
        ? 'Stowed: barrel vertical, breech in the travel lock. Deploy to train it.'
        : s.elevation > 0
          ? 'Traverse is held on centre above level: the clearance sweep covered it at level and below.'
          : 'Level. Traverse is free; raising the barrel returns it to centre.';
  };
  store.watch((s) => [s.mount, s.traverse, s.elevation, s.presentation] as const, paintCannon);
  app.mountPose.subscribe(paintCannon, false);

  // ── Strip-down ────────────────────────────────────────────────────────────
  const stages = spec.strip ?? [];
  const stageRows = stages.map((st) =>
    h(
      'button.strip-row',
      { type: 'button', dataset: { stage: String(st.stage) }, onclick: () => setStrip(app, st.stage) },
      h('span.data.strip-no', null, String(st.stage)),
      h('span.strip-title', null, st.title),
      h('span.data.strip-parts', null, st.stage === 0 ? '' : `−${num(st.parts, 0)}`),
      h('span.data.strip-mass', null, st.stage === 0 ? '' : `−${kg(st.mass_kg)}`),
    ),
  );
  const back = h('button.btn', { type: 'button', 'aria-label': 'Put a layer back', onclick: () => setStrip(app, store.get().strip - 1) }, 'Refit', h('kbd', null, '['));
  const fwd = h('button.btn', { type: 'button', 'aria-label': 'Take a layer off', onclick: () => setStrip(app, store.get().strip + 1) }, 'Remove', h('kbd', null, ']'));
  const stripSum = h('p.act-note', { 'aria-live': 'polite' });
  const strip = h(
    'section.act',
    { 'aria-labelledby': 'act-strip' },
    h('h3', { id: 'act-strip' }, 'Armour'),
    h(
      'div.strip-table',
      { role: 'group', 'aria-label': 'Strip-down stage' },
      h('div.strip-head', { 'aria-hidden': 'true' }, h('span.cap', null, 'Stage'), h('span'), h('span.cap', null, 'Parts'), h('span.cap', null, 'Mass')),
      stageRows,
    ),
    h('div.act-row', null, h('div.seg', null, back, fwd)),
    stripSum,
  );
  store.watch(
    (s) => [s.strip, s.presentation] as const,
    ([stage]) => {
      for (const r of stageRows) {
        const n = Number(r.dataset.stage);
        r.setAttribute('aria-pressed', String(n === stage));
        r.classList.toggle('done', n > 0 && n <= stage);
      }
      back.disabled = stage <= 0;
      fwd.disabled = stage >= STRIP_MAX;
      let parts = 0;
      let mass = 0;
      for (const st of stages) {
        if (st.stage === 0 || st.stage > stage) {
          parts += st.parts;
          mass += st.mass_kg;
        }
      }
      stripSum.textContent = stages.length ? `On the machine: ${num(parts, 0)} parts, ${kg(mass, 1)}.` : '';
    },
  );

  // ── Explode ───────────────────────────────────────────────────────────────
  const ex = slider('act-explode', 'Explode', 0, 100, 1, ['Assembled', 'Assemblies apart', 'Parts apart']);
  ex.input.addEventListener('input', () => setExplode(app, Number(ex.input.value) / 100));
  const explode = h('section.act', { 'aria-labelledby': 'act-ex' }, h('h3.sr-only', { id: 'act-ex' }, 'Explode'), ex.row);
  store.watch(
    (s) => [s.explode, s.presentation] as const,
    ([amount]) => {
      const pct = Math.round(amount * 100);
      if (document.activeElement !== ex.input) ex.input.value = String(pct);
      ex.out.textContent = `${pct}%`;
      ex.input.disabled = !live();
    },
  );

  // ── View ──────────────────────────────────────────────────────────────────
  const xray = h('button.btn', { type: 'button', onclick: () => toggleXray(app) }, 'X-ray armour', h('kbd', null, 'X'));
  const measure = h('button.btn', { type: 'button', onclick: () => toggleMeasure(app) }, 'Measure', h('kbd', null, 'R'));
  const reset = h('button.btn', { type: 'button', onclick: () => resetModel(app) }, 'Reset view', h('kbd', null, '0'));
  const measureOut = h('output.act-note.data', { 'aria-live': 'polite' });
  const view = h(
    'section.act',
    { 'aria-labelledby': 'act-view' },
    h('h3', { id: 'act-view' }, 'View'),
    h('div.act-row.act-wrap', null, xray, measure, reset),
    measureOut,
  );
  store.watch(
    (s) => s.xray,
    (on) => xray.setAttribute('aria-pressed', String(on)),
  );
  const paintMeasure = () => {
    const on = store.get().measure;
    const r = app.measurement.get();
    measure.setAttribute('aria-pressed', String(on));
    measureOut.hidden = !on;
    measureOut.textContent = !on ? '' : r ? `${mm(r.distanceMm)}${r.plane ? ' in plane' : ' between the two points'}` : 'Click two points on the model.';
  };
  store.watch((s) => s.measure, paintMeasure);
  app.measurement.subscribe(paintMeasure, false);

  return h('div.actions-panel', { role: 'region', 'aria-label': 'Controls' }, cannon, strip, explode, view);
}

/** Part number and name beside the pointer while it is over a part. */
export function buildHoverTag(app: App): HTMLElement {
  const no = h('span.data');
  const name = h('span');
  const tag = h('div.hover-tag', { hidden: true, 'aria-hidden': 'true' }, no, name);
  app.hover.subscribe((hit) => {
    const part = hit.part ? app.catalog.byNumber.get(hit.part) : undefined;
    tag.hidden = !part;
    if (!part) return;
    no.textContent = part.number;
    name.textContent = part.name;
    const flip = hit.clientX > window.innerWidth - 280;
    tag.style.transform = `translate(${hit.clientX + (flip ? -14 : 14)}px, ${hit.clientY + 16}px)${flip ? ' translateX(-100%)' : ''}`;
  });
  return tag;
}
