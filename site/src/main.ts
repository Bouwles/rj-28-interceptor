import './styles/base.css';
import './styles/shell.css';
import './styles/tour.css';
import './styles/inspector.css';
import './styles/sheets.css';

import { bindScene } from './app/bind-scene';
import { Commands, type App } from './app/context';
import { bindKeys, KEY_ROWS } from './app/keys';
import { initialState, Signal, Store, type AppState } from './app/store';
import { parseHash, syncUrl } from './app/url';
import { loadCatalog, loadModelManifest, loadMount, loadSheets, loadStations, planData, publicUrl, type Catalog } from './data';
import type { SheetSet } from './data/types';
import { AssetLoader } from './loader/assets';
import { createScene, sceneUnavailable } from './scene';
import type { CameraReadout, Measurement, PointerHit, SceneController } from './scene/types';
import { buildDetail } from './ui/detail';
import { h, isPhone, prefersReducedMotion } from './ui/dom';
import { createLoader } from './ui/loader';
import { buildSheetViewer, primeSheet } from './ui/sheets';
import { bottomBar, helpOverlay, registrationMarks, staticNotice, topBar } from './ui/shell';
import { buildStaticStage, canvasSummary } from './ui/stage';
import { buildHoverTag, buildTools } from './ui/tools';
import { buildTour } from './ui/tour';
import { SECTION_NAMES, SECTIONS } from './ui/tour-content';
import { buildTree } from './ui/tree';

/** Drop anything from the address that does not exist in the data. */
function sanitise(patch: Partial<AppState>, catalog: Catalog, sheets: SheetSet | null): Partial<AppState> {
  const out = { ...patch };
  if (out.selected && !catalog.byNumber.has(out.selected)) delete out.selected;
  if (out.sheet && !sheets?.sheets.some((s) => s.id === out.sheet)) {
    delete out.sheet;
    delete out.sheetFocus;
  }
  if (out.isolated) {
    const ok = out.isolated.kind === 'part' ? catalog.byNumber.has(out.isolated.id) : catalog.byAssembly.has(out.isolated.id);
    if (!ok) delete out.isolated;
  }
  if (out.section !== undefined) out.section = Math.min(SECTIONS.length - 1, out.section);
  // A link to a part is a link to the inspector.
  if (out.selected && (out.mode ?? 'tour') === 'tour') out.mode = 'inspect';
  return out;
}

