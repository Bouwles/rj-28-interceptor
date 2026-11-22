// Turns a drawing sheet (black line work on white, as exported) into an inline
// SVG that sits on the dark page. The exported sheets paint with two custom
// properties, `--ink` and `--paper`, which the page stylesheet redefines; any
// literal black or white is remapped here as well. Line weights are left
// exactly as drawn.

const NAMED: Record<string, [number, number, number]> = {
  black: [0, 0, 0],
  white: [255, 255, 255],
  gray: [128, 128, 128],
  grey: [128, 128, 128],
  silver: [192, 192, 192],
};

function parseColour(value: string): [number, number, number] | null {
  const v = value.trim().toLowerCase();
  if (v in NAMED) return NAMED[v]!;
  let m = /^#([0-9a-f]{3})$/.exec(v);
  if (m) return [...m[1]!].map((c) => parseInt(c + c, 16)) as [number, number, number];
  m = /^#([0-9a-f]{6})$/.exec(v);
  if (m) return [0, 2, 4].map((i) => parseInt(m![1]!.slice(i, i + 2), 16)) as [number, number, number];
  m = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/.exec(v);
  if (m) return [Number(m[1]), Number(m[2]), Number(m[3])];
  return null;
}

/** Map a paint value from the paper drawing to the dark sheet. Unknown values pass through. */
function mapColour(value: string): string {
  const rgb = parseColour(value);
  if (!rgb) return value;
  const [r, g, b] = rgb;
  if (Math.max(r, g, b) - Math.min(r, g, b) > 40) return value; // a real colour: keep it
  const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  if (lum < 0.25) return 'currentColor';
  if (lum > 0.85) return 'var(--sheet-paper)';
  return 'var(--sheet-mid)';
}

const PAINT = /\b(fill|stroke|color|stop-color)\s*:\s*([^;}!]+)/gi;
const mapCss = (css: string) => css.replace(PAINT, (_, prop: string, val: string) => `${prop}:${mapColour(val)}`);

/**
 * A <style> inside inline SVG applies to the whole page. Prefix every rule so
 * the sheet's `.vis`, `.txt` and the rest can only ever touch the sheet.
 */
const scopeCss = (css: string) =>
  css.replace(/(^|\})([^{}@]+)\{/g, (_, close: string, selectors: string) => {
    const scoped = selectors
      .split(',')
      .map((sel) => `.sheet-svg ${sel.trim()}`)
      .join(',');
    return `${close}${scoped}{`;
  });

export interface PreparedSheet {
  svg: SVGSVGElement;
  /** viewBox of the sheet in its own units. */
  box: { x: number; y: number; width: number; height: number };
}

export function prepareSheet(text: string): PreparedSheet | null {
  const doc = new DOMParser().parseFromString(text, 'image/svg+xml');
  const root = doc.documentElement;
  if (!root || root.nodeName.toLowerCase() !== 'svg' || doc.querySelector('parsererror')) return null;

  // The sheets are our own files, but inline SVG runs in the page: allow drawing content only.
  for (const el of [...root.querySelectorAll('script, foreignObject, iframe, object, embed')]) el.remove();
  const all = [root, ...root.querySelectorAll('*')];
  for (const el of all) {
    for (const attr of [...el.attributes]) {
      const name = attr.name.toLowerCase();
      if (name.startsWith('on')) el.removeAttribute(attr.name);
      else if ((name === 'href' || name === 'xlink:href') && /^\s*javascript:/i.test(attr.value)) el.removeAttribute(attr.name);
      else if (name === 'fill' || name === 'stroke' || name === 'stop-color' || name === 'color') {
        el.setAttribute(attr.name, mapColour(attr.value));
      } else if (name === 'style') el.setAttribute('style', mapCss(attr.value));
    }
    if (el.nodeName.toLowerCase() === 'style') {
      // The sheets embed the two typefaces so they render as standalone files.
      // Inline, the page already has them; declaring them again would make the
      // browser swap every face on the page.
      const css = (el.textContent ?? '').replace(/@font-face\s*\{[^}]*\}/g, '');
      el.textContent = scopeCss(mapCss(css));
    }
  }

  const svg = document.importNode(root, true) as unknown as SVGSVGElement;
  let vb = svg.viewBox?.baseVal;
  if (!vb || !vb.width || !vb.height) {
    const w = parseFloat(svg.getAttribute('width') ?? '') || 420;
    const hgt = parseFloat(svg.getAttribute('height') ?? '') || 297;
    svg.setAttribute('viewBox', `0 0 ${w} ${hgt}`);
    vb = svg.viewBox.baseVal;
  }
  const box = { x: vb.x, y: vb.y, width: vb.width, height: vb.height };
  svg.removeAttribute('width');
  svg.removeAttribute('height');
  svg.classList.add('sheet-svg');
  // SVG's default paint is black; on this page the default is the ink colour.
  if (!svg.hasAttribute('fill')) svg.setAttribute('fill', 'currentColor');

  if (!svg.querySelector('.paper')) {
    const paper = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    paper.setAttribute('class', 'paper');
    paper.setAttribute('x', String(box.x));
    paper.setAttribute('y', String(box.y));
    paper.setAttribute('width', String(box.width));
    paper.setAttribute('height', String(box.height));
    svg.insertBefore(paper, svg.firstChild);
  }
  return { svg, box };
}
