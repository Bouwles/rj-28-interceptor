import './styles/base.css';
import './styles/shell.css';
import './styles/intro.css';
import './styles/inspector.css';
import './styles/sheets.css';
import './styles/spec.css';

import { bindScene } from './app/bind-scene';
import { Commands, STRIP_MAX, type App } from './app/context';
import { bindKeys, KEY_ROWS } from './app/keys';
import { initialState, Signal, Store, type AppState } from './app/store';
import { parseHash, syncUrl } from './app/url';
import { loadCatalog, loadModelManifest, loadMount, loadSheets, planData, publicUrl, spec, type Catalog } from './data';
import type { SheetSet } from './data/types';
import { AssetLoader } from './loader/assets';
import { createScene, sceneUnavailable } from './scene';
import type { CameraReadout, Measurement, MountPose, PointerHit, SceneController } from './scene/types';
import { buildActions, buildHoverTag } from './ui/actions';
import { buildDetail } from './ui/detail';
import { h, isPhone, prefersReducedMotion } from './ui/dom';
import { buildIntro } from './ui/intro';
import { buildSheetViewer } from './ui/sheets';
import { header, helpOverlay, modelStatus, motionBar, stageButtons } from './ui/shell';
import { buildSpec } from './ui/spec';
import { buildStaticStage, canvasSummary } from './ui/stage';
import { buildTree } from './ui/tree';

/** Drop anything from the address that does not exist in the data. */
function sanitise(patch: Partial<AppState>, catalog: Catalog, sheets: SheetSet | null): Partial<AppState> {
  const out = { ...patch };
  if (out.selected && !catalog.byNumber.has(out.selected)) delete out.selected;
  if (out.sheet && out.sheet !== '3d' && !sheets?.sheets.some((s) => s.id === out.sheet)) {
    delete out.sheet;
    delete out.sheetFocus;
  }
  if (out.tab === 'blueprints' && !out.sheet) out.sheet = sheets?.sheets[0]?.id ?? null;
  if (out.isolated) {
    const ok = out.isolated.kind === 'part' ? catalog.byNumber.has(out.isolated.id) : catalog.byAssembly.has(out.isolated.id);
    if (!ok) delete out.isolated;
  }
  if (out.strip !== undefined) out.strip = Math.min(STRIP_MAX, out.strip);
  const [lo, hi] = spec.mount.elevation;
  if (out.elevation !== undefined) out.elevation = Math.min(hi, Math.max(lo, out.elevation));
  if (out.traverse !== undefined) out.traverse = Math.min(spec.mount.traverse, Math.max(-spec.mount.traverse, out.traverse));
  if ((out.elevation ?? 0) > 0) out.traverse = 0; // the interlock, see setElevation
  return out;
}

