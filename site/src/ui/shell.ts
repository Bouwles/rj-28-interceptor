import { setMode, setMount, type App } from '../app/context';
import { MODES, type Mode, type MountState } from '../app/store';
import { spec } from '../data';
import { num, pad2 } from '../data/format';
import { h } from './dom';

const MODE_LABEL: Record<Mode, string> = {
  tour: 'Tour',
  inspect: 'Inspect',
  explode: 'Explode',
  blueprint: 'Blueprint',
};

const MODE_SECTION: Record<Exclude<Mode, 'tour'>, string> = {
  inspect: 'Inspect',
  explode: 'Inspect: exploded view',
  blueprint: 'Inspect: blueprint',
};

/** Revision letter shown when the drawing set, which carries the real one, is absent. */
const REVISION = 'C';

/**
 * Top bar, laid out as the header strip of a drawing: designation, the
 * section in view, sheet number and revision, each in its own ruled cell.
 */
export function topBar(app: App, sectionNames: readonly string[]): HTMLElement {
  const sectionCap = h('span.cap', null, 'Section');
  const section = h('span.tb-val');
  const sheetVal = h('span.tb-val.data');
  const last = sectionNames.length - 1;

  const bar = h(
    'header.topbar',
    null,
    h('div.tb-corner', { 'aria-hidden': 'true' }, /\d+/.exec(spec.designation)?.[0] ?? ''),
    h('div.tb-cell.tb-title', null, h('span.cap', null, 'Designation'), h('span.tb-val.tb-name', null, spec.designation)),
    h('div.tb-cell.tb-section', { 'aria-live': 'polite' }, sectionCap, section),
    h('div.tb-cell.tb-serial', null, h('span.cap', null, 'Serial'), h('span.tb-val.data', null, spec.serial)),
    h('div.tb-cell.tb-sheet', null, h('span.cap', null, 'Sheet'), sheetVal),
    h('div.tb-cell.tb-rev', null, h('span.cap', null, 'Rev'), h('span.tb-val.data', null, app.sheets?.revision ?? REVISION)),
  );

  app.store.watch(
    (s) => [s.mode, s.section, s.sheet] as const,
    ([mode, index, sheetId]) => {
      const sheets = app.sheets?.sheets ?? [];
      const open = sheetId ? sheets.findIndex((x) => x.id === sheetId) : -1;
      if (open >= 0) {
        sectionCap.textContent = 'Drawing';
        section.textContent = sheets[open]!.title;
        sheetVal.textContent = `${pad2(open + 1)} / ${pad2(sheets.length)}`;
      } else if (mode === 'tour') {
        sectionCap.textContent = 'Section';
        section.textContent = sectionNames[index] ?? '';
        sheetVal.textContent = `${pad2(index)} / ${pad2(last)}`;
      } else {
        sectionCap.textContent = 'Section';
        section.textContent = MODE_SECTION[mode];
        sheetVal.textContent = `${pad2(last)} / ${pad2(last)}`;
      }
    },
  );
  return bar;
}

/** Stowed / deployed control. Used in the bottom bar and in the mount section of the tour. */
export function mountToggle(app: App): HTMLElement {
  const make = (state: MountState, label: string) =>
    h('button.btn', { type: 'button', onclick: () => setMount(app, state), dataset: { mount: state } }, label);
  const stowed = make('stowed', 'Stowed');
  const deployed = make('deployed', 'Deployed');
  const group = h('div.seg', { role: 'group', 'aria-label': 'Mount position' }, stowed, deployed);
  app.store.watch(
    (s) => s.mount,
    (m) => {
      stowed.setAttribute('aria-pressed', String(m === 'stowed'));
      deployed.setAttribute('aria-pressed', String(m === 'deployed'));
    },
  );
  return group;
}