async function boot(): Promise<void> {
  const root = document.getElementById('app')!;
  const screen = createLoader();
  root.appendChild(screen.el);

  const loader = new AssetLoader();
  planData(loader);
  loader.onProgress((p) => screen.setProgress(p));

  const fromUrl = parseHash(location.hash);
  const forceStatic = new URLSearchParams(location.search).has('static');
  const unavailable = sceneUnavailable(forceStatic);

  // The static edition opens on a render: fetch the first one with everything else.
  const jobs: Promise<unknown>[] = [];
  if (unavailable && (fromUrl.mode ?? 'tour') === 'tour') {
    const def = SECTIONS[Math.min(SECTIONS.length - 1, fromUrl.section ?? 0)]!.plate;
    if (def !== 'sheet') {
      const file = isPhone() && def.phoneFile ? def.phoneFile : def.file;
      jobs.push(loader.image(`renders/${file}`, publicUrl(`renders/${file}`)).catch(() => undefined));
    }
  }

  const sheetsJob = loadSheets(loader).then(async (set) => {
    const first = set?.sheets[0];
    if (first) {
      try {
        const text = await loader.text(first.key, first.url);
        primeSheet(first, text);
        screen.setDrawing(text, first.title);
      } catch {
        // The loading screen simply has no drawing; the viewer reports the missing file.
      }
    }
    return set;
  });

  const [catalog, stations, mount, manifest, sheets] = await Promise.all([
    loadCatalog(loader),
    loadStations(loader),
    loadMount(loader),
    loadModelManifest(loader),
    sheetsJob,
    document.fonts.ready,
    ...jobs,
  ]);

  const store = new Store<AppState>({ ...initialState, ...sanitise(fromUrl, catalog, sheets) });
  const app: App = {
    store,
    catalog,
    sheets,
    stations,
    tour: new Signal(0),
    camera: new Signal<CameraReadout | null>(null),
    measurement: new Signal<Measurement | null>(null),
    hover: new Signal<PointerHit>({ part: null, clientX: 0, clientY: 0 }),
    commands: new Commands(),
    scene: null,
    reducedMotion: prefersReducedMotion,
  };

  // ── Stage: live canvas or the static edition ──────────────────────────────
  const canvas = h('canvas.stage-canvas', { role: 'img', 'aria-label': canvasSummary(catalog.parts.length) }, canvasSummary(catalog.parts.length));
  const stage = h('div.stage', null, canvas);
  let scene: SceneController | null = null;
  let reason = unavailable;
  if (!unavailable) {
    const result = await createScene(canvas, { loader, manifest, stations, mount, url: publicUrl });
    if (result.ok) scene = result.scene;
    else reason = result.reason;
  }
  app.scene = scene;

  // ── Interface ─────────────────────────────────────────────────────────────
  const tour = buildTour(app);
  const tree = buildTree(app);
  const detail = buildDetail(app);
  const frag = document.createDocumentFragment();
  frag.append(
    h('a.skip', { href: '#tour' }, 'Skip to the text'),
    stage,
    registrationMarks(),
    tour.el,
    tour.rail,
    tree,
    detail,
    buildTools(app),
    staticNotice(app),
    buildSheetViewer(app),
    topBar(app, SECTION_NAMES),
    bottomBar(app),
    helpOverlay(app, KEY_ROWS),
    buildHoverTag(app),
  );
  root.insertBefore(frag, screen.el);

  store.watch(
    (s) => [s.mode, s.presentation, s.drawer, s.measure] as const,
    ([mode, presentation, drawer, measure]) => {
      const d = document.body.dataset;
      d.mode = mode;
      d.presentation = presentation;
      d.drawer = String(drawer);
      d.measure = String(measure);
    },
  );

  if (scene) {
    bindScene(app, scene);
    const insets = () => {
      const s = store.get();
      const css = getComputedStyle(document.documentElement);
      const px = (name: string) => parseFloat(css.getPropertyValue(name)) || 0;
      const phone = isPhone();
      const inTour = s.mode === 'tour';
      const panel = tour.el.querySelector<HTMLElement>('.panel');
      scene!.setInsets({
        top: px('--top-h'),
        bottom: px('--bottom-h'),
        left: phone ? 0 : inTour ? px('--rail') + (panel?.offsetWidth ?? 0) : tree.offsetWidth,
        right: phone || inTour || !s.selected ? 0 : detail.offsetWidth,
      });
    };
    store.watch((s) => [s.mode, s.selected] as const, () => requestAnimationFrame(insets));
    window.addEventListener('resize', insets);
    canvas.hidden = false;
  } else {
    canvas.hidden = true;
    stage.appendChild(buildStaticStage(app));
  }

  bindKeys(app);
  syncUrl(store, (patch) => {
    const clean = sanitise(patch, catalog, sheets);
    // An edited address states the whole view: anything it leaves out goes back to its default.
    store.set({
      mode: clean.mode ?? 'tour',
      selected: clean.selected ?? null,
      mount: clean.mount ?? 'stowed',
      explode: clean.explode ?? store.get().explode,
      xray: clean.xray ?? false,
      view: clean.view ?? store.get().view,
      hiddenLines: clean.hiddenLines ?? false,
      sheet: clean.sheet ?? null,
      sheetFocus: clean.sheetFocus ?? null,
      isolated: clean.isolated ?? null,
    });
    if (clean.section !== undefined && store.get().mode === 'tour') tour.goto(clean.section, false);
  });

  store.set({ presentation: scene ? 'live' : 'static', staticReason: scene ? null : reason });
  tour.start();
  await screen.finish();
}

boot().catch((err: unknown) => {
  console.error(err);
  const root = document.getElementById('app');
  if (!root) return;
  root.replaceChildren(
    h(
      'div.fatal',
      { role: 'alert' },
      h('h1', null, 'RJ-28 INTERCEPTOR'),
      h('p', null, 'The dossier data could not be loaded. Reload the page to try again.'),
      h('p.data', null, err instanceof Error ? err.message : String(err)),
    ),
  );
});