async function boot(): Promise<void> {
  const root = document.getElementById('app')!;
  const fromUrl = parseHash(location.hash);
  const store = new Store<AppState>({ ...initialState, tab: fromUrl.tab ?? 'intro' });

  // The introduction needs nothing but the bundled figures: it is on screen
  // at once, and everything else loads behind it.
  root.append(header(store), buildIntro(store), helpOverlay(store, KEY_ROWS));
  const tabClass = () => (document.body.dataset.tab = store.get().tab);
  store.watch((s) => s.tab, tabClass);

  const loader = new AssetLoader();
  planData(loader);
  const forceStatic = new URLSearchParams(location.search).has('static');
  const unavailable = sceneUnavailable(forceStatic);
  const light = isPhone() || window.matchMedia('(pointer: coarse)').matches;
  if (!unavailable) {
    loader.plan('models/rj28_lod1.glb');
    loader.plan('hdri/studio.hdr');
  }

  const [catalog, mount, manifest, sheets] = await Promise.all([
    loadCatalog(loader),
    loadMount(loader),
    loadModelManifest(loader),
    loadSheets(loader),
  ]);
  store.set(sanitise({ ...fromUrl, tab: store.get().tab }, catalog, sheets));

  const app: App = {
    store,
    catalog,
    sheets,
    manifest,
    camera: new Signal<CameraReadout | null>(null),
    measurement: new Signal<Measurement | null>(null),
    hover: new Signal<PointerHit>({ part: null, clientX: 0, clientY: 0 }),
    mountPose: new Signal<MountPose | null>(null),
    commands: new Commands(),
    scene: null,
    reducedMotion: prefersReducedMotion,
  };

  const summary = canvasSummary(catalog.parts.length);
  const canvas = h('canvas.stage-canvas', { role: 'img', 'aria-label': summary }, summary);
  const stage = h('div.stage', null, canvas);
  const tree = h('div.left-col', null, buildTree(app));
  const side = h('aside.side-panel', { 'aria-label': 'Selected part and controls' }, buildDetail(app), buildActions(app));
  const progress = () => {
    const p = loader.progress();
    return p.total > 0 ? p.loaded / p.total : 0;
  };
  // On a phone the two panels are short sheets; the handle makes one tall and short again.
  for (const panel of [tree, side]) {
    panel.prepend(h('button.sheet-handle', { type: 'button', 'aria-label': 'Make the panel taller or shorter', onclick: () => document.body.classList.toggle('sheet-tall') }));
  }
  root.prepend(stage);
  root.append(tree, side, stageButtons(app), motionBar(app), modelStatus(app, progress), buildSheetViewer(app), buildSpec(app), buildHoverTag(app));

  store.watch(
    (s) => [s.presentation, s.drawer, s.measure, s.selected, s.tab === 'blueprints' && s.sheet === '3d'] as const,
    ([presentation, drawer, measure, , drawing]) => {
      const d = document.body.dataset;
      d.drawing = String(drawing);
      document.body.classList.remove('sheet-tall');
      d.presentation = presentation;
      d.drawer = drawer ?? 'none';
      d.measure = String(measure);
    },
  );
  bindKeys(app);
  syncUrl(store, (patch) => {
    const clean = sanitise(patch, catalog, sheets);
    // An edited address states the whole view: anything it leaves out goes back to its default.
    store.set({
      tab: clean.tab ?? 'intro',
      selected: clean.selected ?? null,
      mount: clean.mount ?? 'stowed',
      traverse: clean.traverse ?? 0,
      elevation: clean.elevation ?? 0,
      strip: clean.strip ?? 0,
      explode: clean.explode ?? 0,
      xray: clean.xray ?? false,
      sheet: clean.sheet ?? store.get().sheet,
      view: clean.view ?? store.get().view,
      sheetFocus: clean.sheetFocus ?? null,
      isolated: clean.isolated ?? null,
    });
  });

  // ── The model: loads while the introduction is being read ─────────────────
  let scene: SceneController | null = null;
  let reason = unavailable;
  if (!unavailable) {
    const result = await createScene(canvas, { loader, manifest, parts: catalog.parts, mount, url: publicUrl, light });
    if (result.ok) scene = result.scene;
    else reason = result.reason;
  }
  app.scene = scene;
  if (scene) {
    bindScene(app, scene);
    const insets = () => {
      const css = getComputedStyle(document.documentElement);
      const top = parseFloat(css.getPropertyValue('--top-h')) || 0;
      const phone = isPhone();
      const open = store.get().drawer === 'parts';
      const s = store.get();
      // On a phone a sheet covers the lower part of the screen when one is up.
      const sheet = s.drawer || s.selected ? 0.42 : 0;
      const model = s.tab === 'model';
      const bottom = phone && model ? 66 + window.innerHeight * sheet : 0;
      // The drawing view sits beside the sheet list; the model beside its panels.
      const left = phone ? 0 : model ? (open ? tree.offsetWidth : 0) : 300;
      scene!.setInsets({ top: top + (model ? 0 : 60), bottom, left, right: phone || !model ? 0 : side.offsetWidth });
    };
    store.watch((s) => [s.tab, s.drawer, !!s.selected, s.sheet === '3d'] as const, () => requestAnimationFrame(insets));
    window.addEventListener('resize', insets);
    // Read-only handle for the capture script and for the console.
    (window as unknown as { rj28: unknown }).rj28 = { scene, state: () => store.get() };
  } else {
    canvas.hidden = true;
    stage.appendChild(buildStaticStage(app));
  }
  store.set({ presentation: scene ? 'live' : 'static', staticReason: scene ? null : reason });
}

boot().catch((err: unknown) => {
  console.error(err);
  const root = document.getElementById('app');
  if (!root) return;
  root.append(
    h(
      'div.fatal',
      { role: 'alert' },
      h('p', null, 'Part of the page could not be loaded. Reload to try again.'),
      h('p.data', null, err instanceof Error ? err.message : String(err)),
    ),
  );
});
