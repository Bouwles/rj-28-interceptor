import {
  clear,
  cycleMode,
  setHidden,
  setMode,
  showInDrawing,
  toggleMeasure,
  toggleMount,
  toggleXray,
  type App,
} from './context';

export interface KeyRow {
  keys: string[];
  does: string;
}

/** Shown in the help overlay. Keep in step with the handler below. */
export const KEY_ROWS: KeyRow[] = [
  { keys: ['↑', '↓'], does: 'Step through parts in the tree' },
  { keys: ['F'], does: 'Frame the selection' },
  { keys: ['X'], does: 'X-ray armour' },
  { keys: ['E'], does: 'Exploded view' },
  { keys: ['B'], does: 'Blueprint' },
  { keys: ['M'], does: 'Mount: stowed or deployed' },
  { keys: ['T'], does: 'Tour' },
  { keys: ['I'], does: 'Inspector' },
  { keys: ['R'], does: 'Measure' },
  { keys: ['H'], does: 'Hide the selected part' },
  { keys: ['D'], does: 'Show the selected part in the drawings' },
  { keys: ['/'], does: 'Search parts' },
  { keys: ['Esc'], does: 'Close, then clear the selection' },
  { keys: ['?'], does: 'This list' },
];

function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
}

export function bindKeys(app: App): void {
  window.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const s = app.store.get();
    if (s.presentation === 'loading') return;

    if (e.key === 'Escape') {
      if (typing(e.target)) (e.target as HTMLElement).blur();
      else clear(app);
      return;
    }
    if (typing(e.target)) return;
    // The sheet viewer and the help overlay take the keyboard while open.
    if (s.help) {
      if (e.key === '?') app.store.set({ help: false });
      return;
    }
    if (s.sheet) return;

    const inTour = s.mode === 'tour';
    switch (e.key.length === 1 ? e.key.toLowerCase() : e.key) {
      case 'ArrowDown':
      case 'ArrowUp':
        if (inTour) return;
        e.preventDefault();
        app.commands.emit('step', e.key === 'ArrowDown' ? 1 : -1);
        break;
      case 'f':
        if (!inTour) app.commands.emit('frame');
        break;
      case 'x':
        toggleXray(app);
        break;
      case 'e':
        cycleMode(app, 'explode');
        break;
      case 'b':
        cycleMode(app, 'blueprint');
        break;
      case 'm':
        toggleMount(app);
        break;
      case 't':
        setMode(app, 'tour');
        break;
      case 'i':
        setMode(app, 'inspect');
        break;
      case 'r':
        if (!inTour) toggleMeasure(app);
        break;
      case 'h':
        if (!inTour && s.selected) setHidden(app, [s.selected], !s.hidden.has(s.selected));
        break;
      case 'd': {
        const part = s.selected ? app.catalog.byNumber.get(s.selected) : undefined;
        if (part) showInDrawing(app, part);
        break;
      }
      case '/':
        if (inTour) setMode(app, 'inspect');
        e.preventDefault();
        app.commands.emit('search');
        break;
      case '?':
        app.store.set({ help: true });
        break;
      default:
        return;
    }
  });
}
