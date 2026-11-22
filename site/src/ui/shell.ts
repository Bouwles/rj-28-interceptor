import { setMount, setTab, type App } from '../app/context';
import { TABS, type MountState, type Tab } from '../app/store';
import { spec } from '../data';
import { num, pad2 } from '../data/format';
import { h } from './dom';

export const TAB_LABEL: Record<Tab, string> = {
  model: 'Model',
  dossier: 'Dossier',
  blueprints: 'Blueprints',
  spec: 'Specification',
};

/** Revision letter shown when the drawing set, which carries the real one, is absent. */
const REVISION = 'C';

function tabButtons(app: App, cls: string): HTMLElement {
  const buttons = TABS.map((t, i) =>
    h(
      'button.tab',
      { type: 'button', role: 'tab', id: `${cls}-${t}`, dataset: { tab: t }, title: `${TAB_LABEL[t]} (${i + 1})`, onclick: () => setTab(app, t) },
      h('span.data', { 'aria-hidden': 'true' }, String(i + 1)),
      TAB_LABEL[t],
    ),
  );
  app.store.watch(
    (s) => s.tab,
    (tab) => {
      for (const b of buttons) {
        const on = b.dataset.tab === tab;
        b.setAttribute('aria-selected', String(on));
        b.tabIndex = on ? 0 : -1;
      }
    },
  );
  const list = h(`div.${cls}`, { role: 'tablist', 'aria-label': 'Sections of the dossier' }, buttons);
  // Arrow keys move along the tabs, as a tab list should.
  list.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const i = TABS.indexOf(app.store.get().tab);
    const next = TABS[(i + (e.key === 'ArrowRight' ? 1 : -1) + TABS.length) % TABS.length]!;
    setTab(app, next);
    buttons.find((b) => b.dataset.tab === next)?.focus();
    e.preventDefault();
    e.stopPropagation();
  });
  return list;
}

/**
 * Top bar, laid out as the header strip of a drawing: designation, the four
 * tabs, what is in view, sheet number and revision, each in its own ruled cell.
 */
export function topBar(app: App, sectionNames: readonly string[]): HTMLElement {
  const ctxCap = h('span.cap');
  const ctx = h('span.tb-val');
  const sheetCap = h('span.cap');
  const sheetVal = h('span.tb-val.data');
  const last = sectionNames.length - 1;

  const bar = h(
    'header.topbar',
    null,
    h('div.tb-corner', { 'aria-hidden': 'true' }, /\d+/.exec(spec.designation)?.[0] ?? ''),
    h('div.tb-cell.tb-title', null, h('span.cap', null, 'Designation'), h('span.tb-val.tb-name', null, spec.designation)),
    tabButtons(app, 'tb-tabs'),
    h('div.tb-cell.tb-section', { 'aria-live': 'polite' }, ctxCap, ctx),
    h('div.tb-cell.tb-serial', null, h('span.cap', null, 'Serial'), h('span.tb-val.data', null, spec.serial)),
    h('div.tb-cell.tb-sheet', null, sheetCap, sheetVal),
    h('div.tb-cell.tb-rev', null, h('span.cap', null, 'Rev'), h('span.tb-val.data', null, app.sheets?.revision ?? REVISION)),
  );

  app.store.watch(
    (s) => [s.tab, s.section, s.sheet, s.strip, s.mount] as const,
    ([tab, index, sheetId, strip, mount]) => {
      const sheets = app.sheets?.sheets ?? [];
      const open = sheets.findIndex((x) => x.id === sheetId);
      sheetCap.textContent = 'Sheet';
      if (tab === 'blueprints' && open >= 0) {
        ctxCap.textContent = 'Drawing';
        ctx.textContent = sheets[open]!.title;
        sheetVal.textContent = `${pad2(open + 1)} / ${pad2(sheets.length)}`;
      } else if (tab === 'dossier') {
        ctxCap.textContent = 'Section';
        ctx.textContent = sectionNames[index] ?? '';
        sheetVal.textContent = `${pad2(index)} / ${pad2(last)}`;
      } else {
        ctxCap.textContent = tab === 'model' ? 'Configuration' : 'Reference';
        ctx.textContent =
          tab === 'model' ? `${spec.strip?.[strip]?.title ?? 'Complete'}, cannon ${mount}` : 'Data, joints, mass and bill of materials';
        sheetCap.textContent = 'Parts';
        sheetVal.textContent = num(app.catalog.parts.length, 0);
      }
    },
  );
  return bar;
}

