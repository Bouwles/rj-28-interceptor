import './styles/base.css';
import './styles/shell.css';
import './styles/tour.css';
import './styles/inspector.css';
import './styles/sheets.css';
import './styles/spec.css';

import { bindScene } from './app/bind-scene';
import { Commands, STRIP_MAX, type App } from './app/context';
import { bindKeys, KEY_ROWS } from './app/keys';
import { initialState, Signal, Store, type AppState } from './app/store';
import { parseHash, syncUrl } from './app/url';
import { loadCatalog, loadModelManifest, loadMount, loadSheets, loadStations, planData, publicUrl, spec, type Catalog } from './data';
import type { SheetSet } from './data/types';
import { AssetLoader } from './loader/assets';
import { createScene, sceneUnavailable } from './scene';
import type { CameraReadout, Measurement, MountPose, PointerHit, SceneController } from './scene/types';
import { buildActions, buildHoverTag } from './ui/actions';
import { buildDetail } from './ui/detail';
import { h, isPhone, prefersReducedMotion } from './ui/dom';
import { buildIntro } from './ui/intro';
import { createLoader } from './ui/loader';
import { buildSheetViewer, primeSheet } from './ui/sheets';
import { bottomBar, helpOverlay, registrationMarks, staticNotice, topBar } from './ui/shell';
import { buildSpec } from './ui/spec';
import { buildStaticStage, canvasSummary } from './ui/stage';
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
  if (out.tab === 'blueprints' && !out.sheet) out.sheet = sheets?.sheets[0]?.id ?? null;
  if (out.isolated) {
    const ok = out.isolated.kind === 'part' ? catalog.byNumber.has(out.isolated.id) : catalog.byAssembly.has(out.isolated.id);
    if (!ok) delete out.isolated;
  }
  if (out.section !== undefined) out.section = Math.min(SECTIONS.length - 1, out.section);
  if (out.strip !== undefined) out.strip = Math.min(STRIP_MAX, out.strip);
  const [lo, hi] = spec.mount.elevation;
  if (out.elevation !== undefined) out.elevation = Math.min(hi, Math.max(lo, out.elevation));
  if (out.traverse !== undefined) out.traverse = Math.min(spec.mount.traverse, Math.max(-spec.mount.traverse, out.traverse));
  if ((out.elevation ?? 0) > 0) out.traverse = 0; // the interlock, see setElevation
  // A link that asks for anything is past the title block.
  if (Object.keys(out).length) out.intro = false;
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
  const light = isPhone() || window.matchMedia('(pointer: coarse)').matches;

  const jobs: Promise<unknown>[] = [];
  if (!unavailable) {
    // Announce the first model files so the total is right from the first frame.
    loader.plan('models/rj28_lod1.glb');
    loader.plan('hdri/studio.hdr');
  } else if (fromUrl.tab === 'dossier') {
    // The static dossier opens on a render: fetch it with everything else.
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
    manifest,
    tour: new Signal(0),
    camera: new Signal<CameraReadout | null>(null),
    measurement: new Signal<Measurement | null>(null),
    hover: new Signal<PointerHit>({ part: null, clientX: 0, clientY: 0 }),
    mountPose: new Signal<MountPose | null>(null),
    commands: new Commands(),
    scene: null,
    reducedMotion: prefersReducedMotion,
  };

  // ── Stage: the live canvas, or the static edition ─────────────────────────
  // It goes into the document first, under the loading screen, so the renderer
  // can size itself before its first frame.
  const summary = canvasSummary(catalog.parts.length);
  const canvas = h('canvas.stage-canvas', { role: 'img', 'aria-label': summary }, summary);
  const stage = h('div.stage', null, canvas);
  root.insertBefore(stage, screen.el);
  let scene: SceneController | null = null;
  let reason = unavailable;
  if (!unavailable) {
    const result = await createScene(canvas, { loader, manifest, parts: catalog.parts, stations, mount, url: publicUrl, light });
    if (result.ok) scene = result.scene;
    else reason = result.reason;
  }
  app.scene = scene;

  // ── Interface ─────────────────────────────────────────────────────────────
  const tour = buildTour(app);
  const tree = buildTree(app);
  const side = h('aside.side-panel', { 'aria-label': 'Selected part and actions' }, buildDetail(app), buildActions(app));
  const left = h('div.left-col', null, buildIntro(app), tree);
  const frag = document.createDocumentFragment();
  frag.append(
    h('a.skip', { href: '#tour' }, 'Skip to the text'),
    registrationMarks(),
    tour.el,
    tour.rail,
    left,
    side,
    staticNotice(app),
    buildSheetViewer(app),
    buildSpec(app),
    topBar(app, SECTION_NAMES),
    bottomBar(app),
    helpOverlay(app, KEY_ROWS),
    buildHoverTag(app),
  );
  root.insertBefore(frag, screen.el);

  store.watch(
    (s) => [s.tab, s.presentation, s.drawer, s.measure, s.intro] as const,
    ([tab, presentation, drawer, measure, intro]) => {
      const d = document.body.dataset;
      d.tab = tab;
      d.presentation = presentation;
      d.drawer = drawer ?? 'none';
      d.measure = String(measure);
      d.intro = String(intro);
    },
  );

  if (scene) {
    bindScene(app, scene);
    const insets = () => {
      const s = store.get();
      const css = getComputedStyle(document.documentElement);
      const px = (name: string) => parseFloat(css.getPropertyValue(name)) || 0;
      const phone = isPhone();
      const panel = tour.el.querySelector<HTMLElement>('.panel');
      const dossier = s.tab === 'dossier';
      scene!.setInsets({
        top: px('--top-h'),
        // On a phone the lower part of the screen is under the text, or under the title block.
        bottom: px('--bottom-h') + (!phone ? 0 : dossier ? window.innerHeight * 0.5 : s.intro ? left.offsetHeight : 0),
        left: phone ? 0 : dossier ? px('--rail') + (panel?.offsetWidth ?? 0) : left.offsetWidth,
        right: phone || dossier ? 0 : side.offsetWidth,
      });
    };
    store.watch((s) => [s.tab, s.intro] as const, () => requestAnimationFrame(insets));
    window.addEventListener('resize', insets);
    // Read-only handle for the capture script and for the console.
    (window as unknown as { rj28: unknown }).rj28 = { scene, state: () => store.get() };
  } else {
    canvas.hidden = true;
    stage.appendChild(buildStaticStage(app));
  }

  bindKeys(app);
  syncUrl(store, (patch) => {
    const clean = sanitise(patch, catalog, sheets);
    // An edited address states the whole view: anything it leaves out goes back to its default.
    store.set({
      tab: clean.tab ?? 'model',
      intro: false,
      selected: clean.selected ?? null,
      mount: clean.mount ?? 'stowed',
      traverse: clean.traverse ?? 0,
      elevation: clean.elevation ?? 0,
      strip: clean.strip ?? 0,
      explode: clean.explode ?? 0,
      xray: clean.xray ?? false,
      sheet: clean.sheet ?? store.get().sheet,
      sheetFocus: clean.sheetFocus ?? null,
      isolated: clean.isolated ?? null,
    });
    if (clean.section !== undefined && store.get().tab === 'dossier') tour.goto(clean.section, false);
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
