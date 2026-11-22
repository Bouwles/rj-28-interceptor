import type { App } from '../app/context';
import type { Mode } from '../app/store';
import { publicUrl, spec } from '../data';
import { num, pad2 } from '../data/format';
import { imageSize } from '../loader/assets';
import { BoxModel, GRID_MM, VIEW_TITLE, viewReadout } from './boxmodel';
import { h } from './dom';
import { SECTIONS, type PlateDef } from './tour-content';

/** Text alternative for the canvas: what a reader would see, in a sentence or two. */
export function canvasSummary(partCount: number): string {
  return (
    `Interactive 3D model of ${spec.designation}: a ${num(spec.height_to_cap_crown, 0)} mm tall black humanoid robot with heavy armour over exposed actuators, ` +
    `a hard cap worn brim to the rear, and one cannon on a mount behind the right shoulder that stands vertical when stowed and lies level when deployed. ` +
    `${num(partCount, 0)} parts in ${spec.mass.by_assembly.length} assemblies. The same information is in the text and tables on this page.`
  );
}

function plateFigure(def: PlateDef, index: number): HTMLElement {
  const size = imageSize(`renders/${def.file}`) ?? { width: 4, height: 5 };
  const crop = def.crop ?? { x: 0, y: 0, w: 1, h: 1 };
  const aspect = (size.width * crop.w) / (size.height * crop.h);
  const img = h('img', {
    alt: def.alt,
    decoding: 'async',
    dataset: { src: publicUrl(`renders/${def.file}`) },
    style: def.crop
      ? {
          width: `${100 / crop.w}%`,
          height: `${100 / crop.h}%`,
          left: `${(-crop.x / crop.w) * 100}%`,
          top: `${(-crop.y / crop.h) * 100}%`,
        }
      : null,
  });
  if (def.bleed) {
    const sources = def.phoneFile
      ? h('source', { media: '(max-width: 760px)', dataset: { srcset: publicUrl(`renders/${def.phoneFile}`) } })
      : null;
    return h('figure.plate.plate-bleed', { dataset: { index: String(index) } }, h('picture', null, sources, img));
  }
  return h(
    'figure.plate',
    { dataset: { index: String(index) }, style: { '--a': String(aspect) } },
    h(
      'div.plate-fit',
      null,
      h('div.plate-frame', { class: def.crop ? 'plate-crop' : '' }, img),
      h('figcaption', null, h('span.cap', null, `Plate ${pad2(index)}`), h('span', null, def.caption), h('span.cap.plate-kind', null, 'Offline render')),
    ),
  );
}

function sheetPlate(app: App, index: number): HTMLElement | null {
  const sheet = app.sheets?.sheets[0];
  if (!sheet) return null;
  const aspect = sheet.width && sheet.height ? sheet.width / sheet.height : 420 / 297;
  return h(
    'figure.plate.plate-sheet',
    { dataset: { index: String(index) }, style: { '--a': String(aspect) } },
    h(
      'div.plate-fit',
      null,
      h('div.plate-frame', null, h('img', { alt: `Drawing sheet ${sheet.number}: ${sheet.title}`, decoding: 'async', dataset: { src: sheet.url } })),
      h('figcaption', null, h('span.cap', null, `Sheet ${sheet.number}`), h('span', null, sheet.title), h('span.cap.plate-kind', null, 'Drawing')),
    ),
  );
}

function arm(fig: HTMLElement): void {
  for (const el of fig.querySelectorAll<HTMLElement>('[data-srcset]')) {
    el.setAttribute('srcset', el.dataset.srcset!);
    delete el.dataset.srcset;
  }
  for (const el of fig.querySelectorAll<HTMLImageElement>('img[data-src]')) {
    el.src = el.dataset.src!;
    delete el.dataset.src;
  }
}

/**
 * The static edition of the stage: hero renders for the tour, a box model for
 * the inspector and blueprint modes, the exploded render for the exploded
 * view. It reads the same store the 3D scene would.
 */
export function buildStaticStage(app: App): HTMLElement {
  const { store } = app;

  // Tour plates, one per section.
  const exploded = SECTIONS.find((x) => x.plate !== 'sheet' && x.plate.file === 'exploded.jpg')!.plate as PlateDef;
  const plates: HTMLElement[] = SECTIONS.map((def, i) => {
    if (def.plate === 'sheet') return sheetPlate(app, i) ?? plateFigure(exploded, i);
    return plateFigure(def.plate, i);
  });
  const plateLayer = h('div.stage-plates', null, plates);

  // Exploded view: the render, and a plain statement of what the slider does not do here.
  const explodedIndex = SECTIONS.findIndex((x) => x.plate !== 'sheet' && x.plate.file === exploded.file);
  const explodedFig = plateFigure({ ...exploded, caption: 'Exploded by assembly. The slider drives the 3D model only.' }, explodedIndex);
  const explodeLayer = h('div.stage-plates.stage-explode', null, explodedFig);

  // Inspector: front and side elevations. Blueprint: one dimensioned view.
  const front = new BoxModel(app, 'front', { dimensions: false });
  const side = new BoxModel(app, 'side', { dimensions: false });
  const caption = (title: string) =>
    h('figcaption', null, h('span.cap', null, title), h('span', null, 'Part bounding boxes from the measured data'));
  const inspectLayer = h(
    'div.stage-boxes',
    null,
    h('figure.boxfig', null, front.el, caption(VIEW_TITLE.front)),
    h('figure.boxfig', null, side.el, caption(VIEW_TITLE.side)),
  );
  const print = new BoxModel(app, store.get().view, { dimensions: true });
  const printCap = h('span.cap');
  const printNote = h('span');
  const printLayer = h(
    'div.stage-boxes.stage-print',
    null,
    h('figure.boxfig', null, print.el, h('figcaption', null, printCap, printNote)),
  );

  const root = h('div.static-stage', null, plateLayer, explodeLayer, inspectLayer, printLayer);

  const layers: Record<Mode, HTMLElement> = {
    tour: plateLayer,
    explode: explodeLayer,
    inspect: inspectLayer,
    blueprint: printLayer,
  };

  store.watch(
    (s) => [s.mode, s.section, s.view] as const,
    ([mode, section, view]) => {
      for (const [m, layer] of Object.entries(layers)) layer.hidden = m !== mode;
      if (mode === 'tour') {
        plates.forEach((fig, i) => {
          if (Math.abs(i - section) <= 1) arm(fig);
          fig.classList.toggle('on', i === section);
        });
      } else if (mode === 'explode') {
        arm(explodedFig);
        explodedFig.classList.add('on');
      } else if (mode === 'blueprint') {
        print.setView(view);
        printCap.textContent = VIEW_TITLE[view];
        printNote.textContent =
          view === 'iso'
            ? 'Part bounding boxes, seen from the front right'
            : `Part bounding boxes on a ${GRID_MM} mm grid. Overall dimensions in mm, from the measured envelope.`;
      }
      // A flat view has real angles; a render has no camera to read.
      app.camera.set(mode === 'blueprint' ? viewReadout(view) : null);
    },
  );
  return root;
}
