// Box model: an orthographic drawing of every part's bounding box, made from
// parts.json alone. It stands in for the 3D view in the static edition, so
// parts can still be located, picked and measured without a GPU. Boxes are
// drawn far to near with an opaque fill, which hides what is behind them.

import { isStripped, isVisible, select, type App } from '../app/context';
import type { BlueprintView, MountState } from '../app/store';
import { spec } from '../data';
import { mm, trim1 } from '../data/format';
import type { Part, Vec3 } from '../data/types';
import type { CameraReadout } from '../scene/types';
import { clearNode, s } from './dom';

type P2 = [number, number];

interface Basis {
  r: Vec3; // screen right
  t: Vec3; // screen up
  f: Vec3; // into the screen
}

const SQ3 = Math.sqrt(3);
const SQ2 = Math.SQRT2;
const BASES: Record<BlueprintView, Basis> = {
  front: { r: [1, 0, 0], t: [0, 0, 1], f: [0, 1, 0] },
  rear: { r: [-1, 0, 0], t: [0, 0, 1], f: [0, -1, 0] },
  side: { r: [0, -1, 0], t: [0, 0, 1], f: [1, 0, 0] },
  top: { r: [1, 0, 0], t: [0, 1, 0], f: [0, 0, -1] },
  // True isometric from the front right, so the mount side is towards the viewer.
  iso: {
    r: [1 / SQ2, -1 / SQ2, 0],
    t: [1 / (SQ2 * SQ3), 1 / (SQ2 * SQ3), 2 / (SQ2 * SQ3)],
    f: [1 / SQ3, 1 / SQ3, -1 / SQ3],
  },
};

export const VIEW_TITLE: Record<BlueprintView, string> = {
  front: 'Front elevation',
  side: 'Right side elevation',
  rear: 'Rear elevation',
  top: 'Plan',
  iso: 'Isometric',
};

/** Grid pitch of the flat views, millimetres. */
export const GRID_MM = 100;

const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

/** Camera angles of a view, in the same convention the 3D scene reports. */
export function viewReadout(view: BlueprintView): CameraReadout {
  const f = BASES[view].f;
  const c: Vec3 = [-f[0], -f[1], -f[2]];
  const flat = Math.hypot(c[0], c[1]);
  return {
    azimuthDeg: flat < 1e-6 ? 0 : (Math.atan2(c[0], -c[1]) * 180) / Math.PI,
    elevationDeg: (Math.asin(c[2]) * 180) / Math.PI,
    distanceMm: null,
  };
}

function hull(points: P2[]): P2[] {
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o: P2, a: P2, b: P2) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: P2[] = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2]!, lower[lower.length - 1]!, p) <= 1e-6) lower.pop();
    lower.push(p);
  }
  const upper: P2[] = [];
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i]!;
    while (upper.length >= 2 && cross(upper[upper.length - 2]!, upper[upper.length - 1]!, p) <= 1e-6) upper.pop();
    upper.push(p);
  }
  lower.pop();
  upper.pop();
  return lower.concat(upper);
}

function inside(poly: P2[], x: number, y: number): boolean {
  let sign = 0;
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i]!;
    const b = poly[(i + 1) % poly.length]!;
    const c = (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0]);
    if (Math.abs(c) < 1e-9) continue;
    const sg = c > 0 ? 1 : -1;
    if (sign === 0) sign = sg;
    else if (sg !== sign) return false;
  }
  return true;
}

interface Shape {
  part: Part;
  poly: P2[]; // drawing coordinates: x right, y down, millimetres
  area: number;
  depth: number;
  solid: boolean;
}

/** Which pose parts.json was measured in, read from the data itself. */
function dataPose(parts: Part[]): MountState {
  let top = 0;
  for (const p of parts) if (p.mount_group === 'elev') top = Math.max(top, p.bbox_max[2]);
  return top > spec.envelope.deployed.height + 1 ? 'stowed' : 'deployed';
}

/**
 * Bounding box of an elevating part in the requested mount state. The swing is
 * a quarter turn about the trunnion, which maps an axis-aligned box onto
 * another axis-aligned box exactly, so no approximation is involved.
 */
function posedBox(p: Part, mount: MountState, measured: MountState): [Vec3, Vec3] {
  const quarter = Math.abs(spec.mount.elevation[1] - 90) < 1e-6;
  if (p.mount_group !== 'elev' || mount === measured || !quarter) return [p.bbox_min, p.bbox_max];
  const [, y0, z0] = spec.mount.trunnion;
  const [x1, y1, z1] = p.bbox_min;
  const [x2, y2, z2] = p.bbox_max;
  if (measured === 'stowed') {
    // stowed → deployed: (dy, dz) → (−dz, dy)
    return [
      [x1, y0 - (z2 - z0), z0 + (y1 - y0)],
      [x2, y0 - (z1 - z0), z0 + (y2 - y0)],
    ];
  }
  // deployed → stowed: (dy, dz) → (dz, −dy)
  return [
    [x1, y0 + (z1 - z0), z0 - (y2 - y0)],
    [x2, y0 + (z2 - z0), z0 - (y1 - y0)],
  ];
}

