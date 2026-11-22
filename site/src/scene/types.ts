// The contract between the interface and the 3D scene.
//
// The interface never touches three.js. It owns the application state and
// calls the setters below when that state changes; the scene reports what the
// pointer and the camera are doing through events. Every setter is idempotent
// and may be called before the model has finished loading: the scene keeps the
// last value and applies it when it can.

import type { BlueprintView, Isolation, Mode, MountState } from '../app/store';
import type { ModelManifest, MountData, Station } from '../data/types';
import type { AssetLoader } from '../loader/assets';

export interface CameraReadout {
  /** Degrees round the vertical axis; 0 looks at the robot's front, positive towards its left. */
  azimuthDeg: number;
  /** Degrees above the horizontal. */
  elevationDeg: number;
  /** Camera to orbit target in millimetres, or null for an orthographic camera. */
  distanceMm: number | null;
}

export interface Measurement {
  /** Millimetres, model axes (Z up, robot faces −Y). */
  a: [number, number, number];
  b: [number, number, number];
  distanceMm: number;
  /** Set when the two points were taken on a flat projection and not in 3D. */
  plane?: 'front' | 'side' | 'rear' | 'top';
}

export interface PointerHit {
  /** Part number under the pointer, or null. */
  part: string | null;
  clientX: number;
  clientY: number;
}

export interface SceneEvents {
  /** Pointer moved over a part or off the model. */
  hover: (hit: PointerHit) => void;
  /** Click on a part, or on empty space (part: null). */
  pick: (hit: PointerHit) => void;
  /** Camera changed. Emitted at most once per rendered frame. */
  camera: (readout: CameraReadout) => void;
  /** Measure tool: null while fewer than two points are placed. */
  measure: (m: Measurement | null) => void;
  /** Mount animation position, 0 stowed to 1 deployed. */
  mount: (t: number) => void;
  /** A level of detail finished loading and is on screen. */
  lod: (level: 0 | 1) => void;
  /** The context was lost and could not be restored; the app falls back to the static edition. */
  lost: () => void;
}

export interface SceneInsets {
  /** CSS pixels of the canvas covered by interface on each side; framing centres in what is left. */
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface SceneAssets {
  loader: AssetLoader;
  /** `model.json`: file names, byte sizes and counts of the exported GLBs. */
  manifest: ModelManifest;
  stations: Station[] | null;
  mount: MountData | null;
  /** Resolves a path under `public/` to a URL with the deployment base. */
  url: (path: string) => string;
}

export interface SceneController {
  readonly backend: 'webgpu' | 'webgl2';

  /**
   * Load LOD1, the HDRI and the edge lines; resolve when the first real frame
   * is on screen. LOD0 streams afterwards on capable devices and announces
   * itself through the `lod` event. Reject if the model cannot be shown.
   */
  load(assets: SceneAssets): Promise<void>;
  /** Number of part nodes found in the loaded GLB (checked against the tree). */
  partCount(): number;
  dispose(): void;

  // ── State, pushed from the store ──────────────────────────────────────────
  setMode(mode: Mode, animate: boolean): void;
  /**
   * Scroll tour position: `u = station index + progress through that section`,
   * 0 ≤ u ≤ last index. The scene holds, travels and scrubs the mount from this.
   */
  setTour(u: number): void;
  setSelection(part: string | null): void;
  setVisibility(hidden: ReadonlySet<string>, isolated: Isolation | null): void;
  setMount(state: MountState, animate: boolean): void;
  /** 0 to 1; 0 to 0.5 separates assemblies, 0.5 to 1 separates parts. */
  setExplode(amount: number): void;
  setXray(on: boolean): void;
  setMeasure(active: boolean): void;
  setBlueprintView(view: BlueprintView, animate: boolean): void;
  setHiddenLines(on: boolean): void;
  setInsets(insets: SceneInsets): void;
  setReducedMotion(on: boolean): void;

  // ── Commands ──────────────────────────────────────────────────────────────
  /** Frame a part, an assembly, or the whole model (null). */
  frame(target: { part: string } | { assembly: string } | null): void;

  on<K extends keyof SceneEvents>(type: K, fn: SceneEvents[K]): () => void;
}

export type SceneFailure = 'no-gpu' | 'no-model' | 'no-renderer' | 'load-failed' | 'forced';

export type SceneResult =
  | { ok: true; scene: SceneController }
  | { ok: false; reason: SceneFailure };
