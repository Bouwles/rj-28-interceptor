// The ten tour sections: copy, tables and figures. Every figure in the text is
// read from spec.json or parts.json at run time; nothing numeric is typed here.

import { openSheet, setMode, type App } from '../app/context';
import { KEY_ROWS } from '../app/keys';
import { spec } from '../data';
import { deg, dims, jointLabel, kg, mm, num, range, trim1 } from '../data/format';
import type { Joint, Part } from '../data/types';
import { barChart, designNote, heightLadder, momentArmPlot, specTable, type SpecRow } from './charts';
import { h, type Child } from './dom';
import { mountToggle } from './shell';

export interface PlateDef {
  /** File under `renders/`. */
  file: string;
  /** Alternative for narrow screens. */
  phoneFile?: string;
  caption: string;
  alt: string;
  /** Sub-rectangle of the image to show, as fractions of its width and height. */
  crop?: { x: number; y: number; w: number; h: number };
  /** Fill the whole stage edge to edge instead of sitting in a frame. */
  bleed?: boolean;
}

export interface SectionDef {
  id: string;
  /** Name shown in the top bar and on the rail. */
  name: string;
  plate: PlateDef | 'sheet';
  build: (app: App) => Child;
}

const FOOTER = 'Concept design. Fictional system. Design and build: Paul Nercessian.';

const p = (...text: Child[]) => h('p', null, ...text);
const words = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen'];
/** Small counts read better as words in a sentence; they still come from the data. */
const word = (n: number) => words[n] ?? String(n);
const Word = (n: number) => {
  const w = word(n);
  return w.charAt(0).toUpperCase() + w.slice(1);
};

function joint(name: string): Joint | undefined {
  return spec.joints.find((j) => j.name === name);
}
function jointRow(name: string, label?: string): SpecRow {
  const j = joint(name);
  return j ? [label ?? jointLabel(j.name), range(j.range)] : null;
}
function byName(app: App, assembly: string, name: string): Part | undefined {
  return app.catalog.byAssembly.get(assembly)?.parts.find((x) => x.name === name);
}
function assemblyRow(app: App, id: string, label?: string): SpecRow {
  const a = app.catalog.byAssembly.get(id);
  return a ? [label ?? `${a.name}, ${a.parts.length} parts`, kg(a.mass_kg)] : null;
}
function note(title: string) {
  const i = spec.design_notes.findIndex((n) => n.title.startsWith(title));
  return i >= 0 ? designNote(spec.design_notes[i]!, i) : null;
}
function panel(def: { id: string; title: string }, ...body: Child[]): HTMLElement {
  return h(
    'article.panel',
    null,
    h('header.panel-head', null, h('span.panel-no.data', null, def.id), h('h2', null, def.title)),
    ...body,
  );
}

const head = spec.landmarks;
const knee = spec.design_notes.find((n) => n.title.startsWith('Static knee'))?.inputs as
  | { shin_length_mm: number; crank_radius_mm: number; actuator_stroke_mm: number; moment_arm_by_flexion_mm: Record<string, number> }
  | undefined;
const endurance = spec.design_notes.find((n) => n.title.startsWith('Endurance'));

