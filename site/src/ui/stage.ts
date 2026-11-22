import type { App } from '../app/context';
import { publicUrl, spec } from '../data';
import { num, pad2 } from '../data/format';
import { imageSize } from '../loader/assets';
import { BoxModel, VIEW_TITLE } from './boxmodel';
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
 * The static edition of the stage, for a browser with no WebGL 2 or a model
 * that did not load: hero renders behind the dossier, and a drawing of the
 * part bounding boxes on the model tab so parts can still be found and picked.
 */
export function buildStaticStage(app: App): HTMLElement {
  const { store } = app;
  const exploded = SECTIONS.find((x) => x.plate !== 'sheet' && x.plate.file === 'exploded.jpg')!.plate as PlateDef;
  const plates: HTMLElement[] = SECTIONS.map((def, i) => {
    if (def.plate === 'sheet') return sheetPlate(app, i) ?? plateFigure(exploded, i);
    return plateFigure(def.plate, i);
  });
  const plateLayer = h('div.stage-plates', null, plates);

  const front = new BoxModel(app, 'front', { dimensions: false });
  const side = new BoxModel(app, 'side', { dimensions: false });
  const caption = (title: string, note: string) => h('figcaption', null, h('span.cap', null, title), h('span', null, note));
  const boxLayer = h(
    'div.stage-boxes',
    null,
    h('figure.boxfig', null, front.el, caption(VIEW_TITLE.front, 'Part bounding boxes from the measured data')),
    h('figure.boxfig', null, side.el, caption(VIEW_TITLE.side, 'Pick a box to select the part')),
  );

  const root = h('div.static-stage', null, plateLayer, boxLayer);
  store.watch(
    (s) => [s.tab, s.section] as const,
    ([tab, section]) => {
      plateLayer.hidden = tab !== 'dossier';
      boxLayer.hidden = tab !== 'model';
      if (tab === 'dossier') {
        plates.forEach((fig, i) => {
          if (Math.abs(i - section) <= 1) arm(fig);
          fig.classList.toggle('on', i === section);
        });
      }
      app.camera.set(null); // a render or a flat drawing has no camera to read
    },
  );
  return root;
}
