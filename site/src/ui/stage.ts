import type { App } from '../app/context';
import { spec } from '../data';
import { num } from '../data/format';
import { BoxModel, VIEW_TITLE } from './boxmodel';
import { h } from './dom';

/** Text alternative for the canvas: what a reader would see, in a sentence or two. */
export function canvasSummary(partCount: number): string {
  return (
    `Interactive 3D model of ${spec.designation}: a ${num(spec.height_to_cap_crown, 0)} mm tall black humanoid robot with heavy armour over exposed actuators, ` +
    `a hard cap worn brim to the rear, and one cannon on a mount behind the right shoulder that stands vertical when stowed and lies level when deployed. ` +
    `${num(partCount, 0)} parts in ${spec.mass.by_assembly.length} assemblies. The same information is in the specification.`
  );
}

/**
 * Stand-in for the model when there is no WebGL 2 or the model did not load:
 * front and side drawings of the part envelopes, which can still be picked.
 */
export function buildStaticStage(app: App): HTMLElement {
  const front = new BoxModel(app, 'front', { dimensions: false });
  const side = new BoxModel(app, 'side', { dimensions: false });
  const root = h(
    'div.stage-boxes',
    null,
    h('figure.boxfig', null, front.el, h('figcaption', null, VIEW_TITLE.front)),
    h('figure.boxfig', null, side.el, h('figcaption', null, VIEW_TITLE.side)),
  );
  app.store.watch(
    (s) => s.tab,
    (tab) => (root.hidden = tab !== 'model'),
  );
  return root;
}
