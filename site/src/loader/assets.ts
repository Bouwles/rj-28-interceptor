import manifest from 'virtual:asset-manifest';

export interface LoadProgress {
  /** Bytes received so far across every planned item. */
  loaded: number;
  /** Bytes of every planned item, from the files on disk at build time. */
  total: number;
  /** File name currently arriving, or '' when idle. */
  current: string;
  /** Items finished / items planned. */
  filesDone: number;
  filesTotal: number;
}

interface Item {
  bytes: number;
  loaded: number;
  done: boolean;
}

type Listener = (p: LoadProgress) => void;

/** Size on disk of a public or data asset, by manifest key (`renders/x.jpg`, `data/parts.json`). */
export function assetBytes(key: string): number | null {
  return manifest[key]?.bytes ?? null;
}

export function assetExists(key: string): boolean {
  return key in manifest;
}

export function imageSize(key: string): { width: number; height: number } | null {
  const e = manifest[key];
  return e?.width && e.height ? { width: e.width, height: e.height } : null;
}

/**
 * Fetches assets while counting the bytes that actually arrive. Totals come
 * from the build-time manifest, so the figure on the loading screen is true
 * from the first frame and does not jump as responses start.
 */
export class AssetLoader {
  private items = new Map<string, Item>();
  private listeners = new Set<Listener>();
  private current = '';

  /** Declare an item before fetching it so the total is known up front. */
  plan(key: string, bytes?: number): void {
    if (this.items.has(key)) return;
    this.items.set(key, { bytes: bytes ?? assetBytes(key) ?? 0, loaded: 0, done: false });
    this.emit();
  }

  onProgress(fn: Listener): () => void {
    this.listeners.add(fn);
    fn(this.progress());
    return () => this.listeners.delete(fn);
  }

  progress(): LoadProgress {
    let loaded = 0;
    let total = 0;
    let filesDone = 0;
    for (const it of this.items.values()) {
      loaded += it.loaded;
      total += Math.max(it.bytes, it.loaded);
      if (it.done) filesDone += 1;
    }
    return { loaded, total, current: this.current, filesDone, filesTotal: this.items.size };
  }

  async bytes(key: string, url: string): Promise<Uint8Array> {
    this.plan(key);
    const item = this.items.get(key)!;
    const name = key.split('/').pop() ?? key;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
    this.current = name;
    const chunks: Uint8Array[] = [];
    const reader = res.body?.getReader();
    if (reader) {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        item.loaded += value.byteLength;
        this.current = name;
        this.emit();
      }
    } else {
      const buf = new Uint8Array(await res.arrayBuffer());
      chunks.push(buf);
      item.loaded = buf.byteLength;
    }
    const out = new Uint8Array(item.loaded);
    let offset = 0;
    for (const c of chunks) {
      out.set(c, offset);
      offset += c.byteLength;
    }
    item.bytes = item.loaded;
    item.done = true;
    if (this.current === name) this.current = '';
    this.emit();
    return out;
  }

  async text(key: string, url: string): Promise<string> {
    return new TextDecoder().decode(await this.bytes(key, url));
  }

  async json<T>(key: string, url: string): Promise<T> {
    return JSON.parse(await this.text(key, url)) as T;
  }

  /** Fetch an image through the counter so the <img> that follows is served from the HTTP cache. */
  async image(key: string, url: string): Promise<void> {
    await this.bytes(key, url);
  }

  private emit(): void {
    const p = this.progress();
    for (const fn of this.listeners) fn(p);
  }
}
