import { openSheet, setExplode, setView, toggleHiddenLines, toggleMeasure, toggleXray, type App } from '../app/context';
import { VIEWS, type BlueprintView } from '../app/store';
import { mm } from '../data/format';
import { h } from './dom';

const VIEW_LABEL: Record<BlueprintView, string> = { front: 'Front', side: 'Side', rear: 'Rear', top: 'Top', iso: 'Iso' };

/**
 * Tool strip above the bottom bar in the inspector modes. X-ray and measure are
 * always there; the explode slider and the blueprint views join them in their modes.
 */
export function buildTools(app: App): HTMLElement {
  const { store } = app;

  const xray = h('button.btn', { type: 'button', onclick: () => toggleXray(app) }, 'X-ray armour', h('kbd', null, 'X'));
  const measure = h('button.btn', { type: 'button', onclick: () => toggleMeasure(app) }, 'Measure', h('kbd', null, 'R'));
  const measureOut = h('output.tool-readout.data', { 'aria-live': 'polite' });

  // Explode: 0 to 100 %, with the two stages marked on the scale.
  const slider = h('input.slider', { type: 'range', min: '0', max: '100', step: '1', id: 'explode', 'aria-describedby': 'explode-scale' });
  const explodeVal = h('output.tool-readout.data', { for: 'explode' });
  slider.addEventListener('input', () => setExplode(app, Number(slider.value) / 100));
  const explode = h(
    'div.tool-group.tool-explode',
    null,
    h('label.cap', { for: 'explode' }, 'Explode'),
    h(
      'div.slider-wrap',
      null,
      slider,
      h(
        'div.slider-scale',
        { id: 'explode-scale' },
        h('span.cap', null, 'Assembled'),
        h('span.cap', null, 'Assemblies apart'),
        h('span.cap', null, 'Parts apart'),
      ),
    ),
    explodeVal,
  );

  const viewButtons = VIEWS.map((v) =>
    h('button.btn', { type: 'button', dataset: { view: v }, onclick: () => setView(app, v) }, VIEW_LABEL[v]),
  );
  const hiddenLines = h('button.btn', { type: 'button', onclick: () => toggleHiddenLines(app) }, 'Hidden lines');
  const sheets = h('button.btn', { type: 'button', onclick: () => openSheet(app) }, 'Drawing sheets');
  const blueprint = h(
    'div.tool-group.tool-blueprint',
    null,
    h('div.seg', { role: 'group', 'aria-label': 'View' }, viewButtons),
    hiddenLines,
    sheets,
  );

  const strip = h(
    'div.toolstrip',
    { role: 'toolbar', 'aria-label': 'Tools' },
    h('div.tool-group', null, xray, measure, measureOut),
    explode,
    blueprint,
  );

  store.watch(
    (s) => s.xray,
    (on) => xray.setAttribute('aria-pressed', String(on)),
  );
  store.watch(
    (s) => [s.hiddenLines, s.presentation] as const,
    ([on, presentation]) => {
      hiddenLines.setAttribute('aria-pressed', String(on));
      // Hidden-line display belongs to the 3D line render; the box model has none to show.
      hiddenLines.hidden = presentation !== 'live';
    },
  );
  store.watch(
    (s) => s.view,
    (view) => {
      for (const b of viewButtons) b.setAttribute('aria-pressed', String(b.dataset.view === view));
    },
  );
  store.watch(
    (s) => s.explode,
    (amount) => {
      const pct = Math.round(amount * 100);
      slider.value = String(pct);
      slider.style.setProperty('--fill', `${pct}%`);
      explodeVal.textContent = `${String(pct).padStart(3, ' ')}%`;
    },
  );
  store.watch(
    (s) => s.mode,
    (mode) => {
      explode.hidden = mode !== 'explode';
      blueprint.hidden = mode !== 'blueprint';
      sheets.hidden = !app.sheets?.sheets.length;
    },
  );

  const showMeasure = () => {
    const on = store.get().measure;
    const m = app.measurement.get();
    measure.setAttribute('aria-pressed', String(on));
    measureOut.hidden = !on;
    measureOut.textContent = !on ? '' : m ? `${mm(m.distanceMm)}${m.plane ? ' in plane' : ''}` : 'Click two points';
  };
  store.watch((s) => s.measure, showMeasure);
  app.measurement.subscribe(showMeasure, false);

  return strip;
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