export const SECTIONS: SectionDef[] = [
  // ── 00 ────────────────────────────────────────────────────────────────────
  {
    id: '00',
    name: 'Title',
    plate: {
      file: 'social_card.jpg',
      phoneFile: 'front_deployed.jpg',
      caption: 'Front three-quarter, mount deployed',
      alt: 'The robot from the front left: black armour over exposed actuators, a hard cap worn brim to the rear, the cannon level over the right shoulder.',
      bleed: true,
    },
    build: (app) => {
      const [type, mark] = spec.designation.split(' ');
      return h(
        'div.cover',
        null,
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
        h('p.cover-foot.cap', null, 'Scroll to read the dossier'),
      );
    },
  },

  // ── 01 ────────────────────────────────────────────────────────────────────
  {
    id: '01',
    name: 'Overview',
    plate: {
      file: 'rear_stowed.jpg',
      caption: 'Rear three-quarter, mount stowed',
      alt: 'The robot from the rear right with the barrel standing vertical behind the right shoulder, above the backpack radiators and blowers.',
    },
    build: (app) =>
      panel(
        { id: '01', title: 'Overview' },
        p(
          `RJ-28 is a ${trim1(spec.height_to_cap_crown / 10)} cm autonomous humanoid built to intercept incoming missiles and drones from wherever it is standing. `,
          'It carries one cannon on a swing-arm mount behind the right shoulder: upright for transit, level over the shoulder in use.',
        ),
        p(
          'It is built the way heavy plant is built, and the bulk is components. Three rotary actuators fill each shoulder, the hand drive fills each forearm, and the battery, compute and power distribution fill the chest. ',
          `The model has ${num(app.catalog.parts.length, 0)} named parts in ${word(app.catalog.assemblies.length)} assemblies, each with a function, a material and a mass.`,
        ),
        specTable(
          [
            ['Height to cap crown', mm(spec.height_to_cap_crown)],
            ['Height, mount stowed', mm(spec.envelope.stowed.height)],
            ['Height, mount deployed', mm(spec.envelope.deployed.height)],
            ['Span over shoulder armour', mm(spec.shoulder_armour_span)],
            ['Width over the arms', mm(spec.body.width)],
            ['Depth, body', mm(spec.body.depth)],
            ['Stance width', mm(head.stance_width!)],
            ['Mass, ready', kg(spec.mass.total_kg, 1)],
          ],
          'Principal dimensions',
        ),
        heightLadder('Heights from the floor', [
          { label: 'Cap crown', mm: spec.height_to_cap_crown },
          { label: 'Sensor slit', mm: head.sensor_slit! },
          { label: 'Neck ring', mm: head.neck_ring! },
          { label: 'Shoulder axis', mm: head.shoulder_axis! },
          { label: 'Waist joint', mm: head.waist_joint! },
          { label: 'Hip axis', mm: head.hip_axis! },
          { label: 'Knee axis', mm: head.knee_axis! },
          { label: 'Ankle axis', mm: head.ankle_axis! },
          { label: 'Floor', mm: 0 },
        ]),
        specTable(
          [
            ['Walk', `${num(spec.targets.walk_kmh, 0)} km/h`],
            ['Run', `${num(spec.targets.run_kmh, 0)} km/h`],
            endurance && ['Endurance, mixed duty', `${trim1(endurance.result.endurance_h!)} h`],
            ['Sealing', spec.targets.sealing],
          ],
          'Design targets',
        ),
      ),
  },

  // ── 02 ────────────────────────────────────────────────────────────────────
  {
    id: '02',
    name: 'Head and cap',
    plate: {
      file: 'head_cap.jpg',
      caption: 'Head and cap',
      alt: 'Close view of the head: a raked faceplate with one lit slit, a three-lens cluster on the left cheek and a six-panel hard cap with its brim to the rear.',
    },
    build: (app) => {
      const brim = byName(app, '01', 'Cap Brim');
      const bar = byName(app, '01', 'Rear Sensor Bar');
      return panel(
        { id: '02', title: 'Head and cap' },
        p(
          'The head has no face. A raked plate carries one recessed slit with a stereo camera pair behind dark glass, and a cluster of three lenses on the left cheek: thermal imager, lidar window and spotter camera.',
        ),
        p(
          'The cap is a rigid composite shell bolted to the skull frame and worn brim to the rear. The brim is there for what is under its lip. It stands out over the nape, clear of the collar and the backpack, so the rear sensor bar sees down the back of the machine without the head turning.',
        ),
        p(
          'The neck is a geared yaw ring under a two-axis gimbal. Two short linear actuators drive pitch and roll, and the loom passes through the gimbal with slack for the full range.',
        ),
        specTable(
          [
            ['Sensor slit, height from floor', mm(head.sensor_slit!)],
            ['Neck ring, height from floor', mm(head.neck_ring!)],
            brim && ['Cap brim, bounding size', `${dims(brim.size)} mm`],
            bar && ['Rear sensor bar, bounding size', `${dims(bar.size)} mm`],
            jointRow('neck_yaw'),
            jointRow('neck_pitch'),
            jointRow('neck_roll'),
            assemblyRow(app, '01'),
            assemblyRow(app, '02'),
          ],
          'Head and neck',
        ),
      );
    },
  },

  // ── 03 ────────────────────────────────────────────────────────────────────
  {
    id: '03',
    name: 'Thorax',
    plate: {
      file: 'front_deployed.jpg',
      caption: 'Thorax, armour fitted',
      alt: 'The chest from the front: a keel plate with two set-back pectoral panels, two service hatches and the data plate.',
      crop: { x: 0.24, y: 0.205, w: 0.56, h: 0.27 },
    },
    build: (app) => {
      const pack = byName(app, '03', 'Battery Enclosure');
      const e = endurance?.inputs as { pack_mass_kg: number; usable_fraction: number } | undefined;
      return panel(
        { id: '03', title: 'Thorax' },
        p(
          `The chest is a machined aluminium tub under armour panels on carriers. Its depth is set by the battery: one liquid-cooled enclosure of ${num(spec.targets.pack_kwh, 1)} kWh at ${trim1(spec.targets.pack_voltage)} V nominal, stepped to pass the waist beam and the shoulder pitch actuators.`,
        ),
        p(
          'Two compute modules sit on cold plates above the pack, with power distribution beside them. One coolant loop serves the pack, the compute and the actuators, and gives up its heat through two radiator cores and two blowers in the backpack.',
        ),
        specTable(
          [
            ['Pack energy', `${num(spec.targets.pack_kwh, 1)} kWh`],
            ['Pack voltage, nominal', `${trim1(spec.targets.pack_voltage)} V`],
            e && ['Pack mass', kg(e.pack_mass_kg, 1)],
            pack && ['Battery enclosure, bounding size', `${dims(pack.size)} mm`],
            ['Average draw, mixed duty', `${num(spec.targets.average_draw_kw, 1)} kW`],
            endurance && ['Endurance to empty', `${num(endurance.result.endurance_h!, 2)} h`],
            endurance && ['Endurance to reserve', `${num(endurance.result.endurance_to_reserve_h!, 2)} h`],
            endurance && ['Specific energy, pack level', `${num(endurance.result.pack_wh_per_kg!, 0)} Wh/kg`],
            assemblyRow(app, '03'),
            assemblyRow(app, '06'),
          ],
          'Power and cooling',
        ),
        note('Endurance'),
      );
    },
  },

  // ── 04 ────────────────────────────────────────────────────────────────────
  {
    id: '04',
    name: 'Arms and hands',
    plate: {
      file: 'front_deployed.jpg',
      caption: 'Left arm and hand',
      alt: 'The left arm from the front: a three-plate pauldron marked RJ-28 over the shoulder actuators, a round elbow joint, a thick forearm and a four-digit hand.',
      crop: { x: 0.5, y: 0.2, w: 0.36, h: 0.5 },
    },
    build: (app) => {
      const left = app.catalog.byAssembly.get('07');
      const right = app.catalog.byAssembly.get('08');
      return panel(
        { id: '04', title: 'Arms and hands' },
        p(
          `Each arm has ${word(spec.dof.arms! / 2)} axes. Shoulder pitch sits in the flank of the thorax, roll on the joint centre and yaw at the top of the upper arm, which is why the shoulder is the largest mass on the figure. The elbow is a cycloidal joint; forearm roll and a two-axis wrist follow.`,
        ),
        p(
          `The forearm is thick because the hand is driven from it: ${word(spec.dof.hands! / 2)} motors with screw drives and linkages, one for each hand axis. The hand has a thumb with opposition and flexion, three fingers with one driven flexion each and coupled knuckles, and a ganged splay.`,
        ),
        left &&
          right &&
          p(
            `The arms are not a mirrored pair. The left pauldron is larger and carries the unit number; the right is cut back at the rear to clear the mount. The left arm weighs ${kg(left.mass_kg)}, the right ${kg(right.mass_kg)}.`,
          ),
        specTable(
          [
            jointRow('shoulder_pitch_L'),
            jointRow('shoulder_roll_L'),
            jointRow('shoulder_yaw_L'),
            jointRow('elbow_pitch_L'),
            jointRow('forearm_roll_L'),
            jointRow('wrist_pitch_L'),
            jointRow('wrist_yaw_L'),
          ],
          'Arm, range of motion',
        ),
        specTable(
          [
            jointRow('thumb_opposition_L'),
            jointRow('thumb_flexion_L'),
            jointRow('finger1_flexion_L', 'Finger flexion, each of three'),
            jointRow('finger_splay_L'),
            assemblyRow(app, '09', 'Hand, each'),
          ],
          'Hand',
        ),
      );
    },
  },

  // ── 05 ────────────────────────────────────────────────────────────────────
  {
    id: '05',
    name: 'Legs',
    plate: {
      file: 'knee.jpg',
      caption: 'Knee joint',
      alt: 'Close view of a knee: a round bearing housing on the joint axis between the thigh and shin armour, with actuator rods and bellows behind.',
    },
    build: (app) =>
      panel(
        { id: '05', title: 'Legs' },
        p(
          `Each leg has ${word(spec.dof.legs! / 2)} axes. Three rotary actuators at the hip give yaw, roll and pitch, and the pitch drum forms the top of the thigh.`,
        ),
        p(
          knee
            ? `The knee is a crank joint. Two planetary roller-screw actuators behind the thigh act on a ${trim1(knee.crank_radius_mm)} mm crank, while round bearing housings stay on the knee axis. `
            : 'The knee is a crank joint driven by two planetary roller-screw actuators behind the thigh. ',
          'The ankle is a universal joint with two parallel actuators at the rear of the shin: driven together they pitch the foot, driven apart they roll it.',
        ),
        specTable(
          [
            ['Hip axis, height from floor', mm(head.hip_axis!)],
            ['Knee axis, height from floor', mm(head.knee_axis!)],
            ['Ankle axis, height from floor', mm(head.ankle_axis!)],
            ['Hip axes apart', mm(head.hip_axis_span!)],
            knee && ['Shin length, knee to ankle', mm(knee.shin_length_mm)],
            jointRow('hip_pitch_L'),
            jointRow('knee_pitch_L'),
            knee && ['Knee actuator stroke', mm(knee.actuator_stroke_mm)],
            jointRow('ankle_pitch_L'),
            jointRow('ankle_roll_L'),
            assemblyRow(app, '11', 'Leg, left'),
            assemblyRow(app, '12', 'Leg, right'),
            assemblyRow(app, '13', 'Foot, each'),
          ],
          'Leg',
        ),
        knee && momentArmPlot('Knee actuator moment arm', knee.moment_arm_by_flexion_mm),
        note('Static knee'),
      ),
  },

  // ── 06 ────────────────────────────────────────────────────────────────────
  {
    id: '06',
    name: 'Interceptor cannon',
    plate: {
      file: 'mount.jpg',
      caption: 'Mount: pivot housing, swing arm and breech',
      alt: 'Close view of the mount from the right rear: the round pivot housing on its yoke, the swing arm plate bolted to the breech, and the gear sector below.',
    },
    build: (app) => {
      const m = spec.mount;
      const elevating = app.catalog.parts.filter((x) => x.mount_group === 'elev');
      const traversing = app.catalog.parts.filter((x) => x.mount_group !== '');
      const sum = (list: Part[]) => list.reduce((t, x) => t + x.mass_kg, 0);
      const st = spec.envelope.stowed;
      const dp = spec.envelope.deployed;
      return panel(
        { id: '06', title: 'Interceptor cannon' },
        p(
          `One axis does two jobs. The trunnion swings the cannon between stowed and deployed, and it is the elevation axis in use. At ${deg(m.elevation[1])} the barrel stands vertical behind the right shoulder with the breech in the travel lock. At ${deg(0)} it lies level above the shoulder armour, pointing where the robot faces.`,
        ),
        p(
          `The cannon rides above the trunnion on a swing arm, ${trim1(m.bore_rise)} mm from axis to bore. That puts the stowed barrel behind the shoulder and not beside the head. A slewing ring under the yoke gives traverse once deployed, and the barrel runs in a cradle on two guide rods with the recoil cylinder between them.`,
        ),
        h('div.inline-control', null, h('span.cap', null, 'Mount position'), mountToggle(app)),
        specTable(
          [
            ['Elevation', range(m.elevation)],
            ['Traverse', range([-m.traverse, m.traverse])],
            jointRow('tracker_tilt', 'Tracking head tilt'),
            ['Barrel', `Ø${trim1(m.barrel_od)} × ${trim1(m.barrel_length)} mm`],
            ['Trunnion axis, height from floor', mm(m.trunnion[2])],
            ['Bore above trunnion', mm(m.bore_rise)],
            ['Elevating mass', kg(sum(elevating))],
            ['Traversing mass', kg(sum(traversing))],
            assemblyRow(app, '15'),
          ],
          'Mount',
        ),
        h(
          'section.block',
          null,
          h('h3.cap', null, 'Envelope by mount position'),
          h(
            'table.grid',
            null,
            h('thead', null, h('tr', null, h('th'), h('th', { scope: 'col' }, 'Stowed'), h('th', { scope: 'col' }, 'Deployed'))),
            h(
              'tbody',
              null,
              h('tr', null, h('th', { scope: 'row' }, 'Overall height'), h('td.data', null, mm(st.height)), h('td.data', null, mm(dp.height))),
              h('tr', null, h('th', { scope: 'row' }, 'Overall depth'), h('td.data', null, mm(st.depth)), h('td.data', null, mm(dp.depth))),
              h('tr', null, h('th', { scope: 'row' }, 'Forward of origin'), h('td.data', null, mm(-st.min[1])), h('td.data', null, mm(-dp.min[1]))),
              h('tr', null, h('th', { scope: 'row' }, 'Rear of origin'), h('td.data', null, mm(st.max[1])), h('td.data', null, mm(dp.max[1]))),
            ),
          ),
        ),
      );
    },
  },

  // ── 07 ────────────────────────────────────────────────────────────────────
  {
    id: '07',
    name: 'Armour and materials',
    plate: {
      file: 'exploded.jpg',
      caption: 'Exploded by assembly',
      alt: 'The whole robot exploded: armour panels stand off their carriers, actuators and frames hang in the gaps, and the mount is laid out to one side.',
    },
    build: (app) => {
      const cls = spec.mass.by_class;
      const label = (k: string) => k.charAt(0).toUpperCase() + k.slice(1);
      // Two entries in the data are render helpers, not materials: they are named by their own key.
      const materials = app.catalog.materials.filter((m) => m.name !== m.key);
      return panel(
        { id: '07', title: 'Armour and materials' },
        p(
          `The robot is black, but it is not one black. ${Word(materials.length)} materials separate the parts by roughness, sheen and texture: matte armour composite, satin anodised aluminium, dark titanium at the joints, polished steel on rods and bearing races.`,
        ),
        p(
          `Armour is moulded composite panel on machined carriers, with even gaps that show the structure behind. It accounts for ${kg(cls.armour!, 1)} of the ${kg(spec.mass.total_kg, 1)}. Structure and actuators carry most of the rest.`,
        ),
        barChart(
          'Mass by class',
          Object.entries(cls)
            .map(([k, v]) => ({ label: label(k), value: v }))
            .sort((a, b) => b.value - a.value),
          { unit: 'kg', digits: 2, valueHead: 'Mass' },
        ),
        barChart(
          'Mass by assembly',
          spec.mass.by_assembly.map((a) => ({ label: `${a.assembly} ${a.name}`, value: a.mass_kg, extra: num(a.parts, 0) })),
          { unit: 'kg', digits: 2, extraHead: 'Parts', valueHead: 'Mass' },
        ),
        h(
          'section.block',
          null,
          h('h3.cap', null, 'Materials'),
          h(
            'table.grid',
            null,
            h('thead', null, h('tr', null, h('th', { scope: 'col' }, 'Material'), h('th', { scope: 'col' }, 'Parts'), h('th', { scope: 'col' }, 'Mass'))),
            h(
              'tbody',
              null,
              materials.map((m) =>
                  h('tr', null, h('th', { scope: 'row' }, m.name), h('td.data', null, num(m.parts, 0)), h('td.data', null, kg(m.mass_kg))),
                ),
            ),
          ),
        ),
        note('Mass roll-up'),
      );
    },
  },

  // ── 08 ────────────────────────────────────────────────────────────────────
  {
    id: '08',
    name: 'Drawings',
    plate: 'sheet',
    build: (app) => {
      const set = app.sheets;
      const n = set?.sheets.length ?? 0;
      return panel(
        { id: '08', title: 'Drawings' },
        n
          ? p(
              `${Word(n)} ${n === 1 ? 'sheet is' : 'sheets are'} generated from the same model that this page shows. The line work is vector, so it stays sharp at any zoom, and the dimensions on the sheets are measured from the mesh and not typed.`,
            )
          : p('The drawing set is not part of this build.'),
        n ? p('The sheets are live. Pick a part or a balloon to select it, then show it in the model.') : null,
        set?.placeholder
          ? h('p.advice', null, 'Stand-in sheets are shown until the drawing set is exported. They are drawn from part bounding boxes only.')
          : null,
        n
          ? h(
              'ol.sheet-list',
              null,
              set!.sheets.map((sh) =>
                h(
                  'li',
                  null,
                  h(
                    'button.sheet-card',
                    { type: 'button', onclick: () => openSheet(app, sh.id) },
                    h('span.sheet-thumb', null, h('img', { alt: '', decoding: 'async', dataset: { src: sh.url }, width: sh.width || null, height: sh.height || null })),
                    h(
                      'span.sheet-meta',
                      null,
                      h('span.data', null, sh.number),
                      h('span', null, sh.title),
                      sh.scale ? h('span.data', null, sh.scale) : null,
                    ),
                  ),
                ),
              ),
            )
          : null,
        h(
          'div.actions',
          null,
          n ? h('button.btn', { type: 'button', onclick: () => openSheet(app) }, 'Open the sheet viewer') : null,
          set?.pdfUrl ? h('a.btn', { href: set.pdfUrl, download: '' }, 'Download the set, PDF') : null,
          h('button.btn', { type: 'button', onclick: () => setMode(app, 'blueprint') }, 'Blueprint mode'),
        ),
      );
    },
  },

  // ── 09 ────────────────────────────────────────────────────────────────────
  {
    id: '09',
    name: 'Inspect',
    plate: {
      file: 'front_deployed.jpg',
      caption: 'Front three-quarter, mount deployed',
      alt: 'The whole robot from the front left, standing, with the cannon level over the right shoulder.',
    },
    build: (app) =>
      h(
        'div',
        null,
        panel(
          { id: '09', title: 'Inspect' },
          p(
            `The tour ends here. The inspector is the same model with the controls unlocked: pick any of the ${num(app.catalog.parts.length, 0)} parts to read its function, material, mass and size, hide or isolate it, and find it on a drawing.`,
          ),
          p('The exploded view separates the assemblies and then the parts within them. Blueprint mode shows the model as line work with its overall dimensions.'),
          h(
            'div.actions',
            null,
            h('button.btn', { type: 'button', onclick: () => setMode(app, 'inspect') }, 'Open the inspector'),
            h('button.btn', { type: 'button', onclick: () => setMode(app, 'explode') }, 'Exploded view'),
            h('button.btn', { type: 'button', onclick: () => setMode(app, 'blueprint') }, 'Blueprint'),
          ),
          h(
            'section.block',
            null,
            h('h3.cap', null, 'Keyboard'),
            h(
              'dl.keys',
              null,
              KEY_ROWS.slice(0, 7).map((r) => h('div', null, h('dt', null, r.keys.map((k) => h('kbd', null, k))), h('dd', null, r.does))),
            ),
          ),
        ),
        h('footer.colophon', null, h('p', null, FOOTER)),
      ),
  },
];

export const SECTION_NAMES: string[] = SECTIONS.map((x) => x.name);