interface Frame {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

export interface BoxModelOptions {
  /** Draw overall dimension lines and axis labels (blueprint treatment). */
  dimensions: boolean;
}

export class BoxModel {
  readonly el: SVGSVGElement;
  private view: BlueprintView;
  private shapes: Shape[] = [];
  private frame: Frame = { minX: 0, maxX: 1, minY: 0, maxY: 1 };
  private measured: MountState;
  private gBoxes = s('g.bm-boxes');
  private gGrid = s('g.bm-grid');
  private gDims = s('g.bm-dims');
  private gMark = s('g.bm-mark');
  private gMeasure = s('g.bm-measure');
  private first: P2 | null = null;
  private ro: ResizeObserver;

  constructor(
    private app: App,
    view: BlueprintView,
    private opts: BoxModelOptions,
  ) {
    this.view = view;
    this.measured = dataPose(app.catalog.parts);
    this.el = s(
      'svg.boxmodel',
      { role: 'img', preserveAspectRatio: 'xMidYMid meet' },
      this.gGrid,
      this.gBoxes,
      this.gDims,
      this.gMark,
      this.gMeasure,
    );
    this.el.addEventListener('pointermove', (e) => this.onMove(e));
    this.el.addEventListener('pointerleave', () => app.hover.set({ part: null, clientX: 0, clientY: 0 }));
    this.el.addEventListener('click', (e) => this.onClick(e));
    this.ro = new ResizeObserver(() => this.rescale());
    this.ro.observe(this.el);

    const { store } = app;
    store.watch(
      (st) => [st.mount, st.xray, st.hidden, st.isolated, st.strip] as const,
      () => this.rebuild(),
    );
    store.watch(
      (st) => st.selected,
      () => this.mark(),
    );
    store.watch(
      (st) => st.measure,
      (on) => {
        this.first = null;
        this.el.classList.toggle('measuring', on);
        if (!on) clearNode(this.gMeasure);
      },
    );
    app.measurement.subscribe((m) => {
      if (!m) clearNode(this.gMeasure);
    }, false);
  }

  setView(view: BlueprintView): void {
    if (view === this.view) return;
    this.view = view;
    this.first = null;
    clearNode(this.gMeasure);
    this.rebuild();
  }

  getView(): BlueprintView {
    return this.view;
  }

  dispose(): void {
    this.ro.disconnect();
  }

  /** Model millimetres → drawing coordinates (y down). */
  private project(p: Vec3): P2 {
    const b = BASES[this.view];
    return [dot(p, b.r), -dot(p, b.t)];
  }

  private rebuild(): void {
    const { mount, xray } = this.app.store.get();
    const b = BASES[this.view];
    const shapes: Shape[] = [];
    for (const part of this.app.catalog.parts) {
      if (!isVisible(this.app, part) || isStripped(this.app, part)) continue;
      if (part.material_key === 'decal') continue; // no thickness: nothing to box
      const [lo, hi] = posedBox(part, mount, this.measured);
      const corners: P2[] = [];
      for (let i = 0; i < 8; i++) {
        corners.push(this.project([i & 1 ? hi[0] : lo[0], i & 2 ? hi[1] : lo[1], i & 4 ? hi[2] : lo[2]]));
      }
      const poly = hull(corners);
      let area = 0;
      for (let i = 0; i < poly.length; i++) {
        const p = poly[i]!;
        const q = poly[(i + 1) % poly.length]!;
        area += p[0] * q[1] - q[0] * p[1];
      }
      const centre: Vec3 = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2];
      // A box hides what is behind it only if it stands for one solid thing:
      // screw sets and cable runs span large, mostly empty volumes.
      const solid =
        part.count === 1 &&
        part.material_class !== 'harness' &&
        !(xray && part.material_class === 'armour');
      shapes.push({ part, poly, area: Math.abs(area) / 2, depth: dot(centre, b.f), solid });
    }
    shapes.sort((x, y) => y.depth - x.depth);
    this.shapes = shapes;

