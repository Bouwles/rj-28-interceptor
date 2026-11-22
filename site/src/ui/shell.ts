import { playClip, setMount, type App } from '../app/context';
import { CLIPS } from '../scene/clips';
import type { AppStore, MountState, Tab } from '../app/store';
import { h } from './dom';

const LINKS: [Tab, string][] = [
  ['model', 'Model'],
  ['blueprints', 'Blueprints'],
  ['spec', 'Specification'],
];

/** Slim header: the name on the left, three places to go on the right. */
export function header(store: AppStore): HTMLElement {
  const go = (tab: Tab) => store.set({ tab, drawer: null, measure: false });
  const links = LINKS.map(([tab, label]) => h('button.nav-link', { type: 'button', dataset: { tab }, onclick: () => go(tab) }, label));
  const help = h('button.nav-help', { type: 'button', 'aria-label': 'Keyboard shortcuts', title: 'Keyboard shortcuts', onclick: () => store.set({ help: true }) }, '?');
  store.watch(
    (s) => s.tab,
    (tab) => {
      for (const b of links) {
        if (b.dataset.tab === tab) b.setAttribute('aria-current', 'page');
        else b.removeAttribute('aria-current');
      }
      help.hidden = tab !== 'model';
    },
  );
  return h(
    'header.site-header',
    null,
    h('button.wordmark', { type: 'button', onclick: () => go('intro'), 'aria-label': 'RJ-28 Interceptor, introduction' }, 'RJ-28 Interceptor'),
    h('nav.site-nav', { 'aria-label': 'Sections' }, links, help),
  );
}

/** Stow / deploy control. */
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

/** Buttons over the stage: open the parts list, and on a phone the controls. */
export function stageButtons(app: App): HTMLElement {
  const make = (which: 'parts' | 'actions', label: string) => {
    const b = h(
      `button.btn.stage-btn.stage-btn-${which}`,
      { type: 'button', onclick: () => app.store.set({ drawer: app.store.get().drawer === which ? null : which }) },
      label,
    );
    app.store.watch(
      (s) => s.drawer,
      (open) => b.setAttribute('aria-pressed', String(open === which)),
    );
    return b;
  };
  return h('div.stage-buttons', null, make('parts', 'Parts'), make('actions', 'Controls'));
}

/** Bottom of the stage: the movements the robot can be asked to make. */
export function motionBar(app: App): HTMLElement {
  const tray = h('div.motion-tray', { id: 'motion-tray', role: 'group', 'aria-label': 'Animations', hidden: true });
  const buttons = CLIPS.map((c) => {
    const b = h('button.btn.motion-clip', { type: 'button', onclick: () => playClip(app, c.id) }, c.label);
    tray.appendChild(b);
    return b;
  });
  const toggle = h(
    'button.btn.motion-toggle',
    { type: 'button', 'aria-expanded': 'false', 'aria-controls': 'motion-tray', onclick: () => open(tray.hasAttribute('hidden')) },
    'Animations',
  );
  const stop = h('button.btn.motion-stop', { type: 'button', hidden: true, onclick: () => playClip(app, null) }, 'Stop');
  const open = (on: boolean) => {
    tray.hidden = !on;
    toggle.setAttribute('aria-expanded', String(on));
  };
  app.store.watch(
    (s) => s.clip,
    (clip) => {
      buttons.forEach((b, i) => b.setAttribute('aria-pressed', String(CLIPS[i]!.id === clip)));
      stop.hidden = !clip;
      if (clip) open(false); // out of the way of what it started
    },
  );
  const bar = h('div.motion', null, tray, h('div.motion-row', null, toggle, stop));
  app.store.watch(
    (s) => s.presentation,
    (p) => (bar.hidden = p !== 'live'),
  );
  return bar;
}

const REASONS: Record<string, string> = {
  forced: 'Static view: a drawing of the part envelopes stands in for the 3D model.',
  'no-gpu': 'This browser has no WebGL 2, so a drawing of the part envelopes stands in for the 3D model.',
  'no-model': 'The 3D model is not in this build. A drawing of the part envelopes stands in for it.',
  'no-renderer': 'The 3D viewer is not in this build. A drawing of the part envelopes stands in for it.',
  'load-failed': 'The 3D model did not load. A drawing of the part envelopes stands in for it.',
};

/** What the model view says while the model loads, or when it cannot be shown. */
export function modelStatus(app: App, progress: () => number): HTMLElement {
  const text = h('p');
  const bar = h('i');
  const el = h('div.model-status', { role: 'status' }, text, h('div.progress', { 'aria-hidden': 'true' }, bar));
  const paint = () => {
    const s = app.store.get();
    el.hidden = s.tab !== 'model' || s.presentation === 'live';
    el.classList.toggle('is-note', s.presentation === 'static');
    text.textContent = s.presentation === 'static' ? (REASONS[s.staticReason ?? ''] ?? '') : 'Loading the model';
    bar.style.transform = `scaleX(${progress().toFixed(3)})`;
  };
  app.store.watch((s) => [s.tab, s.presentation, s.staticReason] as const, paint);
  const timer = window.setInterval(() => {
    paint();
    if (app.store.get().presentation !== 'loading') window.clearInterval(timer);
  }, 120);
  return el;
}

/** Help overlay listing the keyboard map. */
export function helpOverlay(store: AppStore, rows: { keys: string[]; does: string }[]): HTMLElement {
  const close = h('button.btn', { type: 'button', onclick: () => store.set({ help: false }) }, 'Close');
  const dialog = h(
    'div.help-box',
    { role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'help-title', tabindex: '-1' },
    h('div.help-head', null, h('h2', { id: 'help-title' }, 'Keyboard'), close),
    h(
      'dl.help-keys',
      null,
      rows.map((r) => h('div', null, h('dt', null, r.keys.map((k) => h('kbd', null, k))), h('dd', null, r.does))),
    ),
    h('p.help-note', null, 'Drag to orbit, right-drag or two fingers to pan, wheel or pinch to zoom. Double-click a part to frame it.'),
  );
  const overlay = h('div.help', { hidden: true, onclick: (e: Event) => e.target === overlay && store.set({ help: false }) }, dialog);
  let returnTo: Element | null = null;
  store.watch(
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
  overlay.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      close.focus();
    }
  });
  return overlay;
}
