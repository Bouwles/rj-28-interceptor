import { assetExists } from '../loader/assets';
import { detectCapability } from './capability';
import type { SceneAssets, SceneController, SceneFailure, SceneResult } from './types';

export type SceneFactory = (canvas: HTMLCanvasElement) => Promise<SceneController>;

/** Set to true by the milestone that adds `./three-scene`. */
const RENDERER_BUILT = false;

/**
 * The renderer is a separate chunk so the static edition never downloads it.
 * When it exists this becomes
 * `(await import('./three-scene')).createThreeScene`.
 */
async function loadFactory(): Promise<SceneFactory | null> {
  return null;
}

/**
 * Cheap, synchronous check made before anything is fetched: can this page show
 * the live model at all? A reason means it cannot, and the page becomes the
 * static edition (renders and drawings in place of the canvas).
 */
export function sceneUnavailable(forceStatic: boolean): SceneFailure | null {
  if (forceStatic) return 'forced';
  const gpu = detectCapability();
  if (!gpu.webgpu && !gpu.webgl2) return 'no-gpu';
  if (!assetExists('models/rj28_lod1.glb')) return 'no-model';
  if (!RENDERER_BUILT) return 'no-renderer';
  return null;
}

/** Build the scene and load the model. Any failure falls back to the static edition. */
export async function createScene(
  canvas: HTMLCanvasElement,
  assets: Omit<SceneAssets, 'manifest'> & { manifest: SceneAssets['manifest'] | null },
): Promise<SceneResult> {
  if (!assets.manifest) return { ok: false, reason: 'no-model' };
  const factory = await loadFactory();
  if (!factory) return { ok: false, reason: 'no-renderer' };
  try {
    const scene = await factory(canvas);
    await scene.load({ ...assets, manifest: assets.manifest });
    return { ok: true, scene };
  } catch (err) {
    console.warn('3D scene failed to load', err);
    return { ok: false, reason: 'load-failed' };
  }
}
