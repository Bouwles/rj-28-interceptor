import {
  clear,
  dismissIntro,
  resetModel,
  setExplode,
  setHidden,
  setStrip,
  setTab,
  showInDrawing,
  toggleMeasure,
  toggleMount,
  toggleXray,
  type App,
} from './context';
import { TABS } from './store';

export interface KeyRow {
  keys: string[];
  does: string;
}

/** Shown in the help overlay. Keep in step with the handler below. */
export const KEY_ROWS: KeyRow[] = [
  { keys: ['1', '2', '3', '4'], does: 'Model, dossier, blueprints, specification' },
  { keys: ['↑', '↓'], does: 'Step through parts in the tree' },
  { keys: ['F'], does: 'Frame the selection' },
  { keys: ['M'], does: 'Cannon: stow or deploy' },
  { keys: ['[', ']'], does: 'Strip-down: put a layer back, take one off' },
  { keys: ['E'], does: 'Explode: assembled, or assemblies apart' },
  { keys: ['X'], does: 'X-ray armour' },
  { keys: ['R'], does: 'Measure' },
  { keys: ['H'], does: 'Hide the selected part' },
  { keys: ['D'], does: 'Show the selected part in the drawings' },
  { keys: ['0'], does: 'Reset the model and the view' },
  { keys: ['/'], does: 'Search parts' },
  { keys: ['Esc'], does: 'Close, then clear the selection' },
  { keys: ['?'], does: 'This list' },
];

function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target instanceof HTMLInputElement && target.type === 'range') return false;
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
    if (s.help) {
      if (e.key === '?') app.store.set({ help: false });
      return;
    }
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    const tabIndex = ['1', '2', '3', '4'].indexOf(key);
    if (tabIndex >= 0) {
      setTab(app, TABS[tabIndex]!);
      return;
    }
    if (key === '?') {
      app.store.set({ help: true });
      return;
    }
    // The sheet viewer takes the rest of the keyboard on its own tab.
    if (s.tab !== 'model') {
      if (key === 'd' && s.selected) {
        const part = app.catalog.byNumber.get(s.selected);
        if (part) showInDrawing(app, part);
      }
      return;
    }
    // Range sliders use the arrow keys themselves.
    const onSlider = e.target instanceof HTMLInputElement && e.target.type === 'range';

    switch (key) {
      case 'ArrowDown':
      case 'ArrowUp':
        if (onSlider) return;
        e.preventDefault();
        dismissIntro(app);
        app.commands.emit('step', key === 'ArrowDown' ? 1 : -1);
        break;
      case 'f':
        app.commands.emit('frame');
        break;
      case 'x':
        toggleXray(app);
        break;
      case 'e':
        setExplode(app, s.explode > 0 ? 0 : 0.5);
        break;
      case 'm':
        toggleMount(app);
        break;
      case '[':
        setStrip(app, s.strip - 1);
        break;
      case ']':
        setStrip(app, s.strip + 1);
        break;
      case 'r':
        toggleMeasure(app);
        break;
      case 'h':
        if (s.selected) setHidden(app, [s.selected], !s.hidden.has(s.selected));
        break;
      case 'd': {
        const part = s.selected ? app.catalog.byNumber.get(s.selected) : undefined;
        if (part) showInDrawing(app, part);
        break;
      }
      case '0':
        resetModel(app);
        break;
      case '/':
        e.preventDefault();
        dismissIntro(app);
        app.commands.emit('search');
        break;
      default:
        return;
    }
  });
}
