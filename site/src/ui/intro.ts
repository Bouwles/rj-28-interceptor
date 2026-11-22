import { dismissIntro, type App } from '../app/context';
import { spec } from '../data';
import { num } from '../data/format';
import { h } from './dom';

/**
 * Title block on the model tab: designation, class and the four headline
 * figures. It holds the left column until the visitor touches the model or
 * the page, then makes way for the assembly tree.
 */
export function buildIntro(app: App): HTMLElement {
  const [type, mark] = spec.designation.split(' ');
  const el = h(
    'section.intro',
    { 'aria-label': 'Title block' },
    h('h1.cover-title', null, h('span.cover-type', null, type), ' ', h('span.cover-mark', null, mark)),
    h('p.cover-class', null, spec.klass),
    h(
      'dl.cover-figures',
      null,
      h('div', null, h('dt.cap', null, 'Height'), h('dd', null, num(spec.height_to_cap_crown, 0), h('span.unit', null, ' mm'))),
      h('div', null, h('dt.cap', null, 'Mass, ready'), h('dd', null, num(spec.mass.total_kg, 0), h('span.unit', null, ' kg'))),
      h('div', null, h('dt.cap', null, 'Degrees of freedom'), h('dd', null, num(spec.dof.total, 0))),
      h('div', null, h('dt.cap', null, 'Named parts'), h('dd', null, num(app.catalog.parts.length, 0))),
    ),
    h('p.intro-hint', null, 'Drag to turn the model. Pick a part to read what it is. The actions on the right move the cannon and take the armour off.'),
    h('button.btn', { type: 'button', onclick: () => dismissIntro(app) }, 'Open the parts list'),
  );
  app.store.watch(
    (s) => s.intro && s.tab === 'model',
    (show) => (el.hidden = !show),
  );
  return el;
}
