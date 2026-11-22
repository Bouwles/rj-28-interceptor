import { assetExists } from '../loader/assets';
import { detectCapability } from './capability';
import type { SceneAssets, SceneFailure, SceneResult } from './types';

/**
 * Cheap, synchronous check made before anything is fetched: can this page show
 * the live model at all? A reason means it cannot, and the page becomes the
 * static edition (renders and drawings in place of the canvas).
 */
export function sceneUnavailable(forceStatic: boolean): SceneFailure | null {
  if (forceStatic) return 'forced';
  if (!detectCapability().webgl2) return 'no-gpu';
  if (!assetExists('models/rj28_lod1.glb')) return 'no-model';
  return null;
}

/**
 * Build the scene and load the model. The renderer is a separate chunk, so the
 * static edition never downloads it. Any failure falls back to the static edition.
 */
export async function createScene(
  canvas: HTMLCanvasElement,
  assets: Omit<SceneAssets, 'manifest'> & { manifest: SceneAssets['manifest'] | null },
): Promise<SceneResult> {
  if (!assets.manifest) return { ok: false, reason: 'no-model' };
  try {
    const { createThreeScene } = await import('./three-scene');
    const scene = await createThreeScene(canvas);
    await scene.load({ ...assets, manifest: assets.manifest });
    return { ok: true, scene };
  } catch (err) {
    console.warn('3D scene failed to load', err);
    return { ok: false, reason: 'load-failed' };
  }
}
