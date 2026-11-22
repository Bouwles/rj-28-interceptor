import specJson from './spec.json';
import { assetExists, type AssetLoader } from '../loader/assets';
import type {
  Assembly,
  ModelManifest,
  MountData,
  Part,
  Sheet,
  SheetPlace,
  SheetSet,
  Spec,
} from './types';

export const spec = specJson as unknown as Spec;

// Every other data file is fetched at run time, so files that the Blender
// build has not written yet are simply absent from this map.
const dataUrls = import.meta.glob(['./*.json', '!./spec.json', '!./stations.json'], {
  query: '?url',
  import: 'default',
  eager: true,
}) as Record<string, string>;

export function dataUrl(name: string): string | null {
  return dataUrls[`./${name}`] ?? null;
}

/** URL of a file under `public/`, with the deployment base path. */
export function publicUrl(path: string): string {
  return import.meta.env.BASE_URL + path.replace(/^\//, '');
}

export interface MaterialRow {
  key: string;
  name: string;
  parts: number;
  mass_kg: number;
}

export interface Catalog {
  parts: Part[];
  byNumber: Map<string, Part>;
  assemblies: Assembly[];
  byAssembly: Map<string, Assembly>;
  materials: MaterialRow[];
}

export function buildCatalog(parts: Part[]): Catalog {
  const byNumber = new Map<string, Part>();
  const byAssembly = new Map<string, Assembly>();
  for (const a of spec.mass.by_assembly) {
    byAssembly.set(a.assembly, { id: a.assembly, name: a.name, parts: [], mass_kg: a.mass_kg });
  }
  const mats = new Map<string, MaterialRow>();
  for (const p of parts) {
    byNumber.set(p.number, p);
    let a = byAssembly.get(p.assembly);
    if (!a) {
      a = { id: p.assembly, name: p.assembly_name, parts: [], mass_kg: 0 };
      byAssembly.set(p.assembly, a);
    }
    a.parts.push(p);
    let m = mats.get(p.material_key);
    if (!m) {
      m = { key: p.material_key, name: p.material, parts: 0, mass_kg: 0 };
      mats.set(p.material_key, m);
    }
    m.parts += 1;
    m.mass_kg += p.mass_kg;
  }
  const assemblies = [...byAssembly.values()].sort((x, y) => x.id.localeCompare(y.id));
  for (const a of assemblies) a.parts.sort((x, y) => x.number.localeCompare(y.number));
  const materials = [...mats.values()].sort((x, y) => y.mass_kg - x.mass_kg);
  return { parts, byNumber, assemblies, byAssembly, materials };
}

export async function loadCatalog(loader: AssetLoader): Promise<Catalog> {
  const url = dataUrl('parts.json');
  if (!url) throw new Error('parts.json is missing from the build');
  return buildCatalog(await loader.json<Part[]>('data/parts.json', url));
}

async function optional<T>(loader: AssetLoader, name: string): Promise<T | null> {
  const url = dataUrl(name);
  if (!url) return null;
  try {
    return await loader.json<T>(`data/${name}`, url);
  } catch {
    return null;
  }
}

export function loadMount(loader: AssetLoader): Promise<MountData | null> {
  return optional<MountData>(loader, 'mount.json');
}

export function loadModelManifest(loader: AssetLoader): Promise<ModelManifest | null> {
  return optional<ModelManifest>(loader, 'model.json');
}

/** Announce optional data files to the loader so they count in the total. */
export function planData(loader: AssetLoader): void {
  for (const key of Object.keys(dataUrls)) loader.plan(`data/${key.slice(2)}`);
}

// ── Drawing sheets ──────────────────────────────────────────────────────────
// sheets.json: `{ set: { file, revision }, sheets: [{ id, number, title, file,
// width, height, parts }] }`, where `parts` maps a part number or an assembly
// id to its places on the sheet. Coordinates are SVG user units.

function place(v: unknown): SheetPlace | null {
  if (Array.isArray(v) && typeof v[0] === 'number' && typeof v[1] === 'number') {
    return { x: v[0], y: v[1], w: Number(v[2]) || 0, h: Number(v[3]) || 0, view: '', balloon: false };
  }
  if (v && typeof v === 'object') {
    const o = v as Record<string, unknown>;
    if (typeof o.x !== 'number' || typeof o.y !== 'number') return null;
    const balloon = !!o.b;
    return {
      x: o.x,
      y: o.y,
      w: Number(o.w) || 0,
      h: Number(o.h) || 0,
      view: typeof o.v === 'string' ? o.v : '',
      balloon,
      // A balloon also records where its leader ends: the thing it points at.
      target: balloon && typeof o.tx === 'number' && typeof o.ty === 'number' ? { x: o.tx, y: o.ty } : undefined,
    };
  }
  return null;
}

function placeMap(raw: unknown): Map<string, SheetPlace[]> {
  const out = new Map<string, SheetPlace[]>();
  if (!raw || typeof raw !== 'object') return out;
  for (const [key, v] of Object.entries(raw as Record<string, unknown>)) {
    // One place, or a list of them. `[x, y]` on its own is a single place.
    const single = !Array.isArray(v) || typeof v[0] === 'number';
    const places = (single ? [v] : (v as unknown[])).map(place).filter((x): x is SheetPlace => x !== null);
    if (places.length) out.set(key, places);
  }
  return out;
}

export function normaliseSheets(
  raw: unknown,
  resolve: (file: string) => { url: string; key: string } | null,
  placeholder: boolean,
): Sheet[] {
  const list = Array.isArray(raw) ? raw : (raw as { sheets?: unknown[] } | null)?.sheets;
  if (!Array.isArray(list)) return [];
  const sheets: Sheet[] = [];
  list.forEach((entry, i) => {
    if (!entry || typeof entry !== 'object') return;
    const o = entry as Record<string, unknown>;
    const file = typeof o.file === 'string' ? o.file : null;
    if (!file) return;
    const where = resolve(file.replace(/^.*[\\/]/, ''));
    if (!where) return;
    const number = String(o.number ?? o.id ?? i + 1);
    sheets.push({
      id: String(o.id ?? number),
      number,
      title: String(o.title ?? ''),
      scale: typeof o.scale === 'string' ? o.scale : '',
      url: where.url,
      key: where.key,
      width: Number(o.width) || 0,
      height: Number(o.height) || 0,
      places: placeMap(o.parts),
      placeholder,
    });
  });
  return sheets;
}

export async function loadSheets(loader: AssetLoader): Promise<SheetSet | null> {
  const raw = await optional<unknown>(loader, 'sheets.json');
  if (raw) {
    const sheets = normaliseSheets(
      raw,
      // A sheet whose file has not been exported yet is left out of the set.
      (file) =>
        assetExists(`drawings/${file}`) ? { url: publicUrl(`drawings/${file}`), key: `drawings/${file}` } : null,
      false,
    );
    const set = (raw as { set?: { file?: unknown; revision?: unknown } }).set;
    const pdfName = typeof set?.file === 'string' ? set.file.replace(/^.*[\\/]/, '') : 'RJ28-GA-set.pdf';
    const pdfUrl = assetExists(`drawings/${pdfName}`) ? publicUrl(`drawings/${pdfName}`) : null;
    const revision = typeof set?.revision === 'string' ? set.revision : null;
    if (sheets.length) return { sheets, pdfUrl, revision, placeholder: false };
  }
  if (!__HAS_SHEETS__) {
    const dev = await import('../dev/placeholder');
    return dev.placeholderSheetSet();
  }
  return null;
}

/** The place where something is drawn largest on a sheet, ignoring its balloon. */
export function bestPlace(places: SheetPlace[] | undefined): SheetPlace | null {
  let best: SheetPlace | null = null;
  for (const p of places ?? []) {
    if (p.balloon) continue;
    if (!best || p.w * p.h > best.w * best.h) best = p;
  }
  return best ?? places?.[0] ?? null;
}

/**
 * Where to show a part in the drawings: the sheet that draws it largest, which
 * is the detail sheet when there is one. Falls back to its assembly.
 */
export function findOnSheets(
  set: SheetSet | null,
  part: Part,
): { sheet: Sheet; at: SheetPlace; exact: boolean } | null {
  if (!set) return null;
  for (const [key, exact] of [
    [part.number, true],
    [part.assembly, false],
  ] as const) {
    let found: { sheet: Sheet; at: SheetPlace; exact: boolean } | null = null;
    for (const sheet of set.sheets) {
      const at = bestPlace(sheet.places.get(key));
      if (at && (!found || at.w * at.h > found.at.w * found.at.h)) found = { sheet, at, exact };
    }
    if (found) return found;
  }
  return null;
}
