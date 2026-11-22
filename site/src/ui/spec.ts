// Specification tab: the reference page. Plain tables, everything from the JSON.

import { selectAndInspect, type App } from '../app/context';
import { spec } from '../data';
import { dims, jointLabel, kg, mm, num, partMass, range, trim1 } from '../data/format';
import type { Assembly } from '../data/types';
import { barChart, designNote, specTable } from './charts';
import { h, type Child } from './dom';

const GROUP_TITLE: Record<string, string> = { leg: 'Legs', waist: 'Waist', arm: 'Arms', hand: 'Hands', neck: 'Neck', mount: 'Mount' };
const capital = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
const vec = (v: readonly number[], digits = 0) => v.map((x) => num(x, digits)).join(', ');

function section(id: string, title: string, ...body: Child[]): HTMLElement {
  return h('section.spec-section', { id: `spec-${id}`, 'aria-labelledby': `spec-${id}-h` }, h('h2', { id: `spec-${id}-h` }, title), ...body);
}

function jointsTable(): HTMLElement {
  const side = (name: string) => (name.endsWith('_L') ? 'Left' : name.endsWith('_R') ? 'Right' : '');
  return h(
    'table.grid.spec-table',
    null,
    h(
      'thead',
      null,
      h(
        'tr',
        null,
        h('th', { scope: 'col' }, 'Joint'),
        h('th', { scope: 'col' }, 'Side'),
        h('th', { scope: 'col' }, 'Range'),
        h('th', { scope: 'col' }, 'Origin, mm'),
        h('th', { scope: 'col' }, 'Axis'),
        h('th.left', { scope: 'col' }, 'Drive'),
      ),
    ),
    Object.keys(GROUP_TITLE).map((g) => {
      const joints = spec.joints.filter((j) => j.group === g);
      if (!joints.length) return null;
      return h(
        'tbody',
        null,
        h('tr.group', null, h('th', { scope: 'rowgroup', colspan: '6' }, `${GROUP_TITLE[g]}, ${joints.length}`)),
        joints.map((j) =>
          h(
            'tr',
            null,
            h('th', { scope: 'row' }, jointLabel(j.name)),
            h('td.left', null, side(j.name)),
            h('td.data', null, range(j.range)),
            h('td.data', null, vec(j.origin, 1)),
            h('td.data', null, vec(j.axis, 3)),
            h('td.left', null, j.drive),
          ),
        ),
      );
    }),
  );
}

/** Bill of materials for one assembly. Built when the assembly is first opened. */
function bomTable(app: App, a: Assembly): HTMLElement {
  return h(
    'table.grid.spec-table.bom',
    null,
    h(
      'thead',
      null,
      h(
        'tr',
        null,
        h('th', { scope: 'col' }, 'Part number'),
        h('th.left', { scope: 'col' }, 'Name'),
        h('th.left', { scope: 'col' }, 'Material'),
        h('th', { scope: 'col' }, 'Qty'),
        h('th', { scope: 'col' }, 'Size, mm'),
        h('th', { scope: 'col' }, 'Mass'),
      ),
    ),
    h(
      'tbody',
      null,
      a.parts.map((p) =>
        h(
          'tr',
          null,
          h('th', { scope: 'row' }, h('button.link.data', { type: 'button', title: 'Show in the model', onclick: () => selectAndInspect(app, p.number) }, p.number)),
          h('td.left', null, p.name),
          h('td.left', null, capital(p.material)),
          h('td.data', null, num(p.count, 0)),
          h('td.data', null, dims(p.size)),
          h('td.data', null, partMass(p.mass_kg)),
        ),
      ),
    ),
  );
}

