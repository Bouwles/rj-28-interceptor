// The introduction: the page the site opens on. Everything here comes from
// spec.json, which is part of the bundle, so it is on screen at once while the
// model loads behind it.

import type { AppStore, Tab } from '../app/store';
import { publicUrl, spec } from '../data';
import { deg, jointLabel, kg, mm, num, range, trim1 } from '../data/format';
import { imageSize } from '../loader/assets';
import { specTable, type SpecRow } from './charts';
import { h, type Child } from './dom';

const FOOTER = 'Design and build: Paul Nercessian.';

const joint = (name: string) => spec.joints.find((j) => j.name === name);
const jointRow = (name: string): SpecRow => {
  const j = joint(name);
  return j ? [jointLabel(j.name), range(j.range)] : null;
};
const assembly = (id: string) => spec.mass.by_assembly.find((a) => a.assembly === id);
const words = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];

function feature(file: string, alt: string, title: string, text: string[], rows: SpecRow[], flip: boolean): HTMLElement {
  const size = imageSize(`renders/${file}`);
  return h(
    'section.feature',
    { class: flip ? 'flip' : '' },
    h('div.feature-image', null, h('img', { src: publicUrl(`renders/${file}`), alt, loading: 'lazy', decoding: 'async', width: size?.width ?? null, height: size?.height ?? null })),
    h('div.feature-text', null, h('h2', null, title), text.map((t) => h('p', null, t)), specTable(rows)),
  );
}

