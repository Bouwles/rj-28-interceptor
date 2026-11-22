import { select, type App } from './context';
import type { SceneController } from '../scene/types';

/**
 * Wire a live scene to the application: store → scene setters, scene events →
 * signals and actions. This is the whole surface between the two halves.
 */
export function bindScene(app: App, scene: SceneController): void {
  const { store } = app;
  let first = true;

  scene.setReducedMotion(app.reducedMotion());
  store.watch(
    (s) => (s.tab === 'model' ? 'model' : s.tab === 'blueprints' && s.sheet === '3d' ? 'blueprint' : 'idle'),
    (mode) => scene.setMode(mode),
  );
  store.watch((s) => s.selected, (part) => scene.setSelection(part));
  store.watch((s) => [s.hidden, s.isolated] as const, ([hidden, isolated]) => scene.setVisibility(hidden, isolated));
  store.watch(
    (s) => [s.mount, s.traverse, s.elevation] as const,
    ([mount, traverse, elevation]) => scene.setMount(mount, traverse, elevation, !first),
  );
  store.watch((s) => s.strip, (stage) => scene.setStrip(stage, !first));
  store.watch((s) => s.explode, (amount) => scene.setExplode(amount));
  store.watch((s) => s.xray, (on) => scene.setXray(on));
  store.watch((s) => s.measure, (on) => scene.setMeasure(on));
  store.watch((s) => s.view, (view) => scene.setBlueprintView(view, !first));
  first = false;

  scene.on('hover', (hit) => app.hover.set(hit));
  scene.on('pick', (hit) => {
    if (store.get().tab === 'model') select(app, hit.part);
  });
  scene.on('activate', (hit) => {
    if (hit.part) {
      select(app, hit.part);
      scene.frame({ part: hit.part });
    }
  });
  scene.on('camera', (r) => app.camera.set(r));
  scene.on('measure', (m) => app.measurement.set(m));
  scene.on('mount', (pose) => app.mountPose.set(pose.moving ? pose : null));
  // The first level of detail is already on screen by the time this runs.
  store.set({ lod: scene.stats().lod });
  scene.on('lod', (lod) => store.set({ lod }));
  scene.on('clip', (clip) => store.set({ clip }));
  scene.on('lost', () => store.set({ presentation: 'static', staticReason: 'load-failed' }));

  app.commands.on('frame', () => {
    const { selected } = store.get();
    scene.frame(selected ? { part: selected } : null);
  });
  app.commands.on('reset', () => scene.resetView());
}
