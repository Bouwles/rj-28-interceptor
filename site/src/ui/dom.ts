// Small DOM builders. `h('button.tool', { type: 'button', onclick }, 'Label')`.

export type Child = Node | string | number | null | undefined | false | Child[];
type Attrs = Record<string, unknown>;

const SVG_NS = 'http://www.w3.org/2000/svg';

function apply(el: Element, attrs: Attrs | null | undefined): void {
  if (!attrs) return;
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith('on') && typeof v === 'function') {
      el.addEventListener(k.slice(2), v as EventListener);
    } else if (k === 'class') {
      el.setAttribute('class', [el.getAttribute('class'), v].filter(Boolean).join(' '));
    } else if (k === 'dataset') {
      Object.assign((el as HTMLElement).dataset, v);
    } else if (k === 'style' && typeof v === 'object') {
      for (const [p, val] of Object.entries(v as Record<string, string>)) {
        (el as HTMLElement).style.setProperty(p, val);
      }
    } else {
      el.setAttribute(k, v === true ? '' : String(v));
    }
  }
}

function append(el: Node, children: Child[]): void {
  for (const c of children) {
    if (c === null || c === undefined || c === false) continue;
    if (Array.isArray(c)) append(el, c);
    else el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

function split(spec: string): [string, string] {
  const i = spec.indexOf('.');
  return i < 0 ? [spec, ''] : [spec.slice(0, i), spec.slice(i + 1).replaceAll('.', ' ')];
}

export function h<K extends keyof HTMLElementTagNameMap>(
  spec: K | `${K}.${string}`,
  attrs?: Attrs | null,
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const [tag, cls] = split(spec);
  const el = document.createElement(tag) as HTMLElementTagNameMap[K];
  if (cls) el.className = cls;
  apply(el, attrs);
  append(el, children);
  return el;
}

export function s<K extends keyof SVGElementTagNameMap>(
  spec: K | `${K}.${string}`,
  attrs?: Attrs | null,
  ...children: Child[]
): SVGElementTagNameMap[K] {
  const [tag, cls] = split(spec);
  const el = document.createElementNS(SVG_NS, tag) as SVGElementTagNameMap[K];
  if (cls) el.setAttribute('class', cls);
  apply(el, attrs);
  append(el, children);
  return el;
}

export function clearNode(el: Node): void {
  while (el.firstChild) el.removeChild(el.firstChild);
}

/** Replace an element's children in one go. */
export function fill(el: Element, ...children: Child[]): void {
  clearNode(el);
  append(el, children);
}

/**
 * Load `<img data-src>` elements under `root` when they come within a
 * viewport of the screen. Done by hand so that it also works for images the
 * browser would not treat as lazy, and without the browser's own placeholders.
 */
export function lazyImages(root: Element): void {
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        const img = e.target as HTMLImageElement;
        if (img.dataset.src) img.src = img.dataset.src;
        delete img.dataset.src;
        io.unobserve(img);
      }
    },
    { rootMargin: '100% 0px' },
  );
  for (const img of root.querySelectorAll('img[data-src]')) io.observe(img);
}

export const prefersReducedMotion = (): boolean =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export const isPhone = (): boolean => window.matchMedia('(max-width: 760px)').matches;
