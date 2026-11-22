import { isVisible, isolate, select, setHidden, showAll, type App } from '../app/context';
import { num } from '../data/format';
import type { Assembly, Part } from '../data/types';
import { clearNode, h, isPhone } from './dom';

const ROW = 30;
const OVERSCAN = 8;

type Row =
  | { kind: 'assembly'; key: string; a: Assembly; open: boolean; shown: number }
  | { kind: 'part'; key: string; p: Part };

/**
 * Assembly tree: seventeen assemblies, then their parts. Only the rows in view
 * exist in the DOM, so nine hundred parts cost the same as thirty.
 */
export function buildTree(app: App): HTMLElement {
  const { store, catalog } = app;
  const expanded = new Set<string>();
  let query = '';
  let rows: Row[] = [];
  let matches: Part[] = catalog.parts;
  let cursor: string | null = null;
  let windowStart = -1;
  let windowEnd = -1;

  const input = h('input.tree-search', {
    id: 'tree-q',
    type: 'search',
    placeholder: 'Search name, number or function',
    autocomplete: 'off',
    spellcheck: 'false',
    'aria-controls': 'tree-list',
  });
  const status = h('span.tree-count.data', { 'aria-live': 'polite' });
  const reset = h('button.tree-reset.cap', { type: 'button', onclick: () => showAll(app) }, 'Show all');
  const spacer = h('div.tree-spacer');
  const empty = h('p.tree-empty', { hidden: true });
  const list = h(
    'div.tree-scroll',
    { id: 'tree-list', role: 'tree', tabindex: '0', 'aria-label': 'Assemblies and parts' },
    spacer,
    empty,
  );
  // What the search looks through: number, name, function and material.
  const haystack = new Map<Part, string>();
  for (const p of catalog.parts) haystack.set(p, `${p.number}\n${p.name}\n${p.function}\n${p.material}`.toLowerCase());
  const closeDrawer = h('button.btn.tree-close', { type: 'button', onclick: () => store.set({ drawer: false }) }, 'Close');
  const panel = h(
    'aside.tree-panel',
    { 'aria-label': 'Assembly tree' },
    h(
      'div.tree-head',
      null,
      h('div.tree-title', null, h('h2.cap', null, 'Assemblies'), closeDrawer),
      h('label.sr-only', { for: 'tree-q' }, 'Search parts by name, number, function or material'),
      input,
      h('div.tree-status', null, status, reset),
    ),
    list,
  );

  const keyOf = (p: Part) => p.number;
  const asmKey = (id: string) => `a:${id}`;
  const domId = (key: string) => `tr-${key.replace(':', '-')}`;

  function flatten(): void {
    const q = query.trim().toLowerCase();
    rows = [];
    matches = [];
    for (const a of catalog.assemblies) {
      const parts = q ? a.parts.filter((p) => haystack.get(p)!.includes(q)) : a.parts;
      if (q && parts.length === 0) continue;
      matches.push(...parts);
      const open = q ? true : expanded.has(a.id);
      rows.push({ kind: 'assembly', key: asmKey(a.id), a, open, shown: parts.length });
      if (open) for (const p of parts) rows.push({ kind: 'part', key: keyOf(p), p });
    }
    spacer.style.height = `${rows.length * ROW}px`;
    empty.hidden = rows.length > 0;
    empty.textContent = rows.length ? '' : `No part matches “${query.trim()}”.`;
    const { hidden, isolated } = store.get();
    const total = catalog.parts.length;
    status.textContent = q
      ? `${num(matches.length, 0)} of ${num(total, 0)} parts`
      : `${num(total, 0)} parts in ${catalog.assemblies.length} assemblies`;
    const off = isolated ? catalog.parts.filter((p) => !isVisible(app, p)).length : hidden.size;
    reset.hidden = off === 0;
    reset.textContent = `Show all (${num(off, 0)} hidden)`;
    windowStart = -1;
    draw();
  }

  function rowEl(row: Row, index: number): HTMLElement {
    const { selected, hidden, isolated } = store.get();
    const common = {
      id: domId(row.key),
      role: 'treeitem',
      dataset: { key: row.key },
      style: { transform: `translateY(${index * ROW}px)` },
    };
    if (row.kind === 'assembly') {
      const visibleParts = row.a.parts.filter((p) => isVisible(app, p)).length;
      const state = visibleParts === 0 ? 'off' : visibleParts === row.a.parts.length ? 'on' : 'mixed';
      const isolated_ = isolated?.kind === 'assembly' && isolated.id === row.a.id;
      return h(
        'div.tree-row.tree-asm',
        { ...common, 'aria-level': '1', 'aria-expanded': String(row.open), class: [row.key === cursor && 'cursor', state === 'off' && 'off'].filter(Boolean).join(' ') },
        h('span.twist', { 'aria-hidden': 'true' }, row.open ? '−' : '+'),
        h('span.tree-no.data', null, row.a.id),
        h('span.tree-name', null, row.a.name),
        h('span.tree-n.data', null, query ? `${row.shown}/${row.a.parts.length}` : String(row.a.parts.length)),
        h(
          'button.tree-iso',
          { type: 'button', tabindex: '-1', 'aria-pressed': String(isolated_), 'aria-label': `Isolate ${row.a.name}`, title: 'Isolate this assembly', dataset: { act: 'iso' } },
          'Iso',
        ),
        h('button.eye', {
          type: 'button',
          tabindex: '-1',
          dataset: { act: 'vis', state },
          'aria-pressed': String(state !== 'off'),
          'aria-label': `${state === 'off' ? 'Show' : 'Hide'} ${row.a.name}`,
          title: state === 'off' ? 'Show' : 'Hide',
        }),
      );
    }
    const p = row.p;
    const on = isVisible(app, p);
    return h(
      'div.tree-row.tree-part',
      {
        ...common,
        'aria-level': '2',
        'aria-selected': String(p.number === selected),
        class: [row.key === cursor && 'cursor', !on && 'off'].filter(Boolean).join(' '),
      },
      h('span.tree-no.data', null, p.number),
      h('span.tree-name', null, p.name),
      h('button.eye', {
        type: 'button',
        tabindex: '-1',
        dataset: { act: 'vis', state: hidden.has(p.number) ? 'off' : 'on' },
        'aria-pressed': String(!hidden.has(p.number)),
        'aria-label': `${hidden.has(p.number) ? 'Show' : 'Hide'} ${p.number} ${p.name}`,
        title: hidden.has(p.number) ? 'Show' : 'Hide',
      }),
    );
  }

  function draw(force = true): void {
    const start = Math.max(0, Math.floor(list.scrollTop / ROW) - OVERSCAN);
    const end = Math.min(rows.length, Math.ceil((list.scrollTop + (list.clientHeight || 600)) / ROW) + OVERSCAN);
    if (!force && start === windowStart && end === windowEnd) return;
    windowStart = start;
    windowEnd = end;
    clearNode(spacer);
    const frag = document.createDocumentFragment();
    for (let i = start; i < end; i++) frag.appendChild(rowEl(rows[i]!, i));
    spacer.appendChild(frag);
    const active = cursor ?? store.get().selected;
    if (active && rows.some((r) => r.key === active)) list.setAttribute('aria-activedescendant', domId(active));
    else list.removeAttribute('aria-activedescendant');
  }

  function reveal(key: string): void {
    const i = rows.findIndex((r) => r.key === key);
    if (i < 0) return;
    const top = i * ROW;
    const view = list.clientHeight || 600;
    if (top < list.scrollTop + ROW) list.scrollTop = Math.max(0, top - ROW * 2);
    else if (top + ROW > list.scrollTop + view - ROW) list.scrollTop = top - view + ROW * 3;
  }

  function moveTo(row: Row | undefined): void {
    if (!row) return;
    cursor = row.key;
    if (row.kind === 'part') select(app, row.p.number);
    reveal(row.key);
    draw();
  }

  function toggle(a: Assembly, open?: boolean): void {
    const next = open ?? !expanded.has(a.id);
    if (next) expanded.add(a.id);
    else expanded.delete(a.id);
    flatten();
  }

  /** Step through parts in tree order, opening assemblies as needed. */
  function step(delta: number): void {
    if (matches.length === 0) return;
    const { selected } = store.get();
    const at = selected ? matches.findIndex((p) => p.number === selected) : -1;
    const next = matches[at < 0 ? (delta > 0 ? 0 : matches.length - 1) : Math.min(matches.length - 1, Math.max(0, at + delta))]!;
    cursor = next.number;
    select(app, next.number);
  }

  // ── Events ────────────────────────────────────────────────────────────────
  list.addEventListener('scroll', () => draw(false), { passive: true });
  new ResizeObserver(() => draw(false)).observe(list);

  list.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    const rowNode = target.closest<HTMLElement>('.tree-row');
    const row = rowNode && rows.find((r) => r.key === rowNode.dataset.key);
    if (!row) return;
    const act = target.closest<HTMLElement>('[data-act]')?.dataset.act;
    if (act === 'vis') {
      if (row.kind === 'assembly') {
        const anyVisible = row.a.parts.some((p) => !store.get().hidden.has(p.number));
        setHidden(app, row.a.parts.map((p) => p.number), anyVisible);
      } else {
        setHidden(app, [row.p.number], !store.get().hidden.has(row.p.number));
      }
      return;
    }
    if (act === 'iso' && row.kind === 'assembly') {
      isolate(app, { kind: 'assembly', id: row.a.id });
      return;
    }
    cursor = row.key;
    if (row.kind === 'assembly') toggle(row.a);
    else {
      select(app, row.p.number);
      if (store.get().drawer) store.set({ drawer: false });
    }
  });
  list.addEventListener('dblclick', (e) => {
    if ((e.target as HTMLElement).closest('.tree-part')) app.commands.emit('frame');
  });

  list.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const active = cursor ?? store.get().selected;
    const i = active ? rows.findIndex((r) => r.key === active) : -1;
    const row = rows[i];
    let handled = true;
    switch (e.key) {
      case 'ArrowDown':
        moveTo(rows[Math.min(rows.length - 1, i + 1)]);
        break;
      case 'ArrowUp':
        moveTo(rows[Math.max(0, i - 1)]);
        break;
      case 'Home':
        moveTo(rows[0]);
        break;
      case 'End':
        moveTo(rows[rows.length - 1]);
        break;
      case 'ArrowRight':
        if (row?.kind === 'assembly') {
          if (!row.open) toggle(row.a, true);
          else moveTo(rows[i + 1]);
        }
        break;
      case 'ArrowLeft':
        if (row?.kind === 'assembly') toggle(row.a, false);
        else if (row?.kind === 'part') moveTo(rows.find((r) => r.key === asmKey(row.p.assembly)));
        break;
      case 'Enter':
      case ' ':
        if (row?.kind === 'assembly') toggle(row.a);
        else if (row?.kind === 'part') app.commands.emit('frame');
        break;
      default:
        handled = false;
    }
    if (handled) {
      e.preventDefault();
      e.stopPropagation();
    }
  });

  input.addEventListener('input', () => {
    query = input.value;
    list.scrollTop = 0;
    flatten();
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && input.value) {
      input.value = '';
      query = '';
      flatten();
      e.stopPropagation();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      list.focus();
      if (!cursor && rows[0]) moveTo(rows[0]);
    }
  });

  app.commands.on('step', step);
  app.commands.on('search', () => {
    if (isPhone() && !store.get().drawer) store.set({ drawer: true });
    requestAnimationFrame(() => input.focus());
  });

  store.watch(
    (s) => s.selected,
    (selected) => {
      if (selected) {
        const part = catalog.byNumber.get(selected);
        if (part && !expanded.has(part.assembly)) expanded.add(part.assembly);
        cursor = selected;
        flatten();
        reveal(selected);
        draw();
      } else {
        draw();
      }
    },
  );
  store.watch(
    (s) => [s.hidden, s.isolated] as const,
    () => flatten(),
  );
  store.watch(
    (s) => [s.mode !== 'tour', s.drawer] as const,
    () => requestAnimationFrame(() => draw()),
  );

  flatten();
  return panel;
}
