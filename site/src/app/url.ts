import { isTab } from './context';
import type { AppState, AppStore } from './store';

// The view lives in the URL fragment so any state can be linked:
//   #part=RJ28-15-006&mount=deployed&trav=-12&strip=2
//   #explode=75&xray=1
//   #tab=blueprints&sheet=ga-003&at=RJ28-15-031
//   #tab=spec
// Defaults are left out, so the plain address is the introduction.

const num = (q: URLSearchParams, key: string): number | null => {
  if (!q.has(key)) return null;
  const v = Number(q.get(key));
  return Number.isFinite(v) ? v : null;
};

export function parseHash(hash: string): Partial<AppState> {
  const q = new URLSearchParams(hash.replace(/^#/, ''));
  const out: Partial<AppState> = {};
  const tab = q.get('tab');
  if (isTab(tab)) out.tab = tab;
  // A link that states anything about the model is a link to the model.
  else if ([...q.keys()].length) out.tab = 'model';
  const part = q.get('part');
  if (part) out.selected = part;
  const mount = q.get('mount');
  if (mount === 'deployed' || mount === 'stowed') out.mount = mount;
  const trav = num(q, 'trav');
  if (trav !== null) out.traverse = trav;
  const elev = num(q, 'elev');
  if (elev !== null) out.elevation = elev;
  const strip = num(q, 'strip');
  if (strip !== null) out.strip = Math.max(0, Math.round(strip));
  const explode = num(q, 'explode');
  if (explode !== null) out.explode = Math.min(100, Math.max(0, explode)) / 100;
  if (q.get('xray') === '1') out.xray = true;
  const sheet = q.get('sheet');
  if (sheet) {
    out.sheet = sheet;
    const at = q.get('at');
    if (at) out.sheetFocus = /^\d\d$/.test(at) ? { assembly: at } : { part: at };
  }
  const iso = q.get('iso');
  if (iso) out.isolated = /^\d\d$/.test(iso) ? { kind: 'assembly', id: iso } : { kind: 'part', id: iso };
  return out;
}

export function toHash(s: AppState): string {
  const q: [string, string][] = [];
  if (s.tab !== 'intro') q.push(['tab', s.tab]);
  if (s.selected) q.push(['part', s.selected]);
  if (s.mount !== 'stowed') {
    q.push(['mount', s.mount]);
    if (s.traverse !== 0) q.push(['trav', String(Math.round(s.traverse * 10) / 10)]);
    if (s.elevation !== 0) q.push(['elev', String(Math.round(s.elevation * 10) / 10)]);
  }
  if (s.strip > 0) q.push(['strip', String(s.strip)]);
  if (s.explode > 0) q.push(['explode', String(Math.round(s.explode * 100))]);
  if (s.xray) q.push(['xray', '1']);
  if (s.isolated) q.push(['iso', s.isolated.id]);
  if (s.tab === 'blueprints' && s.sheet) {
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