    // Frame: both mount envelopes, so the drawing does not jump when the mount moves.
    const env = [spec.envelope.stowed, spec.envelope.deployed, spec.body];
    const f: Frame = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity };
    for (const e of env) {
      for (let i = 0; i < 8; i++) {
        const [x, y] = this.project([i & 1 ? e.max[0] : e.min[0], i & 2 ? e.max[1] : e.min[1], i & 4 ? e.max[2] : e.min[2]]);
        f.minX = Math.min(f.minX, x);
        f.maxX = Math.max(f.maxX, x);
        f.minY = Math.min(f.minY, y);
        f.maxY = Math.max(f.maxY, y);
      }
    }
    this.frame = f;
    // Room round the figure for the scale, and for dimension lines where they are drawn.
    const m = this.opts.dimensions && this.view !== 'iso' ? 360 : 150;
    this.el.setAttribute('viewBox', `${f.minX - m} ${f.minY - m * 0.45} ${f.maxX - f.minX + 2 * m} ${f.maxY - f.minY + m * 1.3}`);
    this.el.setAttribute('aria-label', `${VIEW_TITLE[this.view]} of the part bounding boxes, mount ${mount}`);

    clearNode(this.gBoxes);
    const frag = document.createDocumentFragment();
    for (const sh of shapes) {
      const d = 'M' + sh.poly.map((p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join('L') + 'Z';
      frag.appendChild(s('path', { d, class: sh.solid ? 'bm-solid' : 'bm-open' }));
    }
    this.gBoxes.appendChild(frag);
    this.drawGrid();
    this.drawDims();
    this.mark();
    this.rescale();
  }

  private drawGrid(): void {
    clearNode(this.gGrid);
    const f = this.frame;
    if (this.view === 'iso') return;
    const step = GRID_MM;
    const x0 = Math.floor(f.minX / step) * step - step;
    const x1 = Math.ceil(f.maxX / step) * step + step;
    const y0 = Math.floor(f.minY / step) * step - (this.view === 'top' ? step : 0);
    const y1 = this.view === 'top' ? Math.ceil(f.maxY / step) * step + step : 0;
    let fine = '';
    let coarse = '';
    for (let x = x0; x <= x1; x += step) {
      const seg = `M${x} ${y0}V${y1}`;
      if (x % 500 === 0) coarse += seg;
      else fine += seg;
    }
    for (let y = y0; y <= y1; y += step) {
      const seg = `M${x0} ${y}H${x1}`;
      if (y % 500 === 0) coarse += seg;
      else fine += seg;
    }
    this.gGrid.append(s('path.bm-grid-fine', { d: fine }), s('path.bm-grid-coarse', { d: coarse }));
    if (this.view !== 'top') {
      this.gGrid.append(s('path.bm-floor', { d: `M${x0} 0H${x1}` }));
      // Height scale up the left edge, every 500 mm.
      for (let y = 0; y >= y0; y -= 500) {
        this.gGrid.append(s('text.bm-scale', { x: x0, y, dx: '-0.6em', dy: '0.32em', 'text-anchor': 'end' }, String(-y)));
      }
    }
  }

  private dimension(a: P2, b: P2, offset: number, label: string, vertical: boolean): void {
    // Extension lines out to a dimension line with 45° ticks, value centred on it.
    const g = s('g.bm-dim');
    if (vertical) {
      const x = offset;
      g.append(
        s('path', { d: `M${a[0]} ${a[1]}H${x + Math.sign(x - a[0]) * 30}M${b[0]} ${b[1]}H${x + Math.sign(x - b[0]) * 30}M${x} ${a[1]}V${b[1]}` }),
        s('path.bm-tick', { d: `M${x - 14} ${a[1] + 14}L${x + 14} ${a[1] - 14}M${x - 14} ${b[1] + 14}L${x + 14} ${b[1] - 14}` }),
        // Read from the right, as on a drawing: the figure runs up the line.
        s('text', { x, y: (a[1] + b[1]) / 2, dy: '-0.55em', 'text-anchor': 'middle', transform: `rotate(-90 ${x} ${(a[1] + b[1]) / 2})` }, label),
      );
    } else {
      const y = offset;
      g.append(
        s('path', { d: `M${a[0]} ${a[1]}V${y + 30}M${b[0]} ${b[1]}V${y + 30}M${a[0]} ${y}H${b[0]}` }),
        s('path.bm-tick', { d: `M${a[0] - 14} ${y + 14}L${a[0] + 14} ${y - 14}M${b[0] - 14} ${y + 14}L${b[0] + 14} ${y - 14}` }),
        s('text', { x: (a[0] + b[0]) / 2, y, dy: '1.5em', 'text-anchor': 'middle' }, label),
      );
    }
    this.gDims.append(g);
  }

  private drawDims(): void {
    clearNode(this.gDims);
    if (!this.opts.dimensions || this.view === 'iso') return;
    const { mount } = this.app.store.get();
    const env = spec.envelope[mount];
    const f = this.frame;
    const lo = this.project(env.min);
    const hi = this.project(env.max);
    const left = Math.min(lo[0], hi[0]);
    const right = Math.max(lo[0], hi[0]);
    // Figures are millimetres without the unit, as on the drawing sheets.
    if (this.view === 'top') {
      const top = Math.min(lo[1], hi[1]);
      const bottom = Math.max(lo[1], hi[1]);
      this.dimension([left, bottom], [right, bottom], bottom + 170, trim1(env.width), false);
      this.dimension([right, top], [right, bottom], right + 170, trim1(env.depth), true);
      return;
    }
    const horizontal = this.view === 'side' ? env.depth : env.width;
    this.dimension([left, 0], [right, 0], 170, trim1(horizontal), false);
    // Height to the cap crown, and overall height in this mount state.
    const crown = spec.height_to_cap_crown;
    this.dimension([f.maxX, 0], [f.maxX, -crown], f.maxX + 150, trim1(crown), true);
    this.dimension([f.maxX, 0], [f.maxX, -env.height], f.maxX + 300, trim1(env.height), true);
  }

  private mark(): void {
    clearNode(this.gMark);
    const { selected } = this.app.store.get();
    if (!selected) return;
    const sh = this.shapes.find((x) => x.part.number === selected);
    if (!sh) return;
    const d = 'M' + sh.poly.map((p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join('L') + 'Z';
    // Tag above the box, growing inwards so it stays inside the drawing.
    const xs = sh.poly.map((p) => p[0]);
    const y = Math.min(...sh.poly.map((p) => p[1]));
    const rightHalf = (Math.min(...xs) + Math.max(...xs)) / 2 > (this.frame.minX + this.frame.maxX) / 2;
    this.gMark.append(
      s('path.bm-selected', { d }),
      s(
        'text.bm-selected-tag',
        { x: rightHalf ? Math.max(...xs) : Math.min(...xs), y, dy: '-0.7em', 'text-anchor': rightHalf ? 'end' : 'start' },
        sh.part.number,
      ),
    );
  }

  /** Text and markers are sized in screen pixels, whatever the drawing scale. */
  private rescale(): void {
    const vb = this.el.viewBox.baseVal;
    const w = this.el.clientWidth;
    const hgt = this.el.clientHeight;
    if (!w || !hgt || !vb.width) return;
    const scale = Math.min(w / vb.width, hgt / vb.height);
    this.el.style.setProperty('--u', String(1 / scale));
  }

  private toDrawing(e: MouseEvent): P2 | null {
    const ctm = this.el.getScreenCTM();
    if (!ctm) return null;
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    return [p.x, p.y];
  }

  private pick(pt: P2): Part | null {
    let best: Shape | null = null;
    for (const sh of this.shapes) {
      if (best && sh.area >= best.area) continue;
      if (inside(sh.poly, pt[0], pt[1])) best = sh;
    }
    return best?.part ?? null;
  }

  private onMove(e: PointerEvent): void {
    if (e.pointerType === 'touch') return;
    const pt = this.toDrawing(e);
    if (!pt || this.app.store.get().measure) return;
    this.app.hover.set({ part: this.pick(pt)?.number ?? null, clientX: e.clientX, clientY: e.clientY });
  }

  private onClick(e: MouseEvent): void {
    const pt = this.toDrawing(e);
    if (!pt) return;
    if (this.app.store.get().measure) {
      this.measureClick(pt);
      return;
    }
    select(this.app, this.pick(pt)?.number ?? null);
  }

  private measureClick(pt: P2): void {
    if (this.view === 'iso') return;
    if (!this.first) {
      this.first = pt;
      this.app.measurement.set(null);
      clearNode(this.gMeasure);
      this.gMeasure.append(s('circle.bm-m-point', { cx: pt[0], cy: pt[1], r: 4 }));
      return;
    }
    const a = this.first;
    this.first = null;
    const b = BASES[this.view];
    const model = (p: P2): Vec3 => [
      b.r[0] * p[0] - b.t[0] * p[1],
      b.r[1] * p[0] - b.t[1] * p[1],
      b.r[2] * p[0] - b.t[2] * p[1],
    ];
    const distanceMm = Math.hypot(pt[0] - a[0], pt[1] - a[1]);
    clearNode(this.gMeasure);
    this.gMeasure.append(
      s('path.bm-m-line', { d: `M${a[0]} ${a[1]}L${pt[0]} ${pt[1]}` }),
      s('circle.bm-m-point', { cx: a[0], cy: a[1], r: 4 }),
      s('circle.bm-m-point', { cx: pt[0], cy: pt[1], r: 4 }),
      s('text.bm-m-text', { x: (a[0] + pt[0]) / 2, y: (a[1] + pt[1]) / 2, dy: '-0.6em', 'text-anchor': 'middle' }, mm(distanceMm)),
    );
    this.app.measurement.set({ a: model(a), b: model(pt), distanceMm, plane: this.view });
  }
}