export function buildSpec(app: App): HTMLElement {
  const { catalog } = app;
  const m = spec.mount;
  const t = spec.targets;
  const env = spec.envelope;

  const principal = section(
    'data',
    'Principal data',
    h(
      'div.spec-cols',
      null,
      specTable(
        [
          ['Designation', spec.designation],
          ['Class', spec.klass, true],
          ['Serial', spec.serial],
          ['Height to cap crown', mm(spec.height_to_cap_crown)],
          ['Height, mount stowed', mm(env.stowed.height)],
          ['Height, mount deployed', mm(env.deployed.height)],
          ['Width over the arms', mm(spec.body.width)],
          ['Span over shoulder armour', mm(spec.shoulder_armour_span)],
          ['Depth, body', mm(spec.body.depth)],
          ['Depth, mount stowed', mm(env.stowed.depth)],
          ['Depth, mount deployed', mm(env.deployed.depth)],
        ],
        'Dimensions',
      ),
      specTable(
        [
          ['Mass, ready', kg(spec.mass.total_kg, 1)],
          ['Degrees of freedom', num(spec.dof.total, 0)],
          ['Parts', num(catalog.parts.length, 0)],
          ['Assemblies', num(catalog.assemblies.length, 0)],
          ['Power', t.power, true],
          ['Average draw, mixed duty', `${num(t.average_draw_kw, 1)} kW`],
          ['Walk', `${num(t.walk_kmh, 0)} km/h`],
          ['Run', `${num(t.run_kmh, 0)} km/h`],
          ['Sealing', t.sealing],
        ],
        'Mass, power and targets',
      ),
      specTable(
        [
          ['Barrel', `Ø${trim1(m.barrel_od)} × ${trim1(m.barrel_length)} mm`],
          ['Elevation', range(m.elevation)],
          ['Traverse', range([-m.traverse, m.traverse])],
          ['Trunnion, x, y, z', `${vec(m.trunnion)} mm`],
          ['Bore above trunnion', mm(m.bore_rise)],
          m.min_clearance_mm !== undefined && ['Least clearance through the travel', mm(m.min_clearance_mm)],
          m.required_clearance_mm !== undefined && ['Clearance required', mm(m.required_clearance_mm)],
        ],
        'Mount',
      ),
      specTable(
        Object.entries(spec.landmarks).map(([k, v]) => [capital(k.replace(/_/g, ' ')), mm(v)]),
        'Landmarks',
      ),
    ),
    h('p.spec-foot', null, 'Axes: Z up, the robot faces −Y, its left is +X, origin on the floor between the feet. Millimetres.'),
  );

  const dofRows = Object.entries(spec.dof).filter(([k]) => k !== 'total');
  const joints = section(
    'joints',
    `Joints, ${num(spec.joints.length, 0)} degrees of freedom`,
    h('p.spec-lead', null, dofRows.map(([k, v]) => `${capital(k)} ${num(v, 0)}`).join(', ') + '.'),
    h('div.spec-scroll', null, jointsTable()),
  );

  const cls = spec.mass.by_class;
  const mass = section(
    'mass',
    'Mass roll-up',
    h(
      'div.spec-cols.two',
      null,
      barChart(
        'By class',
        Object.entries(cls)
          .map(([k, v]) => ({ label: capital(k), value: v, extra: num(spec.mass.fill_factors[k] ?? 0, 3) }))
          .sort((a, b) => b.value - a.value),
        { unit: 'kg', digits: 2, extraHead: 'Fill factor', valueHead: 'Mass' },
      ),
      barChart(
        'By assembly',
        spec.mass.by_assembly.map((a) => ({ label: `${a.assembly} ${a.name}`, value: a.mass_kg, extra: num(a.parts, 0) })),
        { unit: 'kg', digits: 2, extraHead: 'Parts', valueHead: 'Mass' },
      ),
    ),
    h(
      'p.spec-foot',
      null,
      `Total ${kg(spec.mass.total_kg)} against a target of ${kg(spec.mass.target_kg, 1)}. The middle column by class is the fill factor: the share of a part's envelope volume that is material. Common scale ${num(spec.mass.common_scale, 4)}.`,
    ),
  );

  const notes = section('notes', 'Design notes', h('div.spec-cols.notes', null, spec.design_notes.map((n, i) => designNote(n, i))));

  const bom = section(
    'bom',
    'Bill of materials',
    h('p.spec-lead', null, 'By assembly. A part number opens that part in the model.'),
    catalog.assemblies.map((a) => {
      const body = h('div.spec-scroll');
      const d = h(
        'details.bom-asm',
        null,
        h(
          'summary',
          null,
          h('span.data', null, a.id),
          h('span.bom-name', null, a.name),
          h('span.data', null, `${num(a.parts.length, 0)} parts`),
          h('span.data', null, kg(a.mass_kg)),
        ),
        body,
      );
      d.addEventListener('toggle', () => {
        if (d.open && !body.firstChild) body.appendChild(bomTable(app, a));
      });
      return d;
    }),
  );

  const nav = h(
    'nav.spec-nav',
    { 'aria-label': 'Specification contents' },
    [
      ['data', 'Principal data'],
      ['joints', 'Joints'],
      ['mass', 'Mass roll-up'],
      ['notes', 'Design notes'],
      ['bom', 'Bill of materials'],
    ].map(([id, label]) =>
      h('a', { href: `#spec-${id}`, onclick: (e: Event) => { e.preventDefault(); document.getElementById(`spec-${id}`)?.scrollIntoView({ block: 'start' }); } }, label),
    ),
  );

  const page = h(
    'main.spec-page',
    { hidden: true, id: 'specification', tabindex: '-1' },
    h('div.spec-inner', null, h('header.spec-head', null, h('h1', null, 'Specification'), h('p', null, `${spec.klass}.`)), nav, principal, joints, mass, notes, bom,
      h('footer.site-footer', null, h('p', null, 'Design and build: Paul Nercessian.'))),
  );
  app.store.watch(
    (s) => s.tab,
    (tab) => (page.hidden = tab !== 'spec'),
  );
  return page;
}
