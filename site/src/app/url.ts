import { isMode } from './context';
import { VIEWS, type AppState, type AppStore, type BlueprintView } from './store';

// The view lives in the URL fragment so any state can be linked:
//   #mode=inspect&part=RJ28-15-006&mount=deployed&xray=1
//   #mode=explode&explode=75
//   #mode=blueprint&view=side&sheet=RJ28-GA-003&at=RJ28-15-031
//   #s=06
// Defaults are left out, so the plain address is the start of the tour.

export function parseHash(hash: string): Partial<AppState> {
  const q = new URLSearchParams(hash.replace(/^#/, ''));
  const out: Partial<AppState> = {};
  const mode = q.get('mode');
  if (isMode(mode)) out.mode = mode;
  const part = q.get('part');
  if (part) out.selected = part;
  const mount = q.get('mount');
  if (mount === 'deployed' || mount === 'stowed') out.mount = mount;
  const explode = Number(q.get('explode'));
  if (q.has('explode') && Number.isFinite(explode)) out.explode = Math.min(100, Math.max(0, explode)) / 100;
  if (q.get('xray') === '1') out.xray = true;
  if (q.get('hidden') === '1') out.hiddenLines = true;
  const view = q.get('view');
  if (view && (VIEWS as readonly string[]).includes(view)) out.view = view as BlueprintView;
  const sheet = q.get('sheet');
  if (sheet) {
    out.sheet = sheet;
    const at = q.get('at');
    if (at) out.sheetFocus = /^\d\d$/.test(at) ? { assembly: at } : { part: at };
  }
  const iso = q.get('iso');
  if (iso) out.isolated = /^\d\d$/.test(iso) ? { kind: 'assembly', id: iso } : { kind: 'part', id: iso };
  const s = Number(q.get('s'));
  if (q.has('s') && Number.isInteger(s) && s >= 0) out.section = s;
  return out;
}

export function toHash(s: AppState): string {
  const q: [string, string][] = [];
  if (s.mode !== 'tour') q.push(['mode', s.mode]);
  if (s.mode === 'tour' && s.section > 0) q.push(['s', String(s.section).padStart(2, '0')]);
  if (s.selected) q.push(['part', s.selected]);
  if (s.mount !== 'stowed') q.push(['mount', s.mount]);
  if (s.mode === 'explode') q.push(['explode', String(Math.round(s.explode * 100))]);
  if (s.xray) q.push(['xray', '1']);
  if (s.mode === 'blueprint') {
    q.push(['view', s.view]);
    if (s.hiddenLines) q.push(['hidden', '1']);
  }
  if (s.isolated) q.push(['iso', s.isolated.id]);
  if (s.sheet) {
    q.push(['sheet', s.sheet]);
    const at = s.sheetFocus?.part ?? s.sheetFocus?.assembly;
    if (at) q.push(['at', at]);
  }
  return q.length ? '#' + q.map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&') : '';
}

/** Keep the address bar in step with the store, and the store in step with edits to the address. */
export function syncUrl(store: AppStore, onExternal: (patch: Partial<AppState>) => void): void {
  let queued = false;
  let written = location.hash;
  const write = () => {
    queued = false;
    const s = store.get();
    if (s.presentation === 'loading') return;
    const hash = toHash(s);
    if (hash === written) return;
    written = hash;
    history.replaceState(null, '', location.pathname + location.search + hash);
  };
  store.subscribe(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(write);
  });
  window.addEventListener('hashchange', () => {
    if (location.hash === written) return;
    written = location.hash;
    onExternal(parseHash(location.hash));
  });
}
