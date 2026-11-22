export type Tab = 'intro' | 'model' | 'blueprints' | 'spec';
export type MountState = 'stowed' | 'deployed';
export type BlueprintView = 'front' | 'side' | 'rear' | 'top' | 'iso';

export const TABS: readonly Tab[] = ['intro', 'model', 'blueprints', 'spec'];
export const VIEWS: readonly BlueprintView[] = ['front', 'side', 'rear', 'top', 'iso'];

export interface Isolation {
  kind: 'part' | 'assembly';
  id: string;
}

export interface SheetFocus {
  part?: string;
  assembly?: string;
}

/** Why the page is showing renders and drawings instead of the live model. */
export type StaticReason = 'forced' | 'no-gpu' | 'no-model' | 'no-renderer' | 'load-failed';

export interface AppState {
  /** `loading` until the first assets are in; then the live 3D scene or the static edition. */
  presentation: 'loading' | 'live' | 'static';
  staticReason: StaticReason | null;
  tab: Tab;
  /** Selected part number. */
  selected: string | null;
  mount: MountState;
  /** Where the deployed cannon points, degrees. */
  traverse: number;
  elevation: number;
  /** Strip-down stage, 0 complete to 4 bare. */
  strip: number;
  /** 0 to 1. Below 0.5 assemblies separate, above it parts separate. */
  explode: number;
  xray: boolean;
  measure: boolean;
  /** Sheet shown on the blueprints tab. */
  sheet: string | null;
  /** What the sheet viewer should centre on. Consumed by the viewer. */
  sheetFocus: SheetFocus | null;
  /** Part numbers switched off in the tree. */
  hidden: ReadonlySet<string>;
  isolated: Isolation | null;
  help: boolean;
  /** Open panel: the parts tree (any screen), or the controls sheet (phone). */
  drawer: 'parts' | 'actions' | null;
  /** Level of detail on screen, once the scene reports one. */
  lod: 0 | 1 | null;
}

export const initialState: AppState = {
  presentation: 'loading',
  staticReason: null,
  tab: 'intro',
  selected: null,
  mount: 'stowed',
  traverse: 0,
  elevation: 0,
  strip: 0,
  explode: 0,
  xray: false,
  measure: false,
  sheet: null,
  sheetFocus: null,
  hidden: new Set(),
  isolated: null,
  help: false,
  drawer: null,
  lod: null,
};

type Listener<S> = (state: S, prev: S) => void;

export class Store<S extends object> {
  private state: S;
  private listeners = new Set<Listener<S>>();

  constructor(initial: S) {
    this.state = initial;
  }

  get(): S {
    return this.state;
  }

  set(patch: Partial<S>): void {
    let changed = false;
    for (const k in patch) {
      if (!Object.is(patch[k], this.state[k])) {
        changed = true;
        break;
      }
    }
    if (!changed) return;
    const prev = this.state;
    this.state = { ...prev, ...patch };
    for (const fn of [...this.listeners]) fn(this.state, prev);
  }

  subscribe(fn: Listener<S>): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  /**
   * Run `fn` now and whenever the selected value changes. Arrays are compared
   * element by element so a selector can pick several fields at once.
   */
  watch<T>(selector: (s: S) => T, fn: (value: T, prev: T | undefined) => void): () => void {
    let last = selector(this.state);
    fn(last, undefined);
    return this.subscribe((s) => {
      const next = selector(s);
      if (same(next, last)) return;
      const before = last;
      last = next;
      fn(next, before);
    });
  }
}

function same(a: unknown, b: unknown): boolean {
  if (Object.is(a, b)) return true;
  if (Array.isArray(a) && Array.isArray(b) && a.length === b.length) {
    return a.every((v, i) => Object.is(v, b[i]));
  }
  return false;
}

/** A single fast-changing value that should not pass through the store (scroll, camera). */
export class Signal<T> {
  private listeners = new Set<(v: T) => void>();
  constructor(private value: T) {}
  get(): T {
    return this.value;
  }
  set(v: T): void {
    this.value = v;
    for (const fn of this.listeners) fn(v);
  }
  subscribe(fn: (v: T) => void, fire = true): () => void {
    this.listeners.add(fn);
    if (fire) fn(this.value);
    return () => this.listeners.delete(fn);
  }
}

export type AppStore = Store<AppState>;
