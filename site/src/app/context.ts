import { findOnSheets, spec, type Catalog } from '../data';
import type { ModelManifest, Part, SheetSet } from '../data/types';
import type { CameraReadout, Measurement, MountPose, PointerHit, SceneController } from '../scene/types';
import { TABS, type AppStore, type Isolation, type MountState, type Signal, type Tab } from './store';

type CommandMap = {
  /** Frame the selection (or the whole model when nothing is selected). */
  frame: void;
  /** Back to the opening view of the model. */
  reset: void;
  /** Step the selection through the tree: +1 next, −1 previous. */
  step: number;
  /** Put the keyboard focus in the tree search field. */
  search: void;
};

export class Commands {
  private map = new Map<keyof CommandMap, Set<(arg: never) => void>>();
  on<K extends keyof CommandMap>(type: K, fn: (arg: CommandMap[K]) => void): () => void {
    let set = this.map.get(type);
    if (!set) this.map.set(type, (set = new Set()));
    set.add(fn as (arg: never) => void);
    return () => set.delete(fn as (arg: never) => void);
  }
  emit<K extends keyof CommandMap>(type: K, ...arg: CommandMap[K] extends void ? [] : [CommandMap[K]]): void {
    for (const fn of this.map.get(type) ?? []) (fn as (a: unknown) => void)(arg[0]);
  }
}

/** Everything a UI module needs. Built once at boot and passed down. */
export interface App {
  store: AppStore;
  catalog: Catalog;
  sheets: SheetSet | null;
  /** `model.json`: what was exported, with counts. */
  manifest: ModelManifest | null;
  camera: Signal<CameraReadout | null>;
  measurement: Signal<Measurement | null>;
  hover: Signal<PointerHit>;
  /** The mount as it stands this frame, while it moves. */
  mountPose: Signal<MountPose | null>;
  commands: Commands;
  scene: SceneController | null;
  reducedMotion: () => boolean;
}

// ── Actions ─────────────────────────────────────────────────────────────────
// The only functions that write to the store. UI modules call these; they
// never patch state directly.

export const STRIP_MAX = spec.strip?.length ? spec.strip.length - 1 : 0;

export function setTab(app: App, tab: Tab): void {
  const s = app.store.get();
  if (s.tab === tab) return;
  const first = app.sheets?.sheets[0]?.id ?? null;
  app.store.set({
    tab,
    measure: false,
    drawer: null,
    sheet: tab === 'blueprints' ? (s.sheet ?? first) : s.sheet,
    sheetFocus: tab === 'blueprints' ? s.sheetFocus : null,
  });
  app.measurement.set(null);
}

export function select(app: App, part: string | null): void {
  if (part && !app.catalog.byNumber.has(part)) return;
  app.store.set({ selected: part });
}

/** Select from outside the model tab (a sheet, a link): the model is where a selection lives. */
export function selectAndInspect(app: App, part: string): void {
  if (!app.catalog.byNumber.has(part)) return;
  app.store.set({ selected: part, tab: 'model', sheetFocus: null });
}

// The sweep that produced the clearance figure covered the traverse with the
// barrel level or below. Above level the traverse is held on centre, as an
// interlock would hold it.
export function setMount(app: App, mount: MountState): void {
  app.store.set({ mount });
}
export function toggleMount(app: App): void {
  setMount(app, app.store.get().mount === 'stowed' ? 'deployed' : 'stowed');
}
export function setElevation(app: App, deg: number): void {
  const [lo, hi] = spec.mount.elevation;
  const elevation = Math.min(hi, Math.max(lo, deg));
  app.store.set({ elevation, traverse: elevation > 0 ? 0 : app.store.get().traverse });
}
export function setTraverse(app: App, deg: number): void {
  const lim = spec.mount.traverse;
  const traverse = Math.min(lim, Math.max(-lim, deg));
  const s = app.store.get();
  app.store.set({ traverse, elevation: traverse !== 0 && s.elevation > 0 ? 0 : s.elevation });
}

export function setStrip(app: App, stage: number): void {
  app.store.set({ strip: Math.min(STRIP_MAX, Math.max(0, Math.round(stage))) });
}

export function setExplode(app: App, amount: number): void {
  app.store.set({ explode: Math.min(1, Math.max(0, amount)) });
}

export function toggleXray(app: App): void {
  app.store.set({ xray: !app.store.get().xray });
}

export function toggleMeasure(app: App): void {
  const on = !app.store.get().measure;
  app.store.set({ measure: on });
  if (!on) app.measurement.set(null);
}

/** Everything on the model tab back to how the page opened. */
export function resetModel(app: App): void {
  app.store.set({ explode: 0, strip: 0, xray: false, measure: false, hidden: new Set(), isolated: null, selected: null });
  app.measurement.set(null);
  app.commands.emit('reset');
}

export function openSheet(app: App, id?: string, focus?: { part?: string; assembly?: string }): void {
  const set = app.sheets;
  if (!set || set.sheets.length === 0) return;
  const sheet = set.sheets.find((s) => s.id === id) ?? set.sheets.find((s) => s.id === app.store.get().sheet) ?? set.sheets[0]!;
  app.store.set({ tab: 'blueprints', measure: false, sheet: sheet.id, sheetFocus: focus ?? null, help: false, drawer: null });
}

/** The model as a drawing, on the blueprints page. */
export function openBlueprint3d(app: App): void {
  app.store.set({ tab: 'blueprints', sheet: '3d', sheetFocus: null, measure: false, help: false, drawer: null });
  app.measurement.set(null);
}

export function setHidden(app: App, numbers: readonly string[], hidden: boolean): void {
  const next = new Set(app.store.get().hidden);
  for (const n of numbers) {
    if (hidden) next.add(n);
    else next.delete(n);
  }
  app.store.set({ hidden: next });
}

export function showAll(app: App): void {
  app.store.set({ hidden: new Set(), isolated: null });
}

export function isolate(app: App, target: Isolation | null): void {
  const cur = app.store.get().isolated;
  const sameTarget = !!cur && !!target && cur.kind === target.kind && cur.id === target.id;
  app.store.set({ isolated: sameTarget ? null : target });
}

/** Is this part drawn, given the hide set and any isolation? */
export function isVisible(app: App, part: Part): boolean {
  const { hidden, isolated } = app.store.get();
  if (hidden.has(part.number)) return false;
  if (!isolated) return true;
  return isolated.kind === 'part' ? isolated.id === part.number : isolated.id === part.assembly;
}

/** Has the strip-down taken this part off? */
export function isStripped(app: App, part: Part): boolean {
  const stage = part.strip ?? 0;
  return stage > 0 && stage <= app.store.get().strip;
}

/** Esc: close the topmost thing, one layer per press. */
export function clear(app: App): void {
  const s = app.store.get();
  if (s.help) app.store.set({ help: false });
  else if (s.drawer) app.store.set({ drawer: null });
  else if (s.measure) toggleMeasure(app);
  else if (s.selected) app.store.set({ selected: null });
  else if (s.isolated) app.store.set({ isolated: null });
}

export function isTab(v: string | null): v is Tab {
  return !!v && (TABS as readonly string[]).includes(v);
}

/** Open the sheet that shows this part, centred on it. Returns false when no sheet does. */
export function showInDrawing(app: App, part: Part): boolean {
  const hit = findOnSheets(app.sheets, part);
  if (!hit) return false;
  openSheet(app, hit.sheet.id, hit.exact ? { part: part.number } : { assembly: part.assembly });
  return true;
}
