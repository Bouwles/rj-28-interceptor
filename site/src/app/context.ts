import { findOnSheets, type Catalog } from '../data';
import type { Part, SheetSet, Station } from '../data/types';
import type { CameraReadout, Measurement, PointerHit, SceneController } from '../scene/types';
import {
  MODES,
  type AppStore,
  type BlueprintView,
  type Isolation,
  type Mode,
  type MountState,
  type Signal,
} from './store';

type CommandMap = {
  /** Frame the selection (or the whole model when nothing is selected). */
  frame: void;
  /** Step the selection through the tree: +1 next, −1 previous. */
  step: number;
  /** Put the keyboard focus in the tree search field. */
  search: void;
  /** Scroll the tour to a section index. */
  goto: number;
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
  stations: Station[] | null;
  /** Scroll tour position: section index + progress through it. */
  tour: Signal<number>;
  camera: Signal<CameraReadout | null>;
  measurement: Signal<Measurement | null>;
  hover: Signal<PointerHit>;
  commands: Commands;
  scene: SceneController | null;
  reducedMotion: () => boolean;
}

// ── Actions ─────────────────────────────────────────────────────────────────
// The only functions that write to the store. UI modules call these; they
// never patch state directly.

export function setMode(app: App, mode: Mode): void {
  const s = app.store.get();
  if (s.mode === mode) return;
  app.store.set({
    mode,
    measure: false,
    drawer: false,
    sheet: null,
    sheetFocus: null,
    // Entering the exploded view at zero would show nothing happening.
    explode: mode === 'explode' && s.explode === 0 ? 0.5 : s.explode,
  });
  app.measurement.set(null);
}

export function cycleMode(app: App, mode: Mode): void {
  // Pressing a mode key again returns to the inspector, the neutral mode.
  setMode(app, app.store.get().mode === mode && mode !== 'inspect' ? 'inspect' : mode);
}

export function select(app: App, part: string | null): void {
  if (part && !app.catalog.byNumber.has(part)) return;
  app.store.set({ selected: part });
}

/** Select from outside the tour (a sheet, a link): the inspector is where a selection lives. */
export function selectAndInspect(app: App, part: string): void {
  if (!app.catalog.byNumber.has(part)) return;
  const s = app.store.get();
  app.store.set({
    selected: part,
    sheet: null,
    sheetFocus: null,
    mode: s.mode === 'tour' ? 'inspect' : s.mode,
  });
}

export function setMount(app: App, mount: MountState): void {
  app.store.set({ mount });
}

export function toggleMount(app: App): void {
  setMount(app, app.store.get().mount === 'stowed' ? 'deployed' : 'stowed');
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

export function setView(app: App, view: BlueprintView): void {
  app.store.set({ view });
}

export function toggleHiddenLines(app: App): void {
  app.store.set({ hiddenLines: !app.store.get().hiddenLines });
}

export function openSheet(app: App, id?: string, focus?: { part?: string; assembly?: string }): void {
  const set = app.sheets;
  if (!set || set.sheets.length === 0) return;
  const sheet = set.sheets.find((s) => s.id === id) ?? set.sheets[0]!;
  app.store.set({ sheet: sheet.id, sheetFocus: focus ?? null, help: false, drawer: false });
}

export function closeSheet(app: App): void {
  app.store.set({ sheet: null, sheetFocus: null });
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

/** Esc: close the topmost thing, one layer per press. */
export function clear(app: App): void {
  const s = app.store.get();
  if (s.help) app.store.set({ help: false });
  else if (s.sheet) closeSheet(app);
  else if (s.drawer) app.store.set({ drawer: false });
  else if (s.measure) toggleMeasure(app);
  else if (s.selected) app.store.set({ selected: null });
  else if (s.isolated) app.store.set({ isolated: null });
}

export function isMode(v: string | null): v is Mode {
  return !!v && (MODES as readonly string[]).includes(v);
}

/** Open the sheet that shows this part, centred on it. Returns false when no sheet does. */
export function showInDrawing(app: App, part: Part): boolean {
  const hit = findOnSheets(app.sheets, part);
  if (!hit) return false;
  openSheet(app, hit.sheet.id, hit.exact ? { part: part.number } : { assembly: part.assembly });
  return true;
}