/** Stowed / deployed control. Used in the action panel and in the mount section of the dossier. */
export function mountToggle(app: App): HTMLElement {
  const make = (state: MountState, label: string) =>
    h('button.btn', { type: 'button', onclick: () => setMount(app, state), dataset: { mount: state } }, label);
  const stowed = make('stowed', 'Stow');
  const deployed = make('deployed', 'Deploy');
  const group = h('div.seg', { role: 'group', 'aria-label': 'Cannon' }, stowed, deployed);
  app.store.watch(
    (s) => s.mount,
    (m) => {
      stowed.setAttribute('aria-pressed', String(m === 'stowed'));
      deployed.setAttribute('aria-pressed', String(m === 'deployed'));
    },
  );
  return group;
}

/** Bottom bar: what is on screen, the camera readout, and on a phone the tabs. */
export function bottomBar(app: App): HTMLElement {
  const status = h('span.tb-val.data');
  const az = h('dd.data');
  const el = h('dd.data');
  const dist = h('dd.data');
  const signed = (v: number) => (v > 0 ? '+' : '') + num(v, 1) + '°';
  const paint = () => {
    const c = app.store.get().tab === 'blueprints' || app.store.get().tab === 'spec' ? null : app.camera.get();
    az.textContent = c ? signed(c.azimuthDeg) : '—';
    el.textContent = c ? signed(c.elevationDeg) : '—';
    dist.textContent = !c ? '—' : c.distanceMm === null ? 'ortho' : `${num(c.distanceMm, 0)} mm`;
  };
  app.camera.subscribe(paint);

  const drawer = (which: 'parts' | 'actions', label: string) => {
    const b = h(
      'button.btn.bb-drawer',
      { type: 'button', onclick: () => app.store.set({ drawer: app.store.get().drawer === which ? null : which, intro: false }) },
      label,
    );
    app.store.watch(
      (s) => s.drawer,
      (open) => b.setAttribute('aria-pressed', String(open === which)),
    );
    return b;
  };

  app.store.watch(
    (s) => [s.presentation, s.lod, s.tab] as const,
    ([presentation, lod]) => {
      paint();
      const files = (app.manifest as { files?: Record<string, { triangles?: number }> } | null)?.files;
      const tris = lod === null ? null : files?.[`lod${lod}`]?.triangles;
      status.textContent =
        presentation !== 'live'
          ? 'Static edition: renders and drawings'
          : lod === null
            ? 'Loading the model'
            : `Level of detail ${lod}${tris ? `, ${num(tris, 0)} triangles` : ''}`;
    },
  );

  return h(
    'nav.bottombar',
    { 'aria-label': 'Status and camera' },
    tabButtons(app, 'bb-tabs'),
    h('div.bb-tools', null, drawer('actions', 'Actions'), drawer('parts', 'Parts')),
    h('div.tb-cell.bb-status', null, h('span.cap', null, 'Model'), status),
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
  'no-gpu': 'This browser has no WebGL 2. Showing renders and drawings.',
  'no-model': 'The 3D model is not in this build. Showing renders and drawings.',
  'no-renderer': 'The 3D viewer is not in this build. Showing renders and drawings.',
  'load-failed': 'The 3D model did not load. Showing renders and drawings.',
};

/** One line saying why the page is static, when it is. */
export function staticNotice(app: App): HTMLElement {
  const note = h('p.static-note.data', { role: 'status' });
  app.store.watch(
    (s) => [s.presentation, s.staticReason, s.tab] as const,
    ([presentation, reason, tab]) => {
      note.hidden = presentation !== 'static' || tab === 'blueprints' || tab === 'spec';
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