/** Bottom bar: mode switch, mount toggle, camera readout. */
export function bottomBar(app: App): HTMLElement {
  const modes = MODES.map((m) =>
    h(
      'button.bb-mode',
      { type: 'button', onclick: () => setMode(app, m), dataset: { mode: m } },
      MODE_LABEL[m],
    ),
  );
  app.store.watch(
    (s) => s.mode,
    (mode) => {
      for (const b of modes) {
        if (b.dataset.mode === mode) b.setAttribute('aria-current', 'page');
        else b.removeAttribute('aria-current');
      }
    },
  );

  const az = h('dd.data');
  const el = h('dd.data');
  const dist = h('dd.data');
  const signed = (v: number) => (v > 0 ? '+' : '') + num(v, 1) + '°';
  app.camera.subscribe((c) => {
    az.textContent = c ? signed(c.azimuthDeg) : '—';
    el.textContent = c ? signed(c.elevationDeg) : '—';
    dist.textContent = !c ? '—' : c.distanceMm === null ? 'ortho' : `${num(c.distanceMm, 0)} mm`;
  });

  const drawer = h(
    'button.btn.bb-drawer',
    { type: 'button', onclick: () => app.store.set({ drawer: !app.store.get().drawer }) },
    'Parts',
  );
  app.store.watch(
    (s) => s.drawer,
    (open) => drawer.setAttribute('aria-pressed', String(open)),
  );

  return h(
    'nav.bottombar',
    { 'aria-label': 'View controls' },
    h('div.bb-modes', { role: 'group', 'aria-label': 'Mode' }, modes),
    h('div.bb-mount', null, h('span.cap', null, 'Mount'), mountToggle(app), drawer),
    h(
      'dl.bb-cam',
      { 'aria-label': 'Camera' },
      h('div', null, h('dt.cap', { title: 'Azimuth' }, 'Az'), az),
      h('div', null, h('dt.cap', { title: 'Elevation' }, 'El'), el),
      h('div', null, h('dt.cap', { title: 'Distance to target' }, 'Dist'), dist),
    ),
    h(
      'button.bb-help',
      { type: 'button', 'aria-label': 'Keyboard shortcuts', onclick: () => app.store.set({ help: true }) },
      h('span.cap', null, 'Keys'),
      h('kbd', null, '?'),
    ),
  );
}

/** Four corner marks on the viewport. */
export function registrationMarks(): HTMLElement {
  return h(
    'div.regmarks',
    { 'aria-hidden': 'true' },
    h('i.reg.reg-tl'),
    h('i.reg.reg-tr'),
    h('i.reg.reg-bl'),
    h('i.reg.reg-br'),
  );
}

const REASONS: Record<string, string> = {
  forced: 'Static edition: renders and drawings.',
  'no-gpu': 'This browser has no WebGL 2 or WebGPU. Showing renders and drawings.',
  'no-model': 'The 3D model is not in this build. Showing renders and drawings.',
  'no-renderer': 'The 3D viewer is not in this build yet. Showing renders and drawings.',
  'load-failed': 'The 3D model did not load. Showing renders and drawings.',
};

/** One line saying why the page is static, when it is. */
export function staticNotice(app: App): HTMLElement {
  const note = h('p.static-note.data', { role: 'status' });
  app.store.watch(
    (s) => [s.presentation, s.staticReason] as const,
    ([presentation, reason]) => {
      note.hidden = presentation !== 'static';
      note.textContent = reason ? (REASONS[reason] ?? '') : '';
    },
  );
  return note;
}

/** Help overlay listing the keyboard map. */
export function helpOverlay(app: App, rows: { keys: string[]; does: string }[]): HTMLElement {
  const close = h('button.btn', { type: 'button', onclick: () => app.store.set({ help: false }) }, 'Close', h('kbd', null, 'Esc'));
  const dialog = h(
    'div.help-box',
    { role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'help-title', tabindex: '-1' },
    h('div.help-head', null, h('h2', { id: 'help-title' }, 'Keyboard'), close),
    h(
      'dl.help-keys',
      null,
      rows.map((r) =>
        h('div', null, h('dt', null, r.keys.map((k) => h('kbd', null, k))), h('dd', null, r.does)),
      ),
    ),
    h('p.help-note', null, 'Orbit: drag. Pan: right-drag or two fingers. Zoom: wheel or pinch. Double-click a part to frame it.'),
  );
  const overlay = h('div.help', { hidden: true, onclick: (e: Event) => e.target === overlay && app.store.set({ help: false }) }, dialog);
  let returnTo: Element | null = null;
  app.store.watch(
    (s) => s.help,
    (open) => {
      overlay.hidden = !open;
      if (open) {
        returnTo = document.activeElement;
        close.focus();
      } else if (returnTo instanceof HTMLElement) {
        returnTo.focus();
        returnTo = null;
      }
    },
  );
  // Keep Tab inside the dialog while it is open.
  overlay.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      close.focus();
    }
  });
  return overlay;
}
