import { isolate, select, setHidden, showInDrawing, type App } from '../app/context';
import { findOnSheets, spec } from '../data';
import { dims, num, partMass } from '../data/format';
import { specTable } from './charts';
import { fill, h } from './dom';

const GROUP_LABEL: Record<string, string> = {
  elev: 'Elevating mass: swings with the trunnion',
  trav: 'Traversing mass: turns with the slewing ring',
};

const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** Side panel for the selected part: what it is, what it is made of, what it weighs. */
export function buildDetail(app: App): HTMLElement {
  const { store, catalog } = app;
  const body = h('div.detail-body');
  const panel = h('aside.detail-panel', { 'aria-label': 'Selected part', hidden: true }, body);

  const render = () => {
    const { selected, hidden, isolated } = store.get();
    const part = selected ? catalog.byNumber.get(selected) : undefined;
    panel.hidden = !part;
    document.body.dataset.selected = part ? 'true' : 'false';
    if (!part) return;
    const assembly = catalog.byAssembly.get(part.assembly);
    const onSheet = findOnSheets(app.sheets, part);
    const isHidden = hidden.has(part.number);
    const partIsolated = isolated?.kind === 'part' && isolated.id === part.number;
    const share = spec.mass.total_kg > 0 ? (part.mass_kg / spec.mass.total_kg) * 100 : 0;

    fill(
      body,
      h(
        'header.detail-head',
        null,
        h('p.detail-no.data', null, part.number),
        h(
          'button.detail-close',
          { type: 'button', onclick: () => select(app, null), 'aria-label': 'Clear the selection' },
          h('span.cap', null, 'Clear'),
          h('kbd', null, 'Esc'),
        ),
        h('h2', null, part.name),
        h('p.detail-asm', null, h('span.data', null, part.assembly), ` ${assembly?.name ?? part.assembly_name}`),
      ),
      h('p.detail-fn', null, part.function),
      specTable([
        ['Material', capital(part.material), true],
        ['Class', capital(part.material_class)],
        ['Mass', partMass(part.mass_kg)],
        share >= 0.1 && ['Share of mass', `${num(share, 1)}%`],
        part.count > 1 && ['Quantity in set', num(part.count, 0)],
        [`${part.count > 1 ? 'Set' : 'Size'}, W × D × H`, `${dims(part.size)} mm`],
        ['Volume', `${num(part.volume_cm3, part.volume_cm3 < 10 ? 2 : 1)} cm³`],
        part.mount_group && ['Moves with', GROUP_LABEL[part.mount_group] ?? part.mount_group, true],
      ]),
      h(
        'div.detail-actions',
        null,
        h(
          'button.btn',
          { type: 'button', 'aria-pressed': String(partIsolated), onclick: () => isolate(app, { kind: 'part', id: part.number }) },
          'Isolate',
        ),
        h(
          'button.btn',
          { type: 'button', 'aria-pressed': String(isHidden), onclick: () => setHidden(app, [part.number], !isHidden) },
          'Hide',
          h('kbd', null, 'H'),
        ),
        h(
          'button.btn',
          {
            type: 'button',
            disabled: !onSheet,
            title: onSheet ? `Sheet ${onSheet.sheet.number}: ${onSheet.sheet.title}` : 'This part is not called out on a sheet',
            onclick: () => showInDrawing(app, part),
          },
          'Show in drawing',
          h('kbd', null, 'D'),
        ),
      ),
      onSheet
        ? h(
            'p.detail-sheet',
            null,
            onSheet.exact ? 'Called out on sheet ' : 'Its assembly is called out on sheet ',
            h('span.data', null, onSheet.sheet.number),
            '.',
          )
        : h('p.detail-sheet', null, 'Not called out on a drawing sheet.'),
    );
  };

  store.watch((s) => [s.selected, s.hidden, s.isolated] as const, render);
  return panel;
}
