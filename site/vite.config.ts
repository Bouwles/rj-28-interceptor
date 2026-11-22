import { defineConfig, type Plugin } from 'vite';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const BASE = '/rj-28-interceptor/';
// Origin the static site is served from. Only used for the absolute URLs that
// link previews need (Open Graph, Twitter card, canonical).
const SITE_ORIGIN = process.env.SITE_ORIGIN ?? 'https://bouwles.github.io';

interface AssetEntry {
  bytes: number;
  width?: number;
  height?: number;
}

/** Pixel size of a JPEG from its start-of-frame marker. */
function jpegSize(file: string): { width: number; height: number } | null {
  const b = readFileSync(file);
  let i = 2;
  while (i + 9 < b.length) {
    if (b[i] !== 0xff) {
      i += 1;
      continue;
    }
    const marker = b[i + 1]!;
    if (marker >= 0xc0 && marker <= 0xc3) {
      return { height: b.readUInt16BE(i + 5), width: b.readUInt16BE(i + 7) };
    }
    i += 2 + b.readUInt16BE(i + 2);
  }
  return null;
}

/**
 * `virtual:asset-manifest`: byte sizes (and image dimensions) of everything the
 * loader may fetch, read from the files on disk when the build starts. The
 * loading screen's progress figure divides by these, so they are true sizes.
 */
function assetManifest(): Plugin {
  const id = 'virtual:asset-manifest';
  const resolved = '\0' + id;
  const scan = (): Record<string, AssetEntry> => {
    const out: Record<string, AssetEntry> = {};
    const add = (key: string, file: string) => {
      const entry: AssetEntry = { bytes: statSync(file).size };
      if (/\.jpe?g$/i.test(file)) Object.assign(entry, jpegSize(file) ?? {});
      out[key] = entry;
    };
    for (const dir of ['models', 'drawings', 'hdri', 'renders']) {
      const abs = join(root, 'public', dir);
      if (!existsSync(abs)) continue;
      for (const f of readdirSync(abs)) {
        const file = join(abs, f);
        if (statSync(file).isFile()) add(`${dir}/${f}`, file);
      }
    }
    const data = join(root, 'src', 'data');
    for (const f of readdirSync(data)) if (f.endsWith('.json')) add(`data/${f}`, join(data, f));
    const dev = join(root, 'src', 'dev', 'placeholder');
    if (existsSync(dev)) for (const f of readdirSync(dev)) add(`dev/${f}`, join(dev, f));
    return out;
  };
  return {
    name: 'rj28-asset-manifest',
    resolveId(source) {
      return source === id ? resolved : null;
    },
    load(loadId) {
      return loadId === resolved ? `export default ${JSON.stringify(scan())};` : null;
    },
  };
}

/** Fills the absolute URLs and the data-derived text in index.html. */
function htmlMeta(): Plugin {
  return {
    name: 'rj28-html-meta',
    transformIndexHtml(html) {
      const spec = JSON.parse(readFileSync(join(root, 'src/data/spec.json'), 'utf8'));
      const parts = JSON.parse(readFileSync(join(root, 'src/data/parts.json'), 'utf8')) as unknown[];
      const card = jpegSize(join(root, 'public/renders/social_card.jpg')) ?? { width: 0, height: 0 };
      const cm = Math.round(spec.height_to_cap_crown / 10);
      const values: Record<string, string> = {
        SITE_URL: SITE_ORIGIN + BASE,
        BASE,
        CARD_W: String(card.width),
        CARD_H: String(card.height),
        CARD_ALT:
          'A black humanoid robot seen from the front left, wearing a hard cap brim to the rear, with a thick cannon level over its right shoulder.',
        DESCRIPTION:
          `Interactive engineering dossier for the ${spec.designation}, a fictional ${cm} cm autonomous humanoid: ` +
          `scroll tour, part inspector, exploded view and drawing sheets, all measured from a scripted 3D model of ${parts.length} parts.`,
      };
      return html.replace(/%([A-Z_]+)%/g, (m, key: string) => values[key] ?? m);
    },
  };
}

export default defineConfig({
  base: BASE,
  plugins: [assetManifest(), htmlMeta()],
  define: {
    // The drawing set is written by the Blender build. Until it exists the
    // sheet viewer runs on a local stand-in, which this flag strips from the
    // bundle as soon as the real index is present.
    __HAS_SHEETS__: JSON.stringify(existsSync(resolve(root, 'src/data/sheets.json'))),
  },
  build: {
    target: 'es2022',
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 900,
  },
  server: { port: 5173, strictPort: false },
  preview: { port: 4173, strictPort: false },
});
