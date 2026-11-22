// The contract between the interface and the 3D scene.
//
// The interface never touches three.js. It owns the application state and
// calls the setters below when that state changes; the scene reports what the
// pointer and the camera are doing through events. Every setter is idempotent
// and may be called before the model has finished loading: the scene keeps the
// last value and applies it when it can.

import type { BlueprintView, Isolation, MountState } from '../app/store';
import type { ModelManifest, MountData, Part } from '../data/types';
import type { AssetLoader } from '../loader/assets';

/** What the canvas is doing: the rendered model, the model as a drawing, or nothing (another page). */
export type SceneMode = 'model' | 'blueprint' | 'idle';

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

export interface MountPose {
  /** Degrees, as the mount stands right now. */
  elevationDeg: number;
  traverseDeg: number;
  /** True while the mount is moving. */
  moving: boolean;
}

export interface SceneStats {
  /** Level of detail on screen. */
  lod: 0 | 1;
  triangles: number;
  drawCalls: number;
  /** Device pixels per CSS pixel while the picture is moving (at rest it is always the full ratio). */
  pixelRatio: number;
  /** True once slow frames have made the scene leave the floor mirror out while moving. */
  reduced: boolean;
  /** Mean and worst interval between rendered frames over the last second of animation, ms. */
  frameMs: number;
  worstMs: number;
  /** Mean time spent issuing one frame, ms. */
  cpuMs: number;
}

export interface SceneEvents {
  /** Pointer moved over a part or off the model. */
  hover: (hit: PointerHit) => void;
  /** Click on a part, or on empty space (part: null). */
  pick: (hit: PointerHit) => void;
  /** Double-click on a part. */
  activate: (hit: PointerHit) => void;
  /** Camera changed. Emitted at most once per rendered frame. */
  camera: (readout: CameraReadout) => void;
  /** Measure tool: null while fewer than two points are placed. */
  measure: (m: Measurement | null) => void;
  /** The mount moved. */
  mount: (pose: MountPose) => void;
  /** A level of detail finished loading and is on screen. */
  lod: (level: 0 | 1) => void;
  /** The visitor touched the model for the first time. */
  interact: () => void;
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
  parts: Part[];
  mount: MountData | null;
  /** Resolves a path under `public/` to a URL with the deployment base. */
  url: (path: string) => string;
  /** Stay on LOD1 and the light post chain (phones). */
  light: boolean;
}

export interface SceneController {
  readonly backend: 'webgpu' | 'webgl2';

  /**
   * Load LOD1 and the HDRI; resolve when the first real frame is on screen.
   * LOD0 streams afterwards on capable devices and announces itself through
   * the `lod` event. Reject if the model cannot be shown.
   */
  load(assets: SceneAssets): Promise<void>;
  /** Number of part nodes found in the loaded GLB (checked against the tree). */
  partCount(): number;
  /** Part numbers that have a node in the loaded GLB. */
  partNumbers(): string[];
  /** Can this part be picked right now (drawn, not stripped, not hidden)? */
  pickable(part: string): boolean;
  stats(): SceneStats;
  dispose(): void;

  // ── State, pushed from the store ──────────────────────────────────────────
  setMode(mode: SceneMode): void;
  setSelection(part: string | null): void;
  setVisibility(hidden: ReadonlySet<string>, isolated: Isolation | null): void;
  /** Stow or deploy. `traverseDeg` and `elevationDeg` are where the deployed cannon points. */
  setMount(state: MountState, traverseDeg: number, elevationDeg: number, animate: boolean): void;
  /** Strip-down stage 0 to 4: every stage up to this one is removed. */
  setStrip(stage: number, animate: boolean): void;
  /** 0 to 1; 0 to 0.5 separates assemblies, 0.5 to 1 separates parts. */
  setExplode(amount: number): void;
  setXray(on: boolean): void;
  setMeasure(active: boolean): void;
  setInsets(insets: SceneInsets): void;
  setReducedMotion(on: boolean): void;
  /** Which side the drawing view looks from. */
  setBlueprintView(view: BlueprintView | null, animate: boolean): void;
  setHiddenLines(on: boolean): void;

  // ── Commands ──────────────────────────────────────────────────────────────
  /** Frame a part, an assembly, or the whole model as it now stands (null). */
  frame(target: { part: string } | { assembly: string } | null): void;
  /** Back to the opening view. */
  resetView(): void;

  on<K extends keyof SceneEvents>(type: K, fn: SceneEvents[K]): () => void;
}

export type SceneFailure = 'no-gpu' | 'no-model' | 'no-renderer' | 'load-failed' | 'forced';

export type SceneResult =
  | { ok: true; scene: SceneController }
  | { ok: false; reason: SceneFailure };
