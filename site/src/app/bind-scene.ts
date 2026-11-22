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
  store.watch((s) => s.mode, (mode) => scene.setMode(mode, !first));
  store.watch((s) => s.selected, (part) => scene.setSelection(part));
  store.watch((s) => [s.hidden, s.isolated] as const, ([hidden, isolated]) => scene.setVisibility(hidden, isolated));
  store.watch((s) => s.mount, (mount) => scene.setMount(mount, !first));
  store.watch((s) => (s.mode === 'explode' ? s.explode : 0), (amount) => scene.setExplode(amount));
  store.watch((s) => s.xray, (on) => scene.setXray(on));
  store.watch((s) => s.measure, (on) => scene.setMeasure(on));
  store.watch((s) => s.view, (view) => scene.setBlueprintView(view, !first));
  store.watch((s) => s.hiddenLines, (on) => scene.setHiddenLines(on));
  app.tour.subscribe((u) => scene.setTour(u));
  first = false;

  scene.on('hover', (hit) => app.hover.set(hit));
  scene.on('pick', (hit) => {
    if (store.get().mode !== 'tour') select(app, hit.part);
  });
  scene.on('camera', (r) => app.camera.set(r));
  scene.on('measure', (m) => app.measurement.set(m));
  scene.on('lost', () => store.set({ presentation: 'static', staticReason: 'load-failed' }));

  app.commands.on('frame', () => {
    const { selected } = store.get();
    scene.frame(selected ? { part: selected } : null);
  });
}