export function buildIntro(store: AppStore): HTMLElement {
  const go = (tab: Tab) => () => store.set({ tab });
  const m = spec.mount;
  const knee = spec.design_notes.find((n) => n.title.startsWith('Static knee'));
  const k = knee?.inputs as { crank_radius_mm: number; actuator_stroke_mm: number; actuators_per_knee: number } | undefined;
  const head = assembly('01');
  const mountAsm = assembly('15');
  const strip = spec.strip ?? [];
  const armourOff = strip.filter((s) => s.stage === 1 || s.stage === 2).reduce((t, s) => t + s.parts, 0);
  const figure = (label: string, value: string, unit?: string): Child =>
    h('div', null, h('dd', null, value, unit ? h('span.unit', null, ` ${unit}`) : null), h('dt', null, label));

  const hero = h(
    'section.hero',
    null,
    h(
      'picture.hero-image',
      null,
      h('source', { media: '(max-width: 760px)', srcset: publicUrl('renders/front_deployed.jpg') }),
      h('img', { src: publicUrl('renders/social_card.jpg'), alt: 'The robot from the front left: black armour over exposed actuators, a hard cap worn brim to the rear, the cannon level over its right shoulder.', decoding: 'async' }),
    ),
    h(
      'div.hero-text',
      null,
      h('h1', null, 'RJ-28 Interceptor'),
      h(
        'p.hero-lead',
        null,
        `A ${trim1(spec.height_to_cap_crown / 10)} cm autonomous humanoid that carries one cannon behind its right shoulder, modelled part by part and measured from the model.`,
      ),
      h(
        'div.hero-actions',
        null,
        h('button.btn.btn-primary', { type: 'button', onclick: go('model') }, 'Open the model'),
        h('button.btn.btn-quiet', { type: 'button', onclick: go('blueprints') }, 'Blueprints'),
        h('button.btn.btn-quiet', { type: 'button', onclick: go('spec') }, 'Specification'),
      ),
      h(
        'dl.hero-figures',
        null,
        figure('Height', num(spec.height_to_cap_crown, 0), 'mm'),
        figure('Mass, ready', num(spec.mass.total_kg, 0), 'kg'),
        figure('Degrees of freedom', num(spec.dof.total, 0)),
        figure('Named parts', num(spec.part_count, 0)),
      ),
    ),
  );

  const page = h(
    'main.intro-page',
    { id: 'intro' },
    hero,
    h(
      'div.features',
      null,
      feature(
        'head_cap.jpg',
        'Close view of the head: a raked faceplate with one lit slit, a three-lens cluster on the left cheek and a six-panel hard cap with its brim to the rear.',
        'Head and cap',
        [
          'The head has no face. A raked plate carries one recessed slit with a stereo camera pair behind dark glass, and three lenses on the left cheek: thermal imager, lidar window and spotter camera.',
          'The cap is a rigid composite shell bolted to the skull frame and worn brim to the rear. The brim stands out over the nape so the sensor bar under its lip sees down the back of the machine without the head turning.',
        ],
        [
          ['Sensor slit, height from floor', mm(spec.landmarks.sensor_slit!)],
          jointRow('neck_yaw'),
          jointRow('neck_pitch'),
          head && [`Head and cap, ${num(head.parts, 0)} parts`, kg(head.mass_kg)],
        ],
        false,
      ),
      feature(
        'mount.jpg',
        'Close view of the mount from the right rear: the round pivot housing on its yoke, the swing arm bolted to the breech, and the gear sector below.',
        'One axis, two jobs',
        [
          `The trunnion swings the cannon between stowed and deployed, and it is the elevation axis in use. At ${deg(m.elevation[1])} the barrel stands vertical behind the right shoulder; at ${deg(0)} it lies level above the shoulder armour, pointing where the robot faces.`,
          `The cannon rides above the trunnion on a swing arm, which keeps the stowed barrel behind the shoulder and not beside the head. A slewing ring under the yoke gives traverse once deployed.`,
        ],
        [
          ['Elevation', range(m.elevation)],
          ['Traverse', range([-m.traverse, m.traverse])],
          ['Barrel', `Ø${trim1(m.barrel_od)} × ${trim1(m.barrel_length)} mm`],
          m.min_clearance_mm !== undefined && ['Least clearance through the travel', mm(m.min_clearance_mm)],
          mountAsm && [`Mount, ${num(mountAsm.parts, 0)} parts`, kg(mountAsm.mass_kg)],
        ],
        true,
      ),
      feature(
        'knee.jpg',
        'Close view of a knee: a round bearing housing on the joint axis between thigh and shin, with actuator rods and bellows behind.',
        'A knee driven like plant',
        [
          k
            ? `The knee is a crank joint. ${words[k.actuators_per_knee]?.replace(/^./, (c) => c.toUpperCase()) ?? k.actuators_per_knee} planetary roller-screw actuators behind the thigh act on a ${trim1(k.crank_radius_mm)} mm crank, while round bearing housings stay on the knee axis.`
            : 'The knee is a crank joint driven by linear actuators behind the thigh.',
          knee ? `In a deep squat each knee holds ${num(knee.result.torque_per_knee_nm!, 0)} N m, which asks ${num(knee.result.force_per_actuator_kn!, 1)} kN of each actuator. The working is in the specification.` : '',
        ],
        [
          jointRow('knee_pitch_L'),
          k && ['Actuator stroke', mm(k.actuator_stroke_mm)],
          ['Knee axis, height from floor', mm(spec.landmarks.knee_axis!)],
          jointRow('ankle_pitch_L'),
        ],
        false,
      ),
      feature(
        'exploded.jpg',
        'The whole robot exploded: armour panels stand off their carriers, actuators and frames hang in the gaps, and the mount is laid out to one side.',
        'Every bulky volume contains something',
        [
          `The model has ${num(spec.part_count, 0)} named parts in ${num(spec.mass.by_assembly.length, 0)} assemblies, each with a function, a material and a mass. Three rotary actuators fill each shoulder, the hand drive fills each forearm, and the battery, compute and power distribution fill the chest.`,
          armourOff ? `In the model the armour comes off in stages. The first two remove ${num(armourOff, 0)} parts and leave the frame, the drives and the harness to look at.` : '',
        ],
        [
          ['Structure', kg(spec.mass.by_class.structure!, 1)],
          ['Actuators', kg(spec.mass.by_class.actuator!, 1)],
          ['Armour', kg(spec.mass.by_class.armour!, 1)],
          ['Battery', kg(spec.mass.by_class.battery!, 1)],
          ['Total, ready', kg(spec.mass.total_kg, 1)],
        ],
        true,
      ),
    ),
    h(
      'section.closing',
      null,
      h('h2', null, 'Turn it over, take it apart'),
      h('p', null, 'The model is live: stow and deploy the cannon, remove the armour layer by layer, and pick any part to read what it is.'),
      h('div.hero-actions', null, h('button.btn.btn-primary', { type: 'button', onclick: go('model') }, 'Open the model')),
    ),
    h('footer.site-footer', null, h('p', null, FOOTER)),
  );
  store.watch(
    (s) => s.tab,
    (tab) => {
      page.classList.toggle('is-open', tab === 'intro');
      page.inert = tab !== 'intro';
    },
  );
  return page;
}
