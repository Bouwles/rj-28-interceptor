"""Engineering drawing sheets, generated from the model.

    blender --background --python blender/build.py -- drawings [sheet=1,3] [cache] [lines] [nopng] [nopdf]

Five A1 sheets as SVG (site/public/drawings), a combined PDF, PNG previews
(docs/review/phase8) and the index the site's sheet viewer reads
(site/src/data/sheets.json).

Method. Nothing here is rendered: the line work is projected.

1. Every part gives up its un-bevelled mesh: vertices, edges, the normals of
   the two faces on each edge, triangles, and which loose island each edge
   belongs to (a screw set is one part and many islands).
2. For a view direction the candidate edges are the creases (over 32 degrees),
   the open borders and the contour edges (one face towards the viewer, one
   away), which is what gives a cylinder or the cap crown its outline.
3. Each candidate is sampled along its length. A ray from the sample towards
   the viewer through a BVH of the scene says whether it is hidden; the ends
   of each visible run are refined by bisection.
4. Two more rays, one either side of a visible contour sample and away from
   the viewer, measure the depth step behind the edge. A large step is an
   outline (thick); everything else is detail (thin).
5. Runs are chained into polylines, simplified and written as SVG paths,
   grouped per view and per part.

Dimensions, tables and notes quote spec.json, parts.json, the mount sweep
report and the model in the scene. No number is typed in this file except
sheet layout (millimetres on paper) and line weights.
"""
import base64
import json
import math
import subprocess
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import axes, explode, frames as FR, parts, poses
from .lib import core as C

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "public" / "drawings"
DATA = ROOT / "site" / "src" / "data"
FONTS = ROOT / "site" / "public" / "fonts"
REVIEW = ROOT / "docs" / "review" / "phase8"
WORK = ROOT / "blender" / "out" / "drawings"
SWEEP = ROOT / "blender" / "out" / "mount_sweep_model.json"
EDGE = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")]

# ── the set ──────────────────────────────────────────────────────────────────
SHEET_W, SHEET_H, MARGIN = 841.0, 594.0, 10.0
DRAWN = "P. NERCESSIAN"
REVISIONS = [                                    # oldest first; the last one is current
    ("A", "PROPORTIONS AND MOUNT GEOMETRY FROZEN AT GATE G1", "2026-11-16"),
    ("B", "DETAILED MODEL, SEVENTEEN ASSEMBLIES, GATE G2", "2026-11-21"),
    ("C", "KNEE ANCHORS, ANKLE PADS, LOOMS REVISED. DRAWING SET ISSUED", "2026-11-22"),
]
TITLES = {1: "General arrangement", 2: "Head and cap assembly", 3: "Interceptor cannon and mount",
          4: "Leg mechanism", 5: "Exploded isometric"}
TOLERANCE = "GENERAL TOLERANCES ISO 2768-mK. DO NOT SCALE."

# line weights and text, millimetres on paper
CSS = """
svg{--ink:#000;--paper:#fff}
.paper{fill:var(--paper)}
path,line,circle,polyline,rect{fill:none;stroke:var(--ink);stroke-linecap:round;stroke-linejoin:round}
.vis{stroke-width:.38}
.det{stroke-width:.15}
.ctx{stroke-width:.13}
.cut{stroke-width:.6}
.hat{stroke-width:.09;stroke-linecap:butt}
.hid{stroke-width:.15;stroke-dasharray:1.8 .9;stroke-linecap:butt}
.pha{stroke-width:.18;stroke-dasharray:7 1 .7 1 .7 1;stroke-linecap:butt}
.ctr{stroke-width:.13;stroke-dasharray:6 1.1 .7 1.1;stroke-linecap:butt}
.dim{stroke-width:.15}
.brk{stroke-width:.2;stroke-dasharray:10 1.2 1 1.2;stroke-linecap:butt}
.frame{stroke-width:.7;stroke-linejoin:miter}
.rule{stroke-width:.25}
.fine{stroke-width:.13}
.ink{fill:var(--ink);stroke:none}
.mask{fill:var(--paper);stroke:none}
.bal circle{fill:var(--paper);stroke-width:.25}
.bal{cursor:pointer}
text{fill:var(--ink);stroke:none}
.tt{font-family:"Archivo",sans-serif;font-stretch:70%;font-weight:650;letter-spacing:.03em}
.tl{font-family:"Archivo",sans-serif;font-stretch:78%;font-weight:500;letter-spacing:.03em}
.tn{font-family:"IBM Plex Mono",monospace;font-weight:400}
.tm{font-family:"IBM Plex Mono",monospace;font-weight:500}
"""
MONO_ADV = 0.6          # IBM Plex Mono advance, em
SANS_ADV = 0.5          # Archivo at 70 to 78% width, upper case, rough average for layout only

X, Y, Z = np.eye(3)


def fmt(v, dec=1):
    """Millimetres as a drawing prints them: no unit, no separator, no trailing zero."""
    if abs(v - round(v)) < 0.5 * 10 ** -dec:
        return str(int(round(v)))
    return f"{v:.{dec}f}"


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ── geometry out of Blender ──────────────────────────────────────────────────
class Geo:
    """One part as arrays, world space, millimetres."""
    __slots__ = ("number", "name", "asm", "mat", "group", "zone", "V", "E", "N1", "N2", "NF", "sharp", "isl",
                 "nisl", "T", "TN")


def _islands(nv, E):
    lab = np.arange(nv)
    if len(E) == 0:
        return lab
    e0, e1 = E[:, 0], E[:, 1]
    while True:
        low = np.minimum(lab[e0], lab[e1])
        new = lab.copy()
        np.minimum.at(new, e0, low)
        np.minimum.at(new, e1, low)
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    return np.unique(lab, return_inverse=True)[1]


def geo_from_mesh(me, mw, sharp_deg=32.0):
    g = Geo()
    nv, ne, npoly = len(me.vertices), len(me.edges), len(me.polygons)
    Rm = np.array(mw.to_3x3())
    V = np.empty(nv * 3)
    me.vertices.foreach_get("co", V)
    g.V = (V.reshape(-1, 3) @ Rm.T + np.array(mw.translation)) / C.MM
    E = np.empty(ne * 2, np.int32)
    me.edges.foreach_get("vertices", E)
    g.E = E.reshape(-1, 2)
    PN = np.empty(npoly * 3)
    me.polygons.foreach_get("normal", PN)
    PN = PN.reshape(-1, 3) @ Rm.T
    nl = len(me.loops)
    LE = np.empty(nl, np.int32)
    me.loops.foreach_get("edge_index", LE)
    tot = np.empty(npoly, np.int32)
    me.polygons.foreach_get("loop_total", tot)
    LP = np.repeat(np.arange(npoly), tot)
    order = np.argsort(LE, kind="stable")
    le, lp = LE[order], LP[order]
    g.NF = np.bincount(LE, minlength=ne)
    first = np.minimum(np.searchsorted(le, np.arange(ne)), max(nl - 1, 0))
    f1 = lp[first] if nl else np.zeros(ne, int)
    f2 = lp[np.minimum(first + 1, max(nl - 1, 0))] if nl else np.zeros(ne, int)
    g.N1 = PN[f1] if npoly else np.zeros((ne, 3))
    g.N2 = np.where((g.NF == 2)[:, None], PN[f2], g.N1) if npoly else np.zeros((ne, 3))
    cosd = np.einsum("ij,ij->i", g.N1, g.N2)
    g.sharp = (g.NF == 2) & (cosd < math.cos(math.radians(sharp_deg)))
    g.isl = _islands(nv, g.E)
    g.nisl = int(g.isl.max()) + 1 if nv else 0
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    T = np.empty(nt * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", T)
    g.T = T.reshape(-1, 3)
    tp = np.empty(nt, np.int32)
    me.loop_triangles.foreach_get("polygon_index", tp)
    g.TN = PN[tp] if nt else np.zeros((0, 3))
    return g


def geo_from_object(ob):
    """The part without its bevel. Only a part with shape keys needs evaluating."""
    me, tmp = ob.data, None
    if me.shape_keys:
        saved = [(m, m.show_viewport) for m in ob.modifiers]
        for m, _ in saved:
            m.show_viewport = False
        tmp = me = C.evaluated_mesh(ob)
        for m, s in saved:
            m.show_viewport = s
    g = geo_from_mesh(me, ob.matrix_world)
    if tmp is not None:
        bpy.data.meshes.remove(tmp)
    _tag(g, ob)
    return g


def _tag(g, ob):
    g.number, g.name, g.asm = ob["rj28_number"], ob["rj28_name"], ob["rj28_assembly"]
    g.mat, g.group, g.zone = ob.get("rj28_material", ""), ob.get("mount_group", ""), ob.get("zone", "")


def geo_cut(ob, co, no):
    """The part cut by a plane (point co and normal no in mm; the side the normal points to is removed),
    with the cut closed. Returns (Geo or None, cut edges or None); the cut edges are a pair of arrays:
    end points (n,2,3) in mm and, per edge, the outward normal of the surface it was cut from."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    co_m, n = Vector(co) * C.MM, Vector(no).normalized()
    res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-7, plane_co=co_m,
                                 plane_no=n, clear_outer=True, clear_inner=False)
    cut_edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_valid]
    loops = None
    if cut_edges:
        bm.normal_update()
        pts, nrm = [], []
        for e in cut_edges:
            if e.link_faces:
                pts.append([list(e.verts[0].co), list(e.verts[1].co)])
                nrm.append(list(e.link_faces[0].normal))
        if pts:
            loops = (np.array(pts) / C.MM, np.array(nrm))
        fill = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=cut_edges, normal=n)
        bm.normal_update()
        for f in [f for f in fill["geom"] if isinstance(f, bmesh.types.BMFace)]:
            if f.normal.dot(n) < 0:
                f.normal_flip()
    if not bm.faces:
        bm.free()
        return None, None
    me = bpy.data.meshes.new("_cut")
    bm.to_mesh(me)
    bm.free()
    g = geo_from_mesh(me, Matrix.Identity(4))
    bpy.data.meshes.remove(me)
    _tag(g, ob)
    return g, loops


class Scene:
    """A set of parts as flat arrays, with a BVH per view direction."""

    def __init__(self, geos):
        self.parts = geos
        self.index = {g.number: i for i, g in enumerate(geos)}
        vo = np.cumsum([0] + [len(g.V) for g in geos])
        io = np.cumsum([0] + [g.nisl for g in geos])
        cat = np.concatenate
        self.V = cat([g.V for g in geos])
        self.E = cat([g.E + vo[i] for i, g in enumerate(geos)])
        self.N1, self.N2 = cat([g.N1 for g in geos]), cat([g.N2 for g in geos])
        self.NF, self.sharp = cat([g.NF for g in geos]), cat([g.sharp for g in geos])
        self.EP = cat([np.full(len(g.E), i, np.int32) for i, g in enumerate(geos)])
        self.VI = cat([g.isl + io[i] for i, g in enumerate(geos)])
        self.nisl = int(io[-1])
        self.T = cat([g.T + vo[i] for i, g in enumerate(geos)])
        self.TN = cat([g.TN for g in geos])
        self.TP = cat([np.full(len(g.T), i, np.int32) for i, g in enumerate(geos)])
        self.VP = cat([np.full(len(g.V), i, np.int32) for i, g in enumerate(geos)])
        self._bvh, self._tris = {}, {}
        self._vl = None

    def mask(self, fn):
        return np.array([bool(fn(g)) for g in self.parts])

    def bvh(self, d, occl=None, key=None):
        """Occluders for view direction d. Faces seen edge-on hide nothing and are left out, which is
        what stops a ray grazing along the face it started on."""
        k = (tuple(np.round(d, 6)), key)
        if k not in self._bvh:
            keep = np.abs(self.TN @ d) > 0.012
            if occl is not None:
                keep &= occl[self.TP]
            if self._vl is None:
                self._vl = self.V.tolist()
            self._bvh[k] = BVHTree.FromPolygons(self._vl, self.T[keep].tolist(), all_triangles=True, epsilon=0.0)
            self._tris[k] = np.nonzero(keep)[0]
        return self._bvh[k]

    def visible_point(self, view, sel, occl=None, key=None, n=13, prefer=None, toward=(0.0, 0.0)):
        """View coordinates of a point where a part of the selection (boolean over parts) is what the
        viewer sees, as near the middle of the selection as possible, or near toward (-1..1 across its
        box). prefer(location) can ask for a kind of surface first (a cut face, say). None if hidden."""
        r, u, d = view.r, view.u, view.d
        bvh = self.bvh(d, occl, key)
        tris = self._tris[(tuple(np.round(d, 6)), key)]
        vm = sel[self.VP]
        if not vm.any():
            return None
        a, b = self.V[vm] @ r, self.V[vm] @ u
        zf = float((self.V @ d).max()) + 50.0
        ca, cb, ha, hb = (a.min() + a.max()) / 2, (b.min() + b.max()) / 2, np.ptp(a) / 2, np.ptp(b) / 2
        g = np.linspace(-0.94, 0.94, n)
        cand = sorted((((x - toward[0]) ** 2 + (y - toward[1]) ** 2, x, y) for x in g for y in g))
        nd = tuple(-d)

        def seen(pa, pb):
            hit = bvh.ray_cast(tuple(r * pa + u * pb + d * zf), nd)
            if hit[2] is None or not sel[self.TP[tris[hit[2]]]]:
                return 0
            return 2 if prefer is not None and prefer(hit[0]) else 1

        e = 0.9 / view.k
        best = {}
        for _, x, y in cand:
            pa, pb = ca + x * ha, cb + y * hb
            sc = seen(pa, pb)
            if not sc:
                continue
            solid = all(seen(pa + dx, pb + dy) == sc for dx, dy in ((e, 0), (-e, 0), (0, e), (0, -e)))
            best.setdefault((sc, solid), (pa, pb))
            if (2 if prefer is not None else 1, True) in best:
                break
        for key_ in ((2, True), (2, False), (1, True), (1, False)):
            if key_ in best:
                return best[key_]
        return None


# ── projection and hidden-line removal ───────────────────────────────────────
class View:
    """An orthographic view: r is paper-right, u is paper-up, the viewer sits along r x u."""

    def __init__(self, vid, title, r, u, scale, label=None):
        self.id, self.title = vid, title
        self.r, self.u = np.asarray(r, float), np.asarray(u, float)
        self.d = np.cross(self.r, self.u)
        self.k = scale
        self.scale_text = label or scale_text(scale)
        self.ox = self.oy = 0.0
        self.lines = {}             # (part number, css class) -> list of (n,2) polylines, view-local paper mm
        self.window = None

    def place(self, ox, oy):
        self.ox, self.oy = ox, oy
        return self

    def ab(self, p):
        p = np.asarray(p, float)
        return p @ self.r, p @ self.u

    def pt(self, a, b):
        """Paper position of view coordinates (model mm)."""
        return self.ox + a * self.k, self.oy - b * self.k

    def P(self, p):
        return self.pt(*self.ab(p))

    def bbox(self, classes=None, numbers=None):
        lo, hi = np.array([1e9, 1e9]), np.array([-1e9, -1e9])
        for (num, cls), pls in self.lines.items():
            if (classes and cls not in classes) or (numbers is not None and num not in numbers):
                continue
            for pl in pls:
                lo, hi = np.minimum(lo, pl.min(0)), np.maximum(hi, pl.max(0))
        if lo[0] > hi[0]:
            return None
        return self.ox + lo[0], self.oy + lo[1], self.ox + hi[0], self.oy + hi[1]

    def _segments(self, classes=("vis", "det", "cut")):
        if getattr(self, "_segcache", None) is None or self._segcache[0] != classes:
            segs = [np.hstack([pl[:-1], pl[1:]]) for (num, cls), pls in self.lines.items() if cls in classes
                    for pl in pls]
            self._segcache = (classes, np.vstack(segs) if segs else np.zeros((0, 4)))
        return self._segcache[1]

    def span_at_y(self, y, tol=0.5):
        """Left and right extent (paper x) of the line work in the band y +/- tol."""
        s = self._segments()
        yy = y - self.oy
        m = (np.minimum(s[:, 1], s[:, 3]) <= yy + tol) & (np.maximum(s[:, 1], s[:, 3]) >= yy - tol)
        if not m.any():
            return None
        return self.ox + min(s[m, 0].min(), s[m, 2].min()), self.ox + max(s[m, 0].max(), s[m, 2].max())

    def span_at_x(self, x, tol=0.5):
        s = self._segments()
        xx = x - self.ox
        m = (np.minimum(s[:, 0], s[:, 2]) <= xx + tol) & (np.maximum(s[:, 0], s[:, 2]) >= xx - tol)
        if not m.any():
            return None
        return self.oy + min(s[m, 1].min(), s[m, 3].min()), self.oy + max(s[m, 1].max(), s[m, 3].max())


def scale_text(k):
    if k >= 1:
        return f"{fmt(k)}:1"
    return f"1:{fmt(1 / k)}"


def _cast_hit(bvh, O, dv):
    rc = bvh.ray_cast
    return np.fromiter((rc(o, dv)[0] is not None for o in O.tolist()), bool, len(O))


def _cast_dist(bvh, O, dv, far=1e7):
    rc = bvh.ray_cast
    return np.fromiter((x if x is not None else far for x in (rc(o, dv)[3] for o in O.tolist())), float, len(O))


def project(scn, view, draw=None, occl=None, hidden=None, outline_only=None, gap=None, step=0.3, tiny=0.35,
            small=2.2, window=None, key=None, lift=0.05, exclude=None):
    """Hidden-line-removed line work of a scene in a view.

    draw, occl, hidden, outline_only: boolean arrays over scn.parts (parts to draw; parts that hide;
    parts whose hidden edges are wanted; parts drawn by their contours only).
    gap: depth step in model mm behind an edge that makes it an outline. step: sample spacing on paper.
    tiny, small: islands smaller than this on paper are dropped / drawn by contour only.
    window: ("rect", a0, b0, a1, b1) or ("circle", a, b, radius) in view coordinates, to crop a detail.
    Returns (segments (n,4) in view coordinates, part index (n,), state (n,): 0 hidden, 1 detail, 2 outline).
    """
    r, u, d, k = view.r, view.u, view.d, view.k
    npart = len(scn.parts)
    draw = np.ones(npart, bool) if draw is None else draw
    hidden = np.zeros(npart, bool) if hidden is None else hidden
    outline_only = np.zeros(npart, bool) if outline_only is None else outline_only
    gap = 2.6 / k if gap is None else gap
    bvh = scn.bvh(d, occl, key)
    a, b = scn.V @ r, scn.V @ u
    E, ep = scn.E, scn.EP
    two = scn.NF == 2
    fr1 = (scn.N1 @ d) > 1e-5
    fr2 = (scn.N2 @ d) > 1e-5
    contour = (two & (fr1 != fr2)) | (scn.NF == 1) | (scn.NF > 2)
    crease = scn.sharp & fr1 & fr2
    cand = draw[ep] & (contour | (crease & ~outline_only[ep]) | (scn.sharp & hidden[ep]))
    # islands too small to read at this scale
    lo_a = np.full(scn.nisl, 1e9)
    hi_a = np.full(scn.nisl, -1e9)
    lo_b, hi_b = lo_a.copy(), hi_a.copy()
    np.minimum.at(lo_a, scn.VI, a)
    np.maximum.at(hi_a, scn.VI, a)
    np.minimum.at(lo_b, scn.VI, b)
    np.maximum.at(hi_b, scn.VI, b)
    size = np.maximum(hi_a - lo_a, hi_b - lo_b) * k
    ei = scn.VI[E[:, 0]]
    cand &= size[ei] >= tiny
    cand &= contour | (size[ei] >= small) | hidden[ep]
    a0, b0, a1, b1 = a[E[:, 0]], b[E[:, 0]], a[E[:, 1]], b[E[:, 1]]
    ln = np.hypot(a1 - a0, b1 - b0)
    cand &= ln * k > 1e-4
    if exclude is not None:
        cand &= ~exclude
    t0 = np.zeros(len(E))
    t1 = np.ones(len(E))
    if window is not None:
        da, db = a1 - a0, b1 - b0
        with np.errstate(divide="ignore", invalid="ignore"):
            if window[0] == "rect":
                for p, q in ((-da, a0 - window[1]), (da, window[3] - a0), (-db, b0 - window[2]), (db, window[4] - b0)):
                    tt = q / p
                    t0 = np.where(p < 0, np.maximum(t0, tt), t0)
                    t1 = np.where(p > 0, np.minimum(t1, tt), t1)
                    cand &= ~((p == 0) & (q < 0))
            else:
                fa, fb = a0 - window[1], b0 - window[2]
                qa = da * da + db * db
                qb = 2 * (fa * da + fb * db)
                qc = fa * fa + fb * fb - window[3] ** 2
                disc = qb * qb - 4 * qa * qc
                sq = np.sqrt(np.maximum(disc, 0))
                t0 = np.maximum(t0, (-qb - sq) / (2 * qa))
                t1 = np.minimum(t1, (-qb + sq) / (2 * qa))
                cand &= disc > 0
        cand &= t1 - t0 > 1e-6
    idx = np.nonzero(cand)[0]
    if len(idx) == 0:
        return np.zeros((0, 4)), np.zeros(0, np.int32), np.zeros(0, np.int8)
    A, B = scn.V[E[idx, 0]], scn.V[E[idx, 1]]
    AB = B - A
    t0, t1 = t0[idx], t1[idx]
    n = np.clip(np.ceil(ln[idx] * (t1 - t0) * k / step), 1, 600).astype(int)
    S = int(n.sum())
    start = np.cumsum(n) - n
    se = np.repeat(np.arange(len(idx)), n)                       # sample -> candidate
    j = np.arange(S) - start[se]
    ts = t0[se] + (j + 0.5) / n[se] * (t1 - t0)[se]
    dv = tuple(d)
    up = d * lift

    def origin(t, e):
        return A[e] + AB[e] * t[:, None] + up

    vis = ~_cast_hit(bvh, origin(ts, se), dv)
    state = vis.astype(np.int8)
    # depth step behind visible contour samples
    con = contour[idx][se] & vis
    ci = np.nonzero(con)[0]
    if len(ci):
        e2 = np.stack([(a1 - a0)[idx], (b1 - b0)[idx]], 1) / ln[idx][:, None]
        perp = (-e2[:, 1])[:, None] * r + e2[:, 0][:, None] * u
        base = A[se[ci]] + AB[se[ci]] * ts[ci][:, None] + d * 0.5
        side = perp[se[ci]] * 0.1
        nd = tuple(-d)
        g = np.maximum(_cast_dist(bvh, base + side, nd), _cast_dist(bvh, base - side, nd)) - 0.5
        state[ci[g > gap]] = 2
    # boundaries between samples of one edge
    same = se[1:] == se[:-1]
    tb = (ts[1:] + ts[:-1]) / 2
    flip = np.nonzero(same & (vis[1:] != vis[:-1]))[0]
    if len(flip):
        lo, hi = ts[flip].copy(), ts[flip + 1].copy()
        vlo = vis[flip]
        for _ in range(4):
            mid = (lo + hi) / 2
            vm = ~_cast_hit(bvh, origin(mid, se[flip]), dv)
            eq = vm == vlo
            lo = np.where(eq, mid, lo)
            hi = np.where(eq, hi, mid)
        tb[flip] = (lo + hi) / 2
    brk = np.ones(S, bool)
    brk[1:] = ~same | (state[1:] != state[:-1])
    i0 = np.nonzero(brk)[0]
    i1 = np.append(i0[1:] - 1, S - 1)
    e = se[i0]
    first = np.ones(len(i0), bool)
    first[1:] = se[i0[1:] - 1] != e[1:]
    last = np.ones(len(i0), bool)
    last[:-1] = se[i1[:-1] + 1] != e[:-1]
    ta = np.where(first, t0[e], tb[np.maximum(i0 - 1, 0)])
    tz = np.where(last, t1[e], tb[np.minimum(i1, S - 2)] if S > 1 else t1[e])
    st = state[i0]
    pe = ep[idx][e]
    keep = (st > 0) | hidden[pe]
    # a hidden crease on the far side of its own part is noise unless asked for; a visible one never is
    a0, b0, a1, b1 = a0[idx][e], b0[idx][e], a1[idx][e], b1[idx][e]
    seg = np.stack([a0 + (a1 - a0) * ta, b0 + (b1 - b0) * ta, a0 + (a1 - a0) * tz, b0 + (b1 - b0) * tz], 1)
    return seg[keep], pe[keep], st[keep]


# ── chaining and simplification ──────────────────────────────────────────────
def _rdp(pl, tol):
    if len(pl) < 3:
        return pl
    keep = np.zeros(len(pl), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pl) - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        p, q = pl[i], pl[j]
        v = q - p
        L = math.hypot(v[0], v[1])
        w = pl[i + 1:j] - p
        dist = np.abs(w[:, 0] * v[1] - w[:, 1] * v[0]) / L if L > 1e-9 else np.hypot(w[:, 0], w[:, 1])
        m = int(dist.argmax())
        if dist[m] > tol:
            keep[i + 1 + m] = True
            stack += [(i, i + 1 + m), (i + 1 + m, j)]
    return pl[keep]


def chain(segs, tol=0.012, min_len=0.12, grid=0.004):
    """Join segments (n,4) that share end points into polylines, simplify, drop the tiny ones."""
    if len(segs) == 0:
        return []
    q = np.round(segs / grid).astype(np.int64)
    ka = (q[:, 0] << 32) ^ (q[:, 1] & 0xFFFFFFFF)
    kb = (q[:, 2] << 32) ^ (q[:, 3] & 0xFFFFFFFF)
    live = ka != kb
    ends = {}
    for i in np.nonzero(live)[0].tolist():
        ends.setdefault(int(ka[i]), []).append(i)
        ends.setdefault(int(kb[i]), []).append(i)
    ka, kb = ka.tolist(), kb.tolist()
    used = np.zeros(len(segs), bool)
    used[~live] = True
    out = []

    def walk(i, key):
        """Follow from segment i out of node key while the path is unambiguous."""
        pts = []
        while True:
            lst = ends[key]
            if len(lst) != 2:
                break
            nxt = lst[0] if lst[1] == i else lst[1]
            if used[nxt] or nxt == i:
                break
            used[nxt] = True
            if ka[nxt] == key:
                pts.append(segs[nxt, 2:4])
                key = kb[nxt]
            else:
                pts.append(segs[nxt, 0:2])
                key = ka[nxt]
            i = nxt
        return pts

    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        fwd = walk(i, kb[i])
        back = walk(i, ka[i])
        pl = np.array(back[::-1] + [segs[i, 0:2], segs[i, 2:4]] + fwd)
        pl = _rdp(pl, tol)
        if np.hypot(*(pl[1:] - pl[:-1]).T).sum() >= min_len:
            out.append(pl)
    return out


def path_d(pls, ox, oy):
    """Compact path data: absolute move, relative lines, hundredths of a millimetre."""
    out = []
    for pl in pls:
        q = np.round((pl + (ox, oy)) * 100).astype(int)
        dq = q[1:] - q[:-1]
        keep = np.any(dq != 0, 1)
        if not keep.any():
            continue
        out.append("M" + _n(q[0, 0]) + " " + _n(q[0, 1]) + "l" + " ".join(
            _n(x) + " " + _n(y) for x, y in dq[keep].tolist()))
    return "".join(out)


def _n(i):
    """Integer hundredths as the shortest decimal."""
    s = "-" if i < 0 else ""
    i = abs(int(i))
    w, f = divmod(i, 100)
    if f == 0:
        return f"{s}{w}"
    fs = f"{f:02d}".rstrip("0")
    return f"{s}{w if w else ''}.{fs}"


# ── the sheet ────────────────────────────────────────────────────────────────
class Sheet:
    def __init__(self, n, scale):
        self.n, self.title, self.scale = n, TITLES[n], scale
        self.number = f"RJ28-GA-{n:03d}"
        self.views, self.under, self.ann = [], [], []
        self.index = {}             # part number or assembly id -> list of dicts for sheets.json
        self.stats = {}

    # primitives, all in paper mm
    def line(self, x1, y1, x2, y2, cls="dim", to=None):
        (self.ann if to is None else to).append(f'<path class="{cls}" d="M{x1:.2f} {y1:.2f}L{x2:.2f} {y2:.2f}"/>')

    def poly(self, pts, cls="dim", close=False, to=None):
        d = "M" + "L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + ("Z" if close else "")
        (self.ann if to is None else to).append(f'<path class="{cls}" d="{d}"/>')

    def circle(self, x, y, r, cls="dim", to=None):
        (self.ann if to is None else to).append(f'<circle class="{cls}" cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}"/>')

    def arc(self, cx, cy, r, a0, a1, cls="dim"):
        """Arc from angle a0 to a1 (degrees, anticlockwise on paper, 0 = paper-right)."""
        x0, y0 = cx + r * math.cos(math.radians(a0)), cy - r * math.sin(math.radians(a0))
        x1, y1 = cx + r * math.cos(math.radians(a1)), cy - r * math.sin(math.radians(a1))
        large = 1 if abs(a1 - a0) > 180 else 0
        sweep = 0 if a1 > a0 else 1
        self.ann.append(f'<path class="{cls}" d="M{x0:.2f} {y0:.2f}A{r:.2f} {r:.2f} 0 {large} {sweep} {x1:.2f} {y1:.2f}"/>')

    def text(self, x, y, s, cls="tn", size=2.5, anchor="start", rot=0.0, to=None, mask=False):
        tr = f' transform="rotate({-rot:.2f} {x:.2f} {y:.2f})"' if rot else ""
        an = "" if anchor == "start" else f' text-anchor="{anchor}"'
        if mask:                                         # paper under text that has to sit on line work
            w = len(str(s)) * (MONO_ADV if cls in ("tn", "tm") else SANS_ADV * 1.1) * size + 1.0
            x0 = x - {"start": 0.5, "middle": w / 2, "end": w - 0.5}[anchor]
            (self.ann if to is None else to).append(
                f'<rect class="mask" x="{x0:.2f}" y="{y - size * 0.88:.2f}" width="{w:.2f}" height="{size * 1.16:.2f}"{tr}/>')
        (self.ann if to is None else to).append(
            f'<text class="{cls}" x="{x:.2f}" y="{y:.2f}" font-size="{size}"{an}{tr}>{esc(s)}</text>')

    def arrow(self, x, y, ang, L=2.8, w=0.48):
        """Filled slim arrowhead with its tip at (x, y), pointing along ang (degrees, paper anticlockwise)."""
        c, s = math.cos(math.radians(ang)), -math.sin(math.radians(ang))
        bx, by = x - c * L, y - s * L
        self.ann.append(f'<path class="ink" d="M{x:.2f} {y:.2f}L{bx - s * w:.2f} {by + c * w:.2f}'
                        f'L{bx + s * w:.2f} {by - c * w:.2f}Z"/>')

    def dot(self, x, y, r=0.45):
        self.ann.append(f'<circle class="ink" cx="{x:.2f}" cy="{y:.2f}" r="{r}"/>')

    # dimensions
    def dim(self, p1, p2, at, text, axis="h", gap=1.2, over=1.6, size=3.0, side=None, ext=True):
        """Linear dimension between feature points p1 and p2, measured along paper x (axis "h") or y ("v"),
        with the dimension line at paper y = at ("h") or x = at ("v"). Text sits above the line."""
        (x1, y1), (x2, y2) = p1, p2
        if axis == "h":
            if x1 > x2:
                (x1, y1), (x2, y2) = (x2, y2), (x1, y1)
            if ext:
                for x, y in ((x1, y1), (x2, y2)):
                    sg = 1 if at > y else -1
                    if abs(at - y) > gap:
                        self.line(x, y + sg * gap, x, at + sg * over)
            L = x2 - x1
            tw = len(text) * MONO_ADV * size
            inside = L > tw + 7.5
            if L > 6.5:
                self.line(x1, at, x2, at)
                self.arrow(x1, at, 180)
                self.arrow(x2, at, 0)
            else:
                self.line(x1 - 5, at, x2 + 5, at)
                self.arrow(x1, at, 0)
                self.arrow(x2, at, 180)
            if inside:
                self.text((x1 + x2) / 2, at - 0.9, text, "tn", size, "middle")
            else:
                if side == "left":
                    self.line(x1 - 5, at, x1 - 6 - tw, at)
                    self.text(x1 - 6, at - 0.9, text, "tn", size, "end")
                else:
                    self.line(x2 + 5 if L <= 6.5 else x2, at, x2 + 6 + tw, at)
                    self.text(x2 + 6, at - 0.9, text, "tn", size, "start")
        else:
            if y1 > y2:
                (x1, y1), (x2, y2) = (x2, y2), (x1, y1)
            if ext:
                for x, y in ((x1, y1), (x2, y2)):
                    sg = 1 if at > x else -1
                    if abs(at - x) > gap:
                        self.line(x + sg * gap, y, at + sg * over, y)
            L = y2 - y1
            tw = len(text) * MONO_ADV * size
            inside = L > tw + 7.5
            if L > 6.5:
                self.line(at, y1, at, y2)
                self.arrow(at, y1, 90)
                self.arrow(at, y2, -90)
            else:
                self.line(at, y1 - 5, at, y2 + 5)
                self.arrow(at, y1, -90)
                self.arrow(at, y2, 90)
            if inside:
                self.text(at - 0.9, (y1 + y2) / 2, text, "tn", size, "middle", rot=90)
            else:
                if side == "below":
                    self.line(at, y2, at, y2 + 6 + tw)
                    self.text(at - 0.9, y2 + 6 + tw / 2, text, "tn", size, "middle", rot=90)
                else:
                    self.line(at, y1, at, y1 - 6 - tw)
                    self.text(at - 0.9, y1 - 6 - tw / 2, text, "tn", size, "middle", rot=90)

    def dim_aligned(self, p1, p2, off, text, gap=1.2, over=1.6, size=3.0, mask=False):
        """Dimension parallel to p1 -> p2, offset by off to the left of that direction (paper mm)."""
        p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
        e = (p2 - p1) / np.linalg.norm(p2 - p1)
        nrm = np.array([e[1], -e[0]])                    # left of travel on paper (y down)
        q1, q2 = p1 + nrm * off, p2 + nrm * off
        sg = 1 if off > 0 else -1
        if abs(off) > gap:
            for p, q in ((p1, q1), (p2, q2)):
                self.line(*(p + nrm * sg * gap), *(q + nrm * sg * over))
        ang = math.degrees(math.atan2(-e[1], e[0]))
        L = np.linalg.norm(q2 - q1)
        if L > 6.5:
            self.line(*q1, *q2)
            self.arrow(*q1, ang + 180)
            self.arrow(*q2, ang)
        else:
            self.line(*(q1 - e * 5), *(q2 + e * 5))
            self.arrow(*q1, ang)
            self.arrow(*q2, ang + 180)
        ta = ang
        if ta > 90 or ta <= -90:
            ta += 180 if ta <= -90 else -180
        up = np.array([-math.sin(math.radians(ta)), -math.cos(math.radians(ta))])    # paper "above" for the text
        tw = len(text) * MONO_ADV * size
        if L > tw + 7.5:
            m = (q1 + q2) / 2 + up * 0.9
            self.text(m[0], m[1], text, "tn", size, "middle", rot=ta, mask=mask)
        else:
            m = q2 + e * (6 + tw / 2) + up * 0.9
            self.line(*q2, *(q2 + e * (6 + tw)))
            self.text(m[0], m[1], text, "tn", size, "middle", rot=ta, mask=mask)

    def dim_angle(self, c, r, a0, a1, text, size=3.0, text_r=None, cls="dim", mask=False):
        """Angular dimension: arc about c from a0 to a1 (degrees, paper anticlockwise from paper-right)."""
        self.arc(c[0], c[1], r, a0, a1, cls)
        sg = 1 if a1 > a0 else -1
        lead = math.degrees(2.8 / r) * 0.5
        for a, s in ((a0, -sg), (a1, sg)):
            x, y = c[0] + r * math.cos(math.radians(a)), c[1] - r * math.sin(math.radians(a))
            self.arrow(x, y, a + s * 90 - s * lead)
        am = math.radians((a0 + a1) / 2)
        tr = (r + 1.4) if text_r is None else text_r
        rot = math.degrees(am) - 90
        if rot > 90 or rot < -90:
            rot += 180 if rot < -90 else -180
            tr += size * 0.7
        self.text(c[0] + tr * math.cos(am), c[1] - tr * math.sin(am), text, "tn", size, "middle", rot=rot, mask=mask)

    def leader(self, target, elbow, text, size=2.8, cls="tl", end="arrow", shelf=4.0, lines=None):
        """Leader from a note to a feature: arrow or dot at target, a shelf at elbow, text after it."""
        tx, ty = target
        ex, ey = elbow
        sg = 1 if ex >= tx else -1
        self.poly([(tx, ty), (ex, ey), (ex + sg * shelf, ey)])
        if end == "arrow":
            self.arrow(tx, ty, math.degrees(math.atan2(-(ty - ey), tx - ex)))
        else:
            self.dot(tx, ty)
        rows = [text] if lines is None else [text] + list(lines)
        for i, s in enumerate(rows):
            self.text(ex + sg * (shelf + 1.2), ey + size * 0.36 + i * size * 1.35, s, cls if i == 0 else "tl", size,
                      "start" if sg > 0 else "end")

    def balloon(self, target, at, item, part=None, assembly=None, view=None, r=4.6, size=3.2):
        tx, ty = target
        bx, by = at
        L = math.hypot(bx - tx, by - ty)
        ux, uy = (bx - tx) / L, (by - ty) / L
        key = part or assembly
        attr = f' data-part="{part}"' if part else f' data-assembly="{assembly}"'
        self.ann.append(f'<g class="bal"{attr} data-item="{esc(item)}">')
        self.line(tx, ty, bx - ux * r, by - uy * r, "dim")
        self.dot(tx, ty, 0.5)
        self.circle(bx, by, r, "rule")
        self.text(bx, by + size * 0.36, item, "tm", size, "middle")
        self.ann.append("</g>")
        self.index.setdefault(key, []).append(dict(v=view.id if view else "", x=round(bx, 1), y=round(by, 1),
                                                   w=round(2 * r, 1), h=round(2 * r, 1), b=1,
                                                   tx=round(tx, 1), ty=round(ty, 1)))

    def table(self, x, y, cols, rows, head=None, row_h=5.0, size=2.4, title=None, head_h=None):
        """cols: list of (width, align, css class). rows: list of lists of strings. Returns the bottom y."""
        w = sum(c[0] for c in cols)
        head_h = head_h or row_h
        if title:
            self.text(x, y - 1.8, title, "tt", 3.6)
        y1 = y
        if head:
            cx = x
            for (cw, al, _), h in zip(cols, head):
                self._cell(cx, y, cw, head_h, h, al, "tl", size * 0.86)
                cx += cw
            y1 = y + head_h
            self.line(x, y1, x + w, y1, "rule")
        for i, row in enumerate(rows):
            cx = x
            for (cw, al, cls), s in zip(cols, row):
                self._cell(cx, y1 + i * row_h, cw, row_h, s, al, cls, size)
                cx += cw
            if i:
                self.line(x, y1 + i * row_h, x + w, y1 + i * row_h, "fine")
        y2 = y1 + len(rows) * row_h
        self.poly([(x, y), (x + w, y), (x + w, y2), (x, y2)], "rule", close=True)
        cx = x
        for cw, _, _ in cols[:-1]:
            cx += cw
            self.line(cx, y, cx, y2, "fine")
        return y2

    def _cell(self, x, y, w, h, s, align, cls, size):
        by = y + h / 2 + size * 0.36
        if align == "r":
            self.text(x + w - 1.4, by, s, cls, size, "end")
        elif align == "c":
            self.text(x + w / 2, by, s, cls, size, "middle")
        else:
            self.text(x + 1.4, by, s, cls, size)

    def view_title(self, v, x, y, extra=None, anchor="middle", size=4.4):
        self.text(x, y, v.title, "tt", size, anchor)
        tw = len(v.title) * SANS_ADV * size * 1.08
        x0 = {"middle": x - tw / 2, "start": x, "end": x - tw}[anchor]
        self.line(x0, y + 1.4, x0 + tw, y + 1.4, "rule")
        self.text(x, y + 5.6, "SCALE " + v.scale_text, "tl", 3.0, anchor)
        if extra:
            self.text(x, y + 9.8, extra, "tl", 2.6, anchor)

    def note_block(self, x, y, title, lines, size=3.0, lead=1.5, cls="tl", width=None):
        self.text(x, y, title, "tt", 3.6)
        yy = y + 5.8
        for s in lines:
            for row in (wrap(s, width, size) if width else [s]):
                self.text(x, yy, row, cls, size)
                yy += size * lead
        return yy

    # centre lines
    def centre_line(self, v, p, axis, half, cross=None):
        """Chain line through a joint axis. Seen end-on it becomes a centre mark."""
        a2 = np.array([np.dot(axis, v.r), np.dot(axis, v.u)])
        x, y = v.P(p)
        L = np.linalg.norm(a2)
        if L < 0.35:
            h = (cross or half * 0.6) * v.k
            self.line(x - h, y, x + h, y, "ctr", self.under)
            self.line(x, y - h, x, y + h, "ctr", self.under)
        else:
            e = a2 / L * half * v.k
            self.line(x - e[0], y + e[1], x + e[0], y - e[1], "ctr", self.under)

    # assembly
    def add_view(self, v):
        self.views.append(v)
        return v

    def furniture(self):
        """Border, zone references, centring marks, title block, revision table."""
        o = []
        m, W, H = MARGIN, SHEET_W, SHEET_H
        self.poly([(m, m), (W - m, m), (W - m, H - m), (m, H - m)], "frame", True, o)
        self.poly([(m / 2, m / 2), (W - m / 2, m / 2), (W - m / 2, H - m / 2), (m / 2, H - m / 2)], "fine", True, o)
        ncol, nrow = 16, 12
        letters = "ABCDEFGHJKLM"
        for i in range(ncol):
            xa = m + (W - 2 * m) * i / ncol
            xb = m + (W - 2 * m) * (i + 0.5) / ncol
            for ya, yb, ty in ((m / 2, m, m - 1.4), (H - m, H - m / 2, H - m / 2 - 1.4)):
                if i:
                    self.line(xa, ya, xa, yb, "fine", o)
                self.text(xb, ty, str(i + 1), "tl", 2.6, "middle", to=o)
        for i in range(nrow):
            ya = m + (H - 2 * m) * i / nrow
            yb = m + (H - 2 * m) * (i + 0.5) / nrow
            for xa, xb2, tx in ((m / 2, m, m * 0.75), (W - m, W - m / 2, W - m * 0.25)):
                if i:
                    self.line(xa, ya, xb2, ya, "fine", o)
                self.text(tx, yb + 0.95, letters[i], "tl", 2.6, "middle", to=o)
        for x, y, dx, dy in ((W / 2, m, 0, 1), (W / 2, H - m, 0, -1), (m, H / 2, 1, 0), (W - m, H / 2, -1, 0)):
            self.line(x - dx * 5, y - dy * 5, x + dx * 4, y + dy * 4, "frame", o)
        # title block
        tw, x1, y1 = 190.0, W - m, H - m
        x0 = x1 - tw
        rows = [22.0, 11.0, 14.0, 11.0]
        y0 = y1 - sum(rows)
        self.poly([(x0, y1), (x0, y0), (x1, y0)], "frame", False, o)

        def cell(cx, cy, cw, ch, cap, val, cls="tl", size=3.2, right=True, top=False, dy=0.0):
            if right:
                self.line(cx + cw, cy, cx + cw, cy + ch, "rule", o)
            if top:
                self.line(cx, cy, cx + cw, cy, "rule", o)
            self.text(cx + 1.5, cy + 3.0, cap, "tl", 1.9, to=o)
            if val:
                self.text(cx + 1.5, cy + ch - 2.2 + dy, val, cls, size, to=o)

        ya = y0
        cell(x0, ya, 128, rows[0], "TITLE", "", right=True)
        self.text(x0 + 1.5, ya + 9.8, "RJ-28 INTERCEPTOR", "tl", 3.6, to=o)
        self.text(x0 + 1.5, ya + 19.0, self.title.upper(), "tt", 7.2, to=o)
        cell(x0 + 128, ya, 62, rows[0], "PROJECTION", "", right=False)
        self._projection_symbol(x0 + 128 + 31, ya + 11.5, o)
        self.text(x0 + 128 + 31, ya + 20.2, "THIRD ANGLE", "tl", 2.4, "middle", to=o)
        yb = ya + rows[0]
        cx = x0
        for cw, cap, val, cls in ((52, "DRAWN", DRAWN, "tl"), (34, "DATE", REVISIONS[-1][2], "tn"),
                                  (40, "SCALE", self.scale, "tm"), (30, "UNITS", "mm", "tm"), (34, "SIZE", "A1", "tm")):
            cell(cx, yb, cw, rows[1], cap, val, cls, 3.4 if cls != "tn" else 3.0, right=cx + cw < x1 - 0.1, top=True)
            cx += cw
        yc = yb + rows[1]
        cell(x0, yc, 96, rows[2], "DRAWING NUMBER", self.number, "tm", 6.4, top=True, dy=0.4)
        cell(x0 + 96, yc, 60, rows[2], "SHEET", f"SHEET {self.n} OF {len(TITLES)}", "tl", 4.2, top=True)
        cell(x0 + 156, yc, 34, rows[2], "REVISION", REVISIONS[-1][0], "tm", 6.4, right=False, top=True, dy=0.4)
        yd = yc + rows[2]
        self.line(x0, yd, x1, yd, "rule", o)
        self.text(x0 + 1.5, yd + 4.4, TOLERANCE, "tl", 2.5, to=o)
        self.text(x0 + 1.5, yd + 8.8, "ALL DIMENSIONS FROM THE MODEL AS MEASURED.", "tl", 2.5, to=o)
        # revision table, newest at the bottom, sitting on the title block
        rh = 4.6
        ry = y0 - rh * (len(REVISIONS) + 1)
        self.poly([(x0, y0), (x0, ry), (x1, ry)], "rule", False, o)
        cols = [(12, "REV"), (118, "DESCRIPTION"), (30, "DATE"), (30, "BY")]
        cx = x0
        for cw, cap in cols:
            self.text(cx + 1.5, ry + 3.2, cap, "tl", 2.0, to=o)
            if cx + cw < x1 - 0.1:
                self.line(cx + cw, ry, cx + cw, y0, "fine", o)
            cx += cw
        for i, (rev, desc, date) in enumerate(REVISIONS):
            yy = ry + rh * (i + 1)
            self.line(x0, yy, x1, yy, "fine", o)
            self.text(x0 + 6, yy + 3.3, rev, "tm", 2.5, "middle", to=o)
            self.text(x0 + 13.5, yy + 3.3, desc, "tl", 2.3, to=o)
            self.text(x0 + 131.5, yy + 3.3, date, "tn", 2.2, to=o)
            self.text(x0 + 161.5, yy + 3.3, DRAWN, "tl", 2.3, to=o)
        self.title_block = (x0, ry, x1, y1)
        return o

    def _projection_symbol(self, cx, cy, o):
        """Third angle: the end view of the truncated cone sits on the side it is seen from."""
        r1, r2, L = 4.2, 2.2, 11.0
        ex = cx - 11.0                                   # end view (circles) on the left
        self.circle(ex, cy, r1, "rule", o)
        self.circle(ex, cy, r2, "rule", o)
        self.line(ex - r1 - 1.6, cy, ex + r1 + 1.6, cy, "ctr", o)
        self.line(ex, cy - r1 - 1.6, ex, cy + r1 + 1.6, "ctr", o)
        x0 = cx + 1.0                                    # side view: small end towards the circles
        self.poly([(x0, cy - r2), (x0 + L, cy - r1), (x0 + L, cy + r1), (x0, cy + r2)], "rule", True, o)
        self.line(x0 - 1.6, cy, x0 + L + 1.6, cy, "ctr", o)

    def svg(self, fonts):
        o = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {fmt(SHEET_W)} {fmt(SHEET_H)}" '
             f'width="{fmt(SHEET_W)}mm" height="{fmt(SHEET_H)}mm" id="{self.number}" data-sheet="{self.n}">',
             f"<title>{self.number} {esc(self.title)}</title>",
             "<style>" + fonts + CSS.replace("\n", "") + "</style>",
             f'<rect class="paper" width="{fmt(SHEET_W)}" height="{fmt(SHEET_H)}"/>',
             '<g id="furniture">'] + self.furniture() + ["</g>", '<g id="centres">'] + self.under + ["</g>"]
        npath = npts = 0
        for v in self.views:
            o.append(f'<g id="{v.id}" class="view" data-view="{esc(v.title)}" data-scale="{v.scale_text}">')
            by_part = {}
            for (num, cls), pls in v.lines.items():
                by_part.setdefault(num, []).append((cls, pls))
            for num in sorted(by_part):
                o.append(f'<g data-part="{num}">' if num else "<g>")
                for cls, pls in sorted(by_part[num]):
                    d = path_d(pls, v.ox, v.oy)
                    if d:
                        o.append(f'<path class="{cls}" d="{d}"/>')
                        npath += 1
                        npts += sum(len(p) for p in pls)
                o.append("</g>")
            o.append("</g>")
        o += ['<g id="annotation">'] + self.ann + ["</g>", "</svg>"]
        self.stats = dict(paths=npath, points=npts)
        return "\n".join(o)

    def part_index(self):
        """Where each part and assembly is on the sheet: balloons first, then the box of its visible lines per view."""
        idx = {k: list(v) for k, v in self.index.items()}
        for v in self.views:
            boxes, asm = {}, {}
            for (num, cls), pls in v.lines.items():
                if not num or cls in ("pha", "hat"):
                    continue
                lo = np.min([pl.min(0) for pl in pls], 0)
                hi = np.max([pl.max(0) for pl in pls], 0)
                for store, key in ((boxes, num), (asm, num[5:7])):
                    if key in store:
                        store[key] = (np.minimum(store[key][0], lo), np.maximum(store[key][1], hi))
                    else:
                        store[key] = (lo, hi)
            for store in (boxes, asm):
                for key, (lo, hi) in store.items():
                    c, s = (lo + hi) / 2, hi - lo
                    idx.setdefault(key, []).append(dict(v=v.id, x=round(v.ox + c[0], 1), y=round(v.oy + c[1], 1),
                                                        w=round(s[0], 1), h=round(s[1], 1)))
        return idx


def wrap(s, width, size, adv=SANS_ADV):
    out, cur = [], ""
    for w in s.split():
        if cur and (len(cur) + 1 + len(w)) * adv * size > width:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return out + [cur] if cur else out


def font_css():
    def face(family, file, extra):
        b = base64.b64encode((FONTS / file).read_bytes()).decode()
        return f'@font-face{{font-family:"{family}";src:url(data:font/woff2;base64,{b}) format("woff2");{extra}}}'
    return (face("Archivo", "Archivo-Variable.woff2", "font-weight:100 900;font-stretch:62% 125%")
            + face("IBM Plex Mono", "IBMPlexMono-Regular.woff2", "font-weight:400")
            + face("IBM Plex Mono", "IBMPlexMono-Medium.woff2", "font-weight:500"))


# ── build context: model, data, scenes, cached line work ─────────────────────
class Ctx:
    def __init__(self, opts):
        self.opts = opts
        self.spec = json.loads((DATA / "spec.json").read_text(encoding="utf-8"))
        self.rows = json.loads((DATA / "parts.json").read_text(encoding="utf-8"))
        self.by_num = {r["number"]: r for r in self.rows}
        self.sweep = json.loads(SWEEP.read_text(encoding="utf-8")) if SWEEP.exists() else None
        self.joints = axes.joints()
        self.scenes = {}
        self.use_lines = "lines" in opts
        WORK.mkdir(parents=True, exist_ok=True)

    def objects(self, fn=None):
        obs = [o for o in parts.all_parts() if o.type == "MESH" and len(o.data.vertices) and not o.get("rj28_decal")
               and o["rj28_assembly"] != "17"]
        return [o for o in obs if fn is None or fn(o)]

    def check(self):
        """The drawings quote the JSON; say so loudly if it does not describe the model in the scene."""
        live = {o["rj28_number"]: o["rj28_name"] for o in parts.all_parts()}
        js = {r["number"]: r["name"] for r in self.rows}
        diff = [k for k in live if js.get(k) != live[k]]
        if diff or len(js) != len([o for o in parts.all_parts() if o.type == "MESH" and len(o.data.vertices)]):
            print(f"DRAWINGS WARN parts.json does not match the model: {len(js)} rows, {len(live)} parts, "
                  f"{len(diff)} names differ ({', '.join(diff[:5])})")
        poses.set_mount("stowed")
        lo, hi = C.bounds_mm(self.objects() + [o for o in parts.all_parts() if o.get("rj28_decal")])
        e = self.spec["envelope"]["stowed"]
        if abs(hi.z - e["height"]) > 0.6 or abs((hi.x - lo.x) - e["width"]) > 0.6:
            print(f"DRAWINGS WARN spec.json envelope {e['width']} x {e['height']} but the model measures "
                  f"{hi.x - lo.x:.1f} x {hi.z:.1f}")

    def scene(self, key, objs=None):
        if key not in self.scenes:
            t = time.time()
            self.scenes[key] = Scene([geo_from_object(o) for o in objs])
            s = self.scenes[key]
            print(f"DRAWINGS scene {key}: {len(s.parts)} parts, {len(s.E)} edges, {len(s.T)} triangles, "
                  f"{time.time() - t:.1f} s")
        return self.scenes[key]

    def lines(self, view, make, classes=None, name=None):
        """Line work for a view, from the cache when asked. make() -> (scene, seg, part idx, state).
        classes: function(Geo, state) -> css class or None."""
        f = WORK / f"{name or view.id}.npz"
        if self.use_lines and f.exists():
            z = np.load(f, allow_pickle=False)
            seg, nums, st = z["seg"], z["nums"], z["st"]
            meta = json.loads(str(z["meta"]))
        else:
            t = time.time()
            scn, seg, pi, st = make()
            numbers = np.array([g.number for g in scn.parts])
            nums = numbers[pi] if len(pi) else np.zeros(0, "U11")
            meta = {g.number: (g.asm, g.mat, g.group, g.zone) for g in scn.parts}
            np.savez_compressed(f, seg=seg, nums=nums, st=st, meta=json.dumps(meta))
            print(f"DRAWINGS view {name or view.id}: {len(seg)} runs, {time.time() - t:.1f} s")
        classes = classes or (lambda num, m, s: ("vis", "det")[2 - s] if s else "hid")
        order = np.lexsort((st, nums))
        seg, nums, st = seg[order] * view.k * np.array([1, -1, 1, -1]), nums[order], st[order]
        cut = np.nonzero((nums[1:] != nums[:-1]) | (st[1:] != st[:-1]))[0] + 1
        for i0, i1 in zip(np.append(0, cut), np.append(cut, len(seg))):
            if i1 <= i0:
                continue
            num = str(nums[i0])
            cls = classes(num, meta[num], int(st[i0]))
            if cls is None:
                continue
            fine = cls in ("det", "ctx", "hid")
            pls = chain(seg[i0:i1], min_len=0.25 if fine else 0.12)
            if pls:
                view.lines.setdefault((num, cls), []).extend(pls)
        view._segcache = None
        return view


# ── output ───────────────────────────────────────────────────────────────────
def edge_exe():
    for p in EDGE:
        if p.exists():
            return p
    return None


def _edge(args, timeout=180):
    exe = edge_exe()
    if exe is None:
        print("DRAWINGS WARN Microsoft Edge not found: no PNG or PDF")
        return False
    prof = WORK / "edge-profile"
    cmd = [str(exe), "--headless=new", "--disable-gpu", "--no-first-run", "--disable-extensions",
           f"--user-data-dir={prof}", "--hide-scrollbars"] + args
    try:
        subprocess.run(cmd, timeout=timeout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        print("DRAWINGS WARN Edge timed out")
        return False
    return True


def rasterise(svg_path, png_path, width=2400):
    h = round(width * SHEET_H / SHEET_W)
    html = WORK / (svg_path.stem + ".html")
    html.write_text(f'<!doctype html><html><body style="margin:0;background:#fff"><img src="{svg_path.as_uri()}" '
                    f'style="display:block;width:{width}px;height:{h}px"></body></html>', encoding="utf-8")
    png_path.parent.mkdir(parents=True, exist_ok=True)
    if png_path.exists():
        png_path.unlink()
    _edge([f"--screenshot={png_path}", f"--window-size={width},{h}", "--force-device-scale-factor=1",
           "--virtual-time-budget=8000", html.as_uri()])
    return png_path.exists()


def pdf_set(svgs, pdf_path):
    html = WORK / "set.html"
    pages = "".join(f'<img src="{p.as_uri()}">' for p in svgs)
    html.write_text(
        "<!doctype html><html><head><style>@page{size:" + f"{fmt(SHEET_W)}mm {fmt(SHEET_H)}mm" + ";margin:0}"
        "html,body{margin:0;padding:0}img{display:block;width:" + f"{fmt(SHEET_W)}mm;height:{fmt(SHEET_H)}mm" +
        ";page-break-after:always;break-after:page}img:last-child{page-break-after:auto;break-after:auto}"
        "</style></head><body>" + pages + "</body></html>", encoding="utf-8")
    if pdf_path.exists():
        pdf_path.unlink()
    _edge([f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer", "--virtual-time-budget=20000", html.as_uri()],
          timeout=400)
    return pdf_path.exists()


# ── shared pieces of the sheets ──────────────────────────────────────────────
ORTHO = {                                             # third angle, robot facing the viewer in "front"
    "front": (X, Z), "rear": (-X, Z), "left": (Y, Z), "right": (-Y, Z), "top": (X, Y),
}
HALF = [("hip", 150), ("knee", 135), ("ankle", 115), ("waist_yaw", 170), ("waist_pitch", 230), ("shoulder", 125),
        ("elbow", 105), ("forearm", 120), ("wrist", 60), ("neck", 85), ("mount_elevation", 150),
        ("mount_traverse", 150), ("tracker", 40)]
TITLE_X0 = SHEET_W - MARGIN - 190.0                   # left edge of the title block column


def bounds(objs):
    lo, hi = C.bounds_mm(objs)
    return np.array(lo), np.array(hi)


def joint_centres(sh, v, joints, groups=("leg", "waist", "arm", "neck", "mount"), scale=1.0, skip=(), only=None):
    seen = set()
    for j in joints:
        if j["group"] not in groups or any(j["name"].startswith(s) for s in skip):
            continue
        if only is not None and not any(j["name"].startswith(s) for s in only):
            continue
        half = next((h for n, h in HALF if j["name"].startswith(n)), 80) * scale
        o, ax = np.array(j["origin"]), np.array(j["axis"])
        a2 = (float(ax @ v.r), float(ax @ v.u))
        end_on = math.hypot(*a2) < 0.35
        ang = 0 if end_on else round(math.degrees(math.atan2(a2[1], a2[0])) % 180 / 3)
        key = (round(float(o @ v.r) / 4), round(float(o @ v.u) / 4), end_on, ang)
        if key in seen:
            continue
        seen.add(key)
        sh.centre_line(v, o, ax, half)


def std_classes(num, meta, state):
    return ("hid", "det", "vis")[state]


def clip_segs(seg, window):
    """Clip (n,4) segments to a window (see project)."""
    if len(seg) == 0 or window is None:
        return seg
    a0, b0, a1, b1 = seg.T
    da, db = a1 - a0, b1 - b0
    t0, t1, ok = np.zeros(len(seg)), np.ones(len(seg)), np.ones(len(seg), bool)
    with np.errstate(divide="ignore", invalid="ignore"):
        if window[0] == "rect":
            for p, q in ((-da, a0 - window[1]), (da, window[3] - a0), (-db, b0 - window[2]), (db, window[4] - b0)):
                tt = q / p
                t0 = np.where(p < 0, np.maximum(t0, tt), t0)
                t1 = np.where(p > 0, np.minimum(t1, tt), t1)
                ok &= ~((p == 0) & (q < 0))
        else:
            fa, fb = a0 - window[1], b0 - window[2]
            qa, qb, qc = da * da + db * db, 2 * (fa * da + fb * db), fa * fa + fb * fb - window[3] ** 2
            disc = qb * qb - 4 * qa * qc
            sq = np.sqrt(np.maximum(disc, 0))
            t0 = np.maximum(t0, (-qb - sq) / (2 * qa))
            t1 = np.minimum(t1, (-qb + sq) / (2 * qa))
            ok &= disc > 0
    ok &= t1 - t0 > 1e-6
    out = np.stack([a0 + da * t0, b0 + db * t0, a0 + da * t1, b0 + db * t1], 1)
    return out[ok]


def _depth(seg, out, px, py):
    """How many solids cover each point (px, py): seg (n,4) are cut edges, out (n,2) their outward normals."""
    x0, y0, x1, y1 = seg.T
    res = np.zeros(len(px), int)
    for i in range(len(px)):
        m = (y0 <= py[i]) != (y1 <= py[i])
        if not m.any():
            continue
        xc = x0[m] + (py[i] - y0[m]) / (y1[m] - y0[m]) * (x1[m] - x0[m])
        right = xc > px[i]
        res[i] = int(np.sum(np.where(out[m, 0][right] > 0, 1, -1)))
    return res


def cut_outline(seg, out, eps=0.02):
    """The cut edges that bound material against air: drops edges buried inside another shell of the part."""
    if len(seg) == 0:
        return seg
    mx, my = (seg[:, 0] + seg[:, 2]) / 2, (seg[:, 1] + seg[:, 3]) / 2
    return seg[_depth(seg, out, mx + out[:, 0] * eps, my + out[:, 1] * eps) <= 0]


def hatch_lines(seg, out, angle, spacing, phase=0.0):
    """Section lining: parallel lines at angle (degrees) wherever the cut covers material."""
    if len(seg) == 0:
        return np.zeros((0, 4))
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    x0, y0 = seg[:, 0] * c + seg[:, 1] * s, -seg[:, 0] * s + seg[:, 1] * c
    x1, y1 = seg[:, 2] * c + seg[:, 3] * s, -seg[:, 2] * s + seg[:, 3] * c
    ox = out[:, 0] * c + out[:, 1] * s
    res = []
    lo, hi = min(y0.min(), y1.min()), max(y0.max(), y1.max())
    for yk in np.arange(math.ceil((lo - phase) / spacing) * spacing + phase, hi, spacing):
        m = (y0 <= yk) != (y1 <= yk)
        if m.sum() < 2:
            continue
        xc = x0[m] + (yk - y0[m]) / (y1[m] - y0[m]) * (x1[m] - x0[m])
        step = np.where(ox[m] < 0, 1, -1)                    # crossing left to right: entering or leaving
        order = np.argsort(xc)
        xc, depth = xc[order], np.cumsum(step[order])
        start = None
        for x, dpt in zip(xc.tolist(), depth.tolist()):
            if dpt > 0 and start is None:
                start = x
            elif dpt <= 0 and start is not None:
                if x - start > 0.05:
                    res.append((start, yk, x, yk))
                start = None
    if not res:
        return np.zeros((0, 4))
    r = np.array(res)
    return np.stack([r[:, 0] * c - r[:, 1] * s, r[:, 0] * s + r[:, 1] * c,
                     r[:, 2] * c - r[:, 3] * s, r[:, 2] * s + r[:, 3] * c], 1)


HATCH = {"armour": 1.5, "cap": 1.3, "alu": 2.1, "ti": 1.7, "steel": 1.1, "cfrp": 0.9, "rubber": 0.8}


def _cross(p1, p2, p3, p4):
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])
    return ccw(p1, p2, p3) * ccw(p1, p2, p4) < 0 and ccw(p3, p4, p1) * ccw(p3, p4, p2) < 0


def place_balloons(sh, view, items, box, sides=("left", "right"), pitch=11.0, off=15.0, limits=None, stagger=0.0):
    """Balloons in columns or rows outside box = (x0, y0, x1, y1), leaders uncrossed.
    items: [(item text, part number or None, assembly or None, (tx, ty))]."""
    x0, y0, x1, y1 = box
    cols = {s: [] for s in sides}
    for it in items:
        tx, ty = it[3]
        dist = {"left": tx - x0, "right": x1 - tx, "top": ty - y0, "bottom": y1 - ty}
        cols[it[4] if len(it) > 4 else min(sides, key=lambda s: dist[s])].append(it)
    for side, lst in cols.items():
        if not lst:
            continue
        vert = side in ("left", "right")
        ax = 1 if vert else 0
        lst.sort(key=lambda it: it[3][ax])
        want = [it[3][ax] for it in lst]
        lo, hi = (y0, y1) if vert else (x0, x1)
        if limits and side in limits:
            lo, hi = limits[side]
        pos = list(want)
        for i in range(1, len(pos)):
            pos[i] = max(pos[i], pos[i - 1] + pitch)
        shift = (sum(want) - sum(pos)) / len(pos)
        pos = [p + shift for p in pos]
        if pos[-1] > hi:
            pos = [p - (pos[-1] - hi) for p in pos]
        if pos[0] < lo:
            pos = [p + (lo - pos[0]) for p in pos]
        fixed = {"left": x0 - off, "right": x1 + off, "top": y0 - off, "bottom": y1 + off}[side]
        sgn = -1 if side in ("left", "top") else 1
        at = []
        for i, p in enumerate(pos):
            f = fixed + sgn * (stagger if i % 2 else 0.0)
            at.append((f, p) if vert else (p, f))
        for _ in range(40):                                  # swap slots until no two leaders cross
            swapped = False
            for i in range(len(lst)):
                for j in range(i + 1, len(lst)):
                    if _cross(lst[i][3], at[i], lst[j][3], at[j]):
                        lst[i], lst[j] = lst[j], lst[i]
                        swapped = True
            if not swapped:
                break
        for it, p in zip(lst, at):
            sh.balloon(it[3], p, it[0], part=it[1], assembly=it[2], view=view)


def break_line(sh, x0, y0, x1, y1, to=None):
    """Long break line: thin, with a zigzag in the middle."""
    L = math.hypot(x1 - x0, y1 - y0)
    ex, ey = (x1 - x0) / L, (y1 - y0) / L
    nx, ny = -ey, ex
    pts = [(x0, y0)]
    for f in (0.3, 0.7):
        cx, cy = x0 + ex * L * f, y0 + ey * L * f
        pts += [(cx - ex * 1.6, cy - ey * 1.6), (cx - ex * 0.8 + nx * 2.2, cy - ey * 0.8 + ny * 2.2),
                (cx + ex * 0.8 - nx * 2.2, cy + ey * 0.8 - ny * 2.2), (cx + ex * 1.6, cy + ey * 1.6)]
    pts.append((x1, y1))
    sh.poly(pts, "fine", to=to)


def section_arrows(sh, x, y0, y1, letter, direction=-1, size=4.2):
    """Cutting plane on a vertical line at paper x from y0 to y1; arrows show the viewing direction."""
    sh.line(x, y0, x, y1, "brk")
    for y in (y0, y1):
        sgn = -1 if y == y0 else 1
        sh.line(x, y, x, y - sgn * 7, "cut")
        sh.line(x, y, x + direction * 9, y, "rule")
        sh.arrow(x + direction * 9, y, 180 if direction < 0 else 0, L=3.6, w=0.75)
        sh.text(x + direction * 12.5, y + size * 0.36, letter, "tt", size, "middle")


def level_mark(sh, x, y, text, side=1, size=2.8):
    """Datum triangle on a level with its height above ground."""
    sh.poly([(x, y), (x - 1.5, y - 2.6), (x + 1.5, y - 2.6)], "rule", close=True)
    sh.line(x - 2.5 if side > 0 else x + 2.5, y, x + side * 4.5, y, "dim")
    sh.text(x + side * 3.0, y - 3.4, text, "tl", size, "start" if side > 0 else "end")


def flag(sh, x, y, n, size=2.6):
    r = 3.2
    pts = [(x + r * math.cos(math.radians(a)), y - r * math.sin(math.radians(a))) for a in (90, 210, 330)]
    sh.ann.append('<path class="mask" d="M' + "L".join(f"{px:.2f} {py:.2f}" for px, py in pts) + 'Z"/>')
    sh.poly(pts, "rule", close=True)
    sh.text(x, y + 1.25, str(n), "tm", size, "middle")


# ── sheet 1: general arrangement ─────────────────────────────────────────────
def sheet1(ctx):
    spec = ctx.spec
    k = 1 / 5
    sh = Sheet(1, scale_text(k))
    poses.set_mount("stowed")
    env, dep, lm = spec["envelope"]["stowed"], spec["envelope"]["deployed"], spec["landmarks"]
    lo, hi = env["min"], env["max"]

    def make(v):
        def run():
            scn = ctx.scene("stowed", ctx.objects())
            harness = scn.mask(lambda g: g.asm == "16" or g.mat == "braid")
            return (scn,) + project(scn, v, outline_only=harness)
        return run

    floor = SHEET_H - MARGIN - 23.0
    xf = MARGIN + 54.0 - lo[0] * k                     # front view: model x = 0
    vf = sh.add_view(View("s1-front", "FRONT VIEW", *ORTHO["front"], k)).place(xf, floor)
    xs = xf + hi[0] * k + 52.0 - lo[1] * k             # left-hand side: model y = 0
    vs = sh.add_view(View("s1-left", "LEFT-HAND SIDE VIEW", *ORTHO["left"], k)).place(xs, floor)
    xr = xs + hi[1] * k + 36.0 + hi[0] * k
    vr = sh.add_view(View("s1-rear", "REAR VIEW", *ORTHO["rear"], k)).place(xr, floor)
    ty = floor - hi[2] * k - 11.0                      # paper y of the front edge of the plan
    vt = sh.add_view(View("s1-top", "TOP VIEW", *ORTHO["top"], k)).place(xf, ty + lo[1] * k)
    for v in (vf, vs, vr):
        ctx.lines(v, make(v), std_classes)
        joint_centres(sh, v, ctx.joints, skip=("tracker",))
    ctx.lines(vt, make(vt), std_classes)
    joint_centres(sh, vt, ctx.joints, skip=("tracker", "knee", "ankle", "hip_pitch", "hip_roll", "elbow", "wrist",
                                            "forearm", "waist_pitch", "neck_pitch", "neck_roll", "shoulder_yaw"))
    # ground line
    for v, a0, a1 in ((vf, lo[0], hi[0]), (vs, lo[1], hi[1]), (vr, -hi[0], -lo[0])):
        sh.line(v.pt(a0 - 40, 0)[0], floor, v.pt(a1 + 40, 0)[0], floor, "fine", sh.under)
    # centre plane
    crown = spec["height_to_cap_crown"]
    for x in (xf, xr):
        sh.line(x, floor + 3, x, floor - crown * k - 7, "ctr", sh.under)
    sh.line(xf, vt.pt(0, lo[1] - 25)[1], xf, vt.pt(0, hi[1] + 20)[1], "ctr", sh.under)
    # landmark heights, stacked from the floor on the mount side of the front view
    marks = [("ANKLE AXIS", lm["ankle_axis"]), ("KNEE AXIS", lm["knee_axis"]), ("HIP AXIS", lm["hip_axis"]),
             ("WAIST JOINT", lm["waist_joint"]), ("SHOULDER AXIS", lm["shoulder_axis"]),
             ("SENSOR SLIT", lm["sensor_slit"])]
    xl = vf.pt(lo[0], 0)[0]
    for i, (name, z) in enumerate(marks):
        y = floor - z * k
        span = vf.span_at_y(y)
        x_out = min(span[0] if span else xl, xl + 30)
        at = xl - 9.0 - i * 6.4
        sh.dim((x_out, y), (xl, floor), at, fmt(z), "v")
        sh.text(at + 2.0, y - 1.0, name, "tl", 2.6)
    sh.line(xl - 1.2, floor, xl - 9.0 - (len(marks) - 1) * 6.4 - 1.6, floor)
    # overall heights between the front and side views
    xo = vf.pt(hi[0], 0)[0]
    for i, (name, z) in enumerate((("CAP CROWN", crown), ("MOUNT STOWED", env["height"]))):
        y = floor - z * k
        sp = vf.span_at_y(y + 0.3)
        at = xo + 9.0 + i * 7.0
        sh.dim(((sp[1] if sp else xf), y), (xo, floor), at, fmt(z), "v")
        sh.text(at - 2.0, y - 1.0, name, "tl", 2.6, "end")
    sh.line(xo + 1.2, floor, xo + 17.6, floor)
    # overall width, depth, stance
    sh.dim(vf.pt(lo[0], 0), vf.pt(hi[0], 0), floor + 8.0, fmt(env["width"]), "h")
    sh.dim(vs.pt(lo[1], 0), vs.pt(hi[1], 0), floor + 8.0, fmt(env["depth"]), "h")
    st = lm["stance_width"]
    sh.dim(vr.pt(-st / 2, 0), vr.pt(st / 2, 0), floor + 8.0, fmt(st), "h")
    for v, x in ((vf, xf), (vs, (vs.pt(lo[1], 0)[0] + vs.pt(hi[1], 0)[0]) / 2), (vr, xr)):
        sh.view_title(v, x, floor + 14.4, size=4.0)
    bt = vt.bbox()
    sh.view_title(vt, bt[2] + 12, (bt[1] + bt[3]) / 2, anchor="start", size=4.0)
    # data column
    m = spec["mass"]
    x0 = TITLE_X0
    rows = [
        ("DESIGNATION", spec["designation"]), ("CLASS", spec["klass"].upper()), ("SERIAL", spec["serial"]),
        ("HEIGHT TO CAP CROWN", fmt(crown)), ("HEIGHT, MOUNT STOWED", fmt(env["height"])),
        ("HEIGHT, MOUNT DEPLOYED", fmt(dep["height"])), ("WIDTH OVER FOREARMS", fmt(env["width"])),
        ("DEPTH, MOUNT STOWED", fmt(env["depth"])), ("DEPTH, MOUNT DEPLOYED", fmt(dep["depth"])),
        ("SHOULDER ARMOUR SPAN", fmt(spec["shoulder_armour_span"])), ("SHOULDER AXIS SPAN", fmt(lm["shoulder_axis_span"])),
        ("HIP AXIS SPAN", fmt(lm["hip_axis_span"])), ("STANCE WIDTH, ANKLE CENTRES", fmt(st)),
        ("MASS, READY", f"{m['total_kg']:.1f} kg"), ("DEGREES OF FREEDOM", str(spec["dof"]["total"])),
        ("PARTS", f"{spec['part_count']} IN {len(m['by_assembly'])} ASSEMBLIES"),
        ("POWER", spec["targets"]["power"].upper().replace("KWH", "kWh")),
    ]
    yb = sh.table(x0, 26.0, [(66, "l", "tl"), (124, "l", "tn")], rows, row_h=5.6, size=2.8, title="PRINCIPAL DATA")
    yb = sh.table(x0, yb + 14.0, [(16, "c", "tm"), (36, "l", "tn"), (138, "l", "tl")],
                  [[str(n), f"RJ28-GA-{n:03d}", TITLES[n].upper()] for n in sorted(TITLES)],
                  head=["SHEET", "DRAWING NUMBER", "TITLE"], row_h=5.6, size=2.8, title="DRAWING LIST")
    jl = {j["name"]: j for j in ctx.joints}
    sh.note_block(x0, yb + 12.0, "NOTES", [
        "1.  ALL DIMENSIONS IN MILLIMETRES, MEASURED FROM THE MODEL.",
        "2.  SHOWN IN THE NEUTRAL STANCE WITH THE MOUNT STOWED, BARREL VERTICAL.",
        f"     ELEVATION {fmt(spec['mount']['elevation'][0])}° TO {fmt(spec['mount']['elevation'][1])}°, "
        f"TRAVERSE ±{fmt(spec['mount']['traverse'])}°. SEE SHEET 3.",
        "3.  HEIGHTS ARE ABOVE GROUND LEVEL TO THE JOINT AXES NAMED.",
        "4.  CHAIN LINES MARK JOINT AXES. HAND AXES ARE NOT SHOWN AT THIS SCALE.",
        f"5.  KNEE FLEXION RANGE {fmt(jl['knee_pitch_L']['range'][0])}° TO {fmt(jl['knee_pitch_L']['range'][1])}°. "
        "SEE SHEET 4.",
        "6.  MARKINGS (ASSEMBLY 17) AND HARNESS DETAIL ARE OMITTED FOR CLARITY.",
    ], size=2.9, lead=1.6)
    return sh


# ── sheet 2: head and cap ────────────────────────────────────────────────────
HEAD_ITEMS = [                                        # (part name, assembly, preferred view)
    ("Cap Crown", "01", "sec"), ("Cap Button", "01", "sec"), ("Cap Carrier", "01", "sec"),
    ("Cap Base Flange", "01", "sec"), ("Cap Brim", "01", "sec"), ("Brim Flange", "01", "sec"),
    ("Cap Arch Mesh", "01", "front"), ("Cap Strap Band", "01", "front"), ("Cap Strap Latch", "01", "front"),
    ("Skull Frame", "01", "sec"), ("Skull Shell Front", "01", "left"), ("Skull Shell Jaw", "01", "left"),
    ("Skull Shell Rear", "01", "left"), ("Faceplate", "01", "sec"), ("Slit Bezel", "01", "front"),
    ("Slit Window", "01", "sec"), ("Camera Bracket", "01", "sec"), ("Lens Cluster Bezel", "01", "front"),
    ("Thermal Imager Lens", "01", "front"), ("Jaw Guard", "01", "front"), ("Processor Board", "01", "sec"),
    ("Heat Spreader", "01", "sec"), ("Rear Sensor Bar", "01", "rear"), ("Neck Yaw Outer Race", "02", "sec"),
    ("Neck Yaw Inner Race", "02", "sec"), ("Gimbal Base", "02", "sec"), ("Gimbal Cross", "02", "sec"),
    ("Gimbal Head Yoke", "02", "sec"), ("Neck Yaw Motor", "02", "rear"), ("Neck Left Act Body", "02", "rear"),
]


def sheet2(ctx):
    k = 0.5
    sh = Sheet(2, scale_text(k))
    poses.set_mount("stowed")
    objs = ctx.objects(lambda o: o["rj28_assembly"] in ("01", "02"))
    by_name = {(o["rj28_name"], o["rj28_assembly"]): o for o in objs}
    scn = ctx.scene("head", objs)
    lo, hi = bounds(objs)
    W, D, H = (hi - lo) * k
    base = 300.0
    gap = 31.0
    x = MARGIN + 30.0
    oy = base + lo[2] * k
    vR = sh.add_view(View("s2-right", "RIGHT-HAND SIDE VIEW", *ORTHO["right"], k)).place(x + hi[1] * k, oy)
    x += D + gap
    xF = x - lo[0] * k
    vF = sh.add_view(View("s2-front", "FRONT VIEW", *ORTHO["front"], k)).place(xF, oy)
    x += W + gap
    vL = sh.add_view(View("s2-left", "LEFT-HAND SIDE VIEW", *ORTHO["left"], k)).place(x - lo[1] * k, oy)
    x += D + gap
    vB = sh.add_view(View("s2-rear", "REAR VIEW", *ORTHO["rear"], k)).place(x + hi[0] * k, oy)
    top_front = base - H - 11.0
    vT = sh.add_view(View("s2-top", "TOP VIEW", *ORTHO["top"], k)).place(xF, top_front + lo[1] * k)
    harness = scn.mask(lambda g: g.mat == "braid")
    for v in (vR, vF, vL, vB, vT):
        ctx.lines(v, lambda v=v: (scn,) + project(scn, v, outline_only=harness, step=0.25), std_classes)
        joint_centres(sh, v, ctx.joints, groups=("neck",), scale=0.8)
    yt = base - H
    for v in (vF, vB):
        sh.line(v.ox, base + 3, v.ox, yt - 4, "ctr", sh.under)
    sh.line(xF, vT.pt(0, lo[1])[1] + 3, xF, vT.pt(0, hi[1])[1] - 3, "ctr", sh.under)

    # ── dimensions measured from the parts ──
    crown = bounds([by_name[("Cap Crown", "01")]])
    brim = bounds([by_name[("Cap Brim", "01")]])
    shell = bounds([o for o in objs if o["rj28_name"].startswith("Skull Shell")])
    button = bounds([by_name[("Cap Button", "01")]])
    zc = (crown[0][2] + crown[1][2]) / 2
    # right-hand side view: cap lengths in a chain with the overall depth above; heights on the left
    y1 = yt - 8.0
    pf, pr = vR.pt(-crown[0][1], zc - 18), vR.pt(-crown[1][1], zc - 8)
    pb = vR.pt(-brim[1][1], brim[1][2])
    sh.dim(pr, pf, y1, fmt(crown[1][1] - crown[0][1]), "h")
    sh.dim(pb, pr, y1, fmt(brim[1][1] - crown[1][1]), "h", side="left")
    sh.dim(pb, vR.pt(-lo[1], lo[2] + H / k * 0.45), y1 - 7.5, fmt(brim[1][1] - lo[1]), "h")
    xr0 = vR.pt(-hi[1], 0)[0]
    sh.dim((pb[0], vR.pt(0, crown[0][2])[1]), (vR.pt(-(crown[0][1] + crown[1][1]) / 2, 0)[0], vR.pt(0, crown[1][2])[1]),
           xr0 - 8.0, fmt(crown[1][2] - crown[0][2]), "v")
    sh.dim((vR.pt(-crown[1][1], 0)[0], base), (vR.pt(-(crown[0][1] + crown[1][1]) / 2, 0)[0], yt), xr0 - 15.5,
           fmt(hi[2] - lo[2]), "v")
    # front view: skull width; rear view: cap width above, brim width below
    sh.dim(vF.pt(shell[0][0], shell[0][2] + 30), vF.pt(shell[1][0], shell[0][2] + 30), base + 8.0,
           fmt(shell[1][0] - shell[0][0]), "h")
    sh.dim(vB.pt(-crown[1][0], zc - 20), vB.pt(-crown[0][0], zc - 20), y1, fmt(crown[1][0] - crown[0][0]), "h")
    sh.dim(vB.pt(-brim[1][0], brim[0][2]), vB.pt(-brim[0][0], brim[0][2]), base + 8.0, fmt(brim[1][0] - brim[0][0]), "h")
    # top view: overall cap length, button
    xt1 = vT.pt(hi[0], 0)[0]
    sh.dim((vT.pt(brim[1][0] * 0.5, 0)[0], vT.pt(0, brim[1][1])[1]), (vT.pt(crown[1][0] * 0.6, 0)[0], vT.pt(0, crown[0][1])[1]),
           xt1 + 9.0, fmt(brim[1][1] - crown[0][1]), "v")
    bt = vT.pt(button[0][0] + 5, (button[0][1] + button[1][1]) / 2 + 12)
    sh.leader(bt, (vT.pt(lo[0], 0)[0] - 12.0, bt[1] - 16.0), "Ø" + fmt(button[1][0] - button[0][0]) + " BUTTON", cls="tn")
    for v in (vR, vF, vL, vB):
        b = v.bbox()
        sh.view_title(v, (b[0] + b[2]) / 2, base + 15.0, size=4.0)
    sh.view_title(vT, vT.pt(lo[0], 0)[0] - 14.0, vT.pt(0, hi[1])[1] + 24.0, anchor="end", size=4.0)

    # ── section A-A on the centre plane, and the slit at 2:1 ──
    xc = 0.5                                             # half a millimetre off centre: no face lies in the cut
    cut_key = "head_cut"
    if cut_key not in ctx.scenes:
        geos, loops = [], {}
        for o in objs:
            g, segs = geo_cut(o, (xc, 0, 0), (1, 0, 0))
            if g is not None:
                geos.append(g)
                if segs is not None:
                    loops[g.number] = segs
        ctx.scenes[cut_key] = Scene(geos)
        ctx.scenes[cut_key].loops = loops
    cs = ctx.scenes[cut_key]
    on_cut = np.all(np.abs(cs.V[cs.E][:, :, 0] - xc) < 1e-4, axis=1)
    cs_h = cs.mask(lambda g: g.mat == "braid")
    slit = bounds([by_name[("Slit Window", "01")]])
    sc = ((slit[0][1] + slit[1][1]) / 2 + 14.0, (slit[0][2] + slit[1][2]) / 2 - 2.0)
    sr = 36.0
    vA = sh.add_view(View("s2-section", "SECTION A-A", *ORTHO["left"], 1.0))
    sec_base = SHEET_H - MARGIN - 17.0
    xA = MARGIN + 44.0
    vA.place(xA - lo[1], sec_base + lo[2])
    vD = sh.add_view(View("s2-detail", "DETAIL B", *ORTHO["left"], 2.0))
    dcx = xA + (hi[1] - lo[1]) + 132.0
    dcy = sec_base - sr * 2 - 24.0
    vD.place(dcx - sc[0] * 2.0, dcy + sc[1] * 2.0)
    win = ("circle", sc[0], sc[1], sr)
    flip = np.array([1, -1, 1, -1])
    for v, w in ((vA, None), (vD, win)):
        ctx.lines(v, lambda v=v, w=w: (cs,) + project(cs, v, outline_only=cs_h, exclude=on_cut, window=w,
                                                      step=0.25, small=1.6), std_classes)
        for g in cs.parts:
            segs = cs.loops.get(g.number)
            if segs is None:
                continue
            pts, nrm = segs
            s2 = np.stack([pts[:, 0] @ v.r, pts[:, 0] @ v.u, pts[:, 1] @ v.r, pts[:, 1] @ v.u], 1)
            o2 = np.stack([nrm @ v.r, nrm @ v.u], 1)
            ln = np.hypot(o2[:, 0], o2[:, 1])
            ok = ln > 1e-6
            pap = s2[ok] * v.k * flip
            op = o2[ok] / ln[ok][:, None] * np.array([1, -1])
            outl = cut_outline(pap, op)
            if w is not None:
                outl = clip_segs(outl * flip / v.k, w) * v.k * flip
            pls = chain(outl, min_len=0.1)
            if pls:
                v.lines.setdefault((g.number, "cut"), []).extend(pls)
            sp = HATCH.get(g.mat)
            size = max(np.ptp(pap[:, [0, 2]]), np.ptp(pap[:, [1, 3]])) if len(pap) else 0
            if sp and size > 3.0:
                n3 = int(g.number[-3:])
                h = hatch_lines(pap, op, 45 if n3 % 2 else 135, sp * (1.25 if v.k > 1 else 1.0), phase=(n3 % 3) * 0.4)
                if w is not None and len(h):
                    h = clip_segs(h * flip / v.k, w) * v.k * flip
                if len(h):
                    v.lines.setdefault((g.number, "hat"), []).extend([r.reshape(2, 2) for r in h])
        v._segcache = None
    joint_centres(sh, vA, ctx.joints, groups=("neck",), scale=0.55)
    # cutting plane on the front view, detail circle on the section
    section_arrows(sh, xF + xc * k, yt - 3.5, base + 3.5, "A", direction=-1)
    cxs, cys = vA.pt(*sc)
    sh.circle(cxs, cys, sr, "pha")
    sh.text(cxs + 2.0, cys + sr + 5.5, "B", "tt", 4.6, mask=True)
    sh.circle(dcx, dcy, sr * 2.0, "rule")
    bA = vA.bbox()
    sh.view_title(vA, bA[2] + 22.0, sec_base - 6.0, anchor="start", size=4.0,
                  extra="ON THE CENTRE PLANE, LOOKING TO THE RIGHT-HAND SIDE")
    sh.view_title(vD, dcx, dcy + sr * 2.0 + 9.0, size=4.0, extra="SENSOR SLIT")
    # slit window in the detail: measured along and across its own section, whose axes come from the mesh
    gw = scn.parts[scn.index[by_name[("Slit Window", "01")]["rj28_number"]]]
    yz = gw.V[:, 1:] - gw.V[:, 1:].mean(0)
    evec = np.linalg.eigh(yz.T @ yz)[1]
    up = np.array([0.0, evec[0, 1], evec[1, 1]])              # the long axis of the glass in the section
    if up[2] < 0:
        up = -up
    nrm = np.array([0.0, -up[2], up[1]])                      # out of the face, forwards
    hu, hn = gw.V @ up, gw.V @ nrm
    mid = gw.V.mean(0)
    mid[0] = xc

    def on_face(a_up, a_n):
        return mid + up * (a_up - mid @ up) + nrm * (a_n - mid @ nrm)

    sh.dim_aligned(vD.P(on_face(hu.min(), hn.max())), vD.P(on_face(hu.max(), hn.max())), 34.0, fmt(hu.max() - hu.min()))
    gx, gy = vD.P(on_face((hu.min() + hu.max()) / 2, (hn.min() + hn.max()) / 2))
    sh.leader((gx, gy), (gx - 40.0, gy + 44.0), f"WINDOW GLASS, {fmt(hn.max() - hn.min())} THICK", size=2.8)

    # ── balloons and parts table ──
    views = {"sec": (vA, cs), "front": (vF, scn), "left": (vL, scn), "rear": (vB, scn), "right": (vR, scn)}
    per_view, rows, item = {}, [], 0
    for name, aa, pref in HEAD_ITEMS:
        ob = by_name.get((name, aa))
        if ob is None:
            print(f"DRAWINGS WARN sheet 2: no part named {name!r}")
            continue
        num = ob["rj28_number"]
        hit = None
        for vk in [pref] + [q for q in ("sec", "left", "front", "rear", "right") if q != pref]:
            v, s = views[vk]
            if num not in s.index:
                continue
            sel = np.zeros(len(s.parts), bool)
            sel[s.index[num]] = True
            p = s.visible_point(v, sel, prefer=(lambda loc: abs(loc[0] - xc) < 0.01) if vk == "sec" else None)
            if p is not None:
                hit = (vk, v.pt(*p))
                break
        if hit is None:
            print(f"DRAWINGS WARN sheet 2: {name} is not visible in any view")
            continue
        item += 1
        per_view.setdefault(hit[0], []).append((str(item), num, None, hit[1]))
        r = ctx.by_num.get(num, {})
        rows.append([str(item), num, name.upper(), str(r.get("material", "")).upper(), str(r.get("count", 1)),
                     f"{r.get('mass_kg', 0):.3f}"])
    if "sec" in per_view:
        place_balloons(sh, vA, per_view["sec"], bA, ("left", "right"), pitch=11.0, off=15.0,
                       limits={"left": (bA[1] + 14, bA[3] - 4), "right": (bA[1] + 14, sec_base - 34)})
    for vk, sides, off in (("front", ("left", "right"), 12.0), ("left", ("top",), 24.0), ("rear", ("right",), 13.0),
                           ("right", ("bottom",), 30.0)):
        if vk in per_view:
            v = views[vk][0]
            place_balloons(sh, v, per_view[vk], v.bbox(), sides, pitch=10.5, off=off)
    tx = TITLE_X0
    rh = 4.9
    ty0 = sh_title_top(sh) - 6.0 - (len(rows) + 1) * rh
    sh.table(tx, ty0, [(10, "c", "tm"), (27, "l", "tn"), (48, "l", "tl"), (74, "l", "tl"), (10, "c", "tn"), (21, "r", "tn")],
             rows, head=["ITEM", "PART NUMBER", "DESCRIPTION", "MATERIAL", "QTY", "MASS kg"], row_h=rh, size=2.5,
             title="PARTS LIST, ITEMS BALLOONED")
    a01 = next(a for a in ctx.spec["mass"]["by_assembly"] if a["assembly"] == "01")
    a02 = next(a for a in ctx.spec["mass"]["by_assembly"] if a["assembly"] == "02")
    sh.note_block(tx, 26.0, "NOTES", [
        f"1.  ASSEMBLY 01 HEAD AND CAP: {a01['parts']} PARTS, {a01['mass_kg']:.2f} kg. ASSEMBLY 02 NECK: {a02['parts']} PARTS, "
        f"{a02['mass_kg']:.2f} kg.",
        "2.  THE CAP IS WORN BRIM TO THE REAR. THE FRONT VIEW LOOKS INTO THE STRAP ARCH.",
        "3.  SECTION A-A IS TAKEN ON THE CENTRE PLANE. FASTENERS, GLASS AND MESH ARE NOT LINED.",
        "4.  THE PARTS LIST NAMES THE BALLOONED ITEMS ONLY.",
        f"5.  NECK TRAVEL: YAW ±{fmt(_range(ctx, 'neck_yaw'))}°, PITCH ±{fmt(_range(ctx, 'neck_pitch'))}°, "
        f"ROLL ±{fmt(_range(ctx, 'neck_roll'))}°.",
    ], size=3.0, lead=1.6, width=186.0)
    return sh


def _range(ctx, name):
    return next(j for j in ctx.joints if j["name"] == name)["range"][1]


def sh_title_top(sh):
    """Top of the revision table: 4.6 mm per revision row, above a 58 mm title block."""
    return SHEET_H - MARGIN - 58.0 - 4.6 * (len(REVISIONS) + 1)


# ── sheet 3: cannon and mount ────────────────────────────────────────────────
ZONE_NAMES = {"pauldron_R": "RIGHT SHOULDER ARMOUR", "arm_R": "RIGHT ARM", "head": "HEAD", "cap": "CAP AND BRIM",
              "thorax": "THORAX", "backpack": "BACKPACK", "mount_fix": "MOUNT HARDPOINT"}


def sheet3(ctx):
    k = 0.4
    sh = Sheet(3, scale_text(k))
    spec = ctx.spec
    mt, env, dep = spec["mount"], spec["envelope"]["stowed"], spec["envelope"]["deployed"]
    T = np.array(mt["trunnion"])
    rise = mt["bore_rise"]
    el0, el1 = mt["elevation"]
    tv = mt["traverse"]
    poses.set_mount("stowed")
    objs = ctx.objects(lambda o: o["rj28_assembly"] in ("01", "02", "03", "06", "08", "15"))
    scn = ctx.scene("mount_stowed", objs)
    mobs = [o for o in objs if o.get("mount_group") in ("elev", "trav")]
    eobs = [o for o in mobs if o.get("mount_group") == "elev"]
    barrel = next(o for o in objs if o["rj28_name"] == "Barrel" and o["rj28_assembly"] == "15")
    m_all = bounds([o for o in objs if o["rj28_assembly"] == "15"])
    e_st, b_st = bounds(eobs), bounds([barrel])
    poses.set_mount("deployed")
    e_dp, b_dp = bounds(eobs), bounds([barrel])
    poses.set_mount("stowed")
    y0, y1 = dep["min"][1] - 20.0, env["max"][1] + 14.0
    z0, z1 = 1350.0, env["height"] + 16.0
    x0, x1 = m_all[0][0] - 14.0, 92.0
    vS = sh.add_view(View("s3-side", "RIGHT-HAND SIDE VIEW", *ORTHO["right"], k))      # a = -y, b = z
    vT = sh.add_view(View("s3-top", "TOP VIEW", -Y, X, k))                            # a = -y, b = x
    vF = sh.add_view(View("s3-front", "FRONT VIEW", X, Z, k))                         # a = x, b = z
    xs0, yb = MARGIN + 40.0, SHEET_H - MARGIN - 32.0
    vS.place(xs0 + y1 * k, yb + z0 * k)
    side_top = yb - (z1 - z0) * k
    vT.place(xs0 + y1 * k, side_top - 22.0 + x0 * k)
    xf0 = xs0 + (y1 - y0) * k + 30.0
    vF.place(xf0 - x0 * k, yb + z0 * k)
    wins = {vS: ("rect", -y1, z0, -y0, z1), vT: ("rect", -y1, x0, -y0, x1), vF: ("rect", x0, z0, x1, z1)}

    def cls(num, meta, state):
        if meta[0] == "15":
            return ("hid", "det", "vis")[state]
        return "ctx" if state else None

    for v in (vS, vT, vF):
        ctx.lines(v, lambda v=v: (scn,) + project(scn, v, window=wins[v], step=0.25), cls)

    # the same mount, deployed and at the traverse limits, as phantom outlines
    def phantom(view, key, obs, elev, trav):
        def run():
            poses.set_mount("deployed", elev=elev, trav=trav)
            s = Scene([geo_from_object(o) for o in obs])
            poses.set_mount("stowed")
            return (s,) + project(s, view, gap=30.0, small=4.0, step=0.25)
        ctx.lines(view, run, lambda num, meta, state: "pha" if state == 2 else None, name=f"{view.id}-{key}")

    phantom(vS, "deployed", eobs, 0.0, 0.0)
    phantom(vT, "deployed", eobs, 0.0, 0.0)
    phantom(vT, "trav-in", eobs, 0.0, tv)
    phantom(vT, "trav-out", eobs, 0.0, -tv)

    # ── side view ──
    tx, tyy = vS.P(T)
    bore_z, bore_y = T[2] + rise, T[1] + rise
    reach = T[1] - e_dp[0][1]
    x_rear = vS.pt(-e_st[1][1], 0)[0]
    # axes: trunnion, bore level, bore stowed
    sh.line(x_rear - 26.0, tyy, vS.pt(-(T[1] - 100), 0)[0], tyy, "ctr")
    sh.line(tx, tyy - 34, tx, tyy + 34, "ctr")
    y_bore = vS.pt(0, bore_z)[1]
    sh.line(x_rear - 26.0, y_bore, vS.pt(-(e_dp[0][1] - 26), 0)[0], y_bore, "ctr")
    sh.line(*vS.pt(-bore_y, e_st[0][2] - 26), *vS.pt(-bore_y, e_st[1][2] + 12), "ctr")
    # elevation: angle between the bore axis stowed and deployed
    q = vS.pt(-bore_y, bore_z)
    sh.dim_angle(q, 150.0, 0.0, el1, fmt(el1) + "°", mask=True)
    # depression limit: the bore axis at the lowest elevation
    th = math.radians(-el0)
    p5 = T + np.array([0, -rise * math.sin(th), rise * math.cos(th)])
    d5 = np.array([0, -math.cos(th), -math.sin(th)])
    sh.line(*vS.P(p5 + d5 * 60), *vS.P(p5 + d5 * (reach + 52)), "ctr")
    qi = vS.P(p5 + d5 * (rise * (math.cos(th) - 1) / math.sin(th)))
    sh.dim_angle(qi, (reach + 34) * k, 0.0, el0, fmt(abs(el0)) + "°", text_r=(reach + 34) * k + 8.0)
    # path of the muzzle centre about the trunnion
    mz = np.array([T[0], b_dp[0][1], (b_dp[0][2] + b_dp[1][2]) / 2])
    rm = float(np.linalg.norm((mz - T)[1:]))
    a_dep = math.degrees(math.atan2(mz[2] - T[2], T[1] - mz[1]))
    sh.arc(tx, tyy, rm * k, a_dep, a_dep + (el1 - 0.0), "pha")
    am = math.radians(a_dep + 56.0)
    sh.text(tx + (rm * k + 2.5) * math.cos(am), tyy - (rm * k + 2.5) * math.sin(am), "PATH OF THE MUZZLE CENTRE", "tl", 2.8,
            "middle", rot=math.degrees(am) - 90)
    # bore rise and barrel length, behind the breech
    xd = x_rear - 12.0
    sh.dim((xd + 1.2, tyy), (xd + 1.2, y_bore), xd, fmt(rise), "v", ext=False)
    xb = x_rear - 12.0
    sh.dim((vS.pt(-(bore_y + mt["barrel_od"] / 2), 0)[0], vS.pt(0, b_st[0][2])[1]),
           (vS.pt(-(bore_y + mt["barrel_od"] / 2), 0)[0], vS.pt(0, b_st[0][2] + mt["barrel_length"])[1]),
           xb, fmt(mt["barrel_length"]), "v")
    # barrel diameter by leader on the stowed barrel
    zb = b_st[0][2] + mt["barrel_length"] * 0.66
    sh.leader(vS.pt(-(bore_y - mt["barrel_od"] / 2), zb), (vS.pt(-(bore_y - 130), 0)[0], vS.pt(0, zb + 50)[1]),
              "Ø" + fmt(mt["barrel_od"]) + " BARREL", cls="tn", size=3.0)
    # reach of the muzzle ahead of the trunnion, deployed
    sh.dim((tx, tyy + 36), (vS.pt(-e_dp[0][1], 0)[0], vS.pt(0, b_dp[0][2])[1]), yb + 9.0, fmt(reach), "h")
    # heights above ground
    sh.text(x_rear - 25.0, tyy + 4.2, f"TRUNNION AXIS, {fmt(T[2])} ABOVE GROUND", "tl", 2.8, mask=True)
    ytop = vS.pt(0, env["height"])[1]
    xm = vS.pt(-(e_st[0][1] - 12), 0)[0]
    sh.line(xm - 6.0, ytop, xm + 12.0, ytop, "dim")
    level_mark(sh, xm + 4.0, ytop, f"{fmt(env['height'])} ABOVE GROUND, STOWED", side=1, size=2.8)
    pha = [pl for (num, c), pls in vS.lines.items() if c == "pha" for pl in pls]
    if pha:
        top = min((pl[pl[:, 1].argmin()] for pl in pha), key=lambda p: p[1])
        px, py = vS.ox + top[0], vS.oy + top[1]
        sh.line(px - 3.0, py, px + 24.0, py, "dim")
        level_mark(sh, px + 16.0, py, f"{fmt(dep['height'])} ABOVE GROUND, DEPLOYED", side=1, size=2.8)
    break_line(sh, vS.pt(-y1, 0)[0] + 24, yb, vS.pt(-y0, 0)[0] - 84, yb)
    sh.view_title(vS, xs0 + (y1 - y0) * k / 2, yb + 18.0, size=4.0, extra="MOUNT STOWED. DEPLOYED POSITION IN PHANTOM")

    # ── top view: traverse ──
    sx, sy = vT.pt(-T[1], T[0])
    Lc = reach + 60.0
    for a in (-tv, 0.0, tv):
        e = np.array([math.sin(math.radians(a)), -math.cos(math.radians(a)), 0.0])     # positive swings inboard
        p = np.array([T[0], T[1], 0.0])
        sh.line(*vT.P(p - e * (40 if a else 150)), *vT.P(p + e * Lc), "ctr")
    sh.line(sx, sy - 30, sx, sy + 30, "ctr")
    ra = (reach + 26.0) * k
    sh.dim_angle((sx, sy), ra, 0.0, tv, fmt(tv) + "°")
    sh.dim_angle((sx, sy), ra, 0.0, -tv, fmt(tv) + "°")
    # bore offset from the centre plane
    yc0 = vT.pt(0, 0)[1]
    xo = vT.pt(-e_st[1][1], 0)[0] - 12.0
    sh.line(xo - 4.0, yc0, vT.pt(-y0, 0)[0] - 150, yc0, "ctr")
    sh.dim((xo + 1.2, yc0), (xo + 1.2, sy), xo, fmt(abs(T[0])), "v", ext=False)
    sh.text(xo + 3.0, yc0 - 1.4, "CENTRE PLANE", "tl", 2.6)
    sh.view_title(vT, vT.pt(-y0, 0)[0] + 10.0, vT.pt(0, x1)[1] + 8.0, anchor="start", size=4.0,
                  extra="DEPLOYED AT ZERO AND AT THE TRAVERSE LIMITS IN PHANTOM")

    # ── front view ──
    bx, cxf = vF.pt(T[0], 0)[0], vF.pt(0, 0)[0]
    yo = vF.pt(0, e_st[1][2])[1] - 9.0
    sh.line(bx, vF.pt(0, e_st[0][2] - 26)[1], bx, yo - 3.0, "ctr")
    sh.line(cxf, yb - 4, cxf, yo - 3.0, "ctr")
    sh.dim((bx, yo + 1.2), (cxf, yo + 1.2), yo, fmt(abs(T[0])), "h", ext=False)
    sh.line(vF.pt(T[0] - 140, 0)[0], vF.pt(0, T[2])[1], vF.pt(T[0] + 150, 0)[0], vF.pt(0, T[2])[1], "ctr")
    break_line(sh, vF.pt(x0, 0)[0] + 16, yb, vF.pt(x1, 0)[0], yb)
    break_line(sh, vF.pt(x1, 0)[0], yb, vF.pt(x1, 0)[0], vF.pt(0, 1700)[1])
    break_line(sh, vT.pt(-y1, 0)[0] + 50, vT.pt(0, x1)[1], vT.pt(-y0, 0)[0] - 190, vT.pt(0, x1)[1])
    sh.view_title(vF, xf0 + (x1 - x0) * k / 2, yb + 18.0, size=4.0, extra="MOUNT STOWED")

    # ── clearance schedule from the swept-volume check ──
    tx0 = TITLE_X0
    yt = 30.0
    if ctx.sweep:
        best = {}
        for z in ctx.sweep["zones"]:
            if z["zone"] in ZONE_NAMES and (z["zone"] not in best or z["clearance_mm"] < best[z["zone"]]["clearance_mm"]):
                best[z["zone"]] = z
        rows = []
        for i, z in enumerate(sorted(best.values(), key=lambda z: z["clearance_mm"])):
            rows.append([str(i + 1), ZONE_NAMES[z["zone"]], f"{z['clearance_mm']:.1f}", f"{z['elev']:+.1f}°",
                         f"{z['trav']:+.1f}°", "CRADLE" if z["group"] == "elev" else "YOKE"])
            p = np.array(z["at_mm"], float)
            for v, (dx, dy) in ((vS, (7.0, -9.0)), (vT, (7.0, 9.0)), (vF, (7.0, 9.0))):
                w = wins[v]
                a, b = v.ab(p)
                if w[1] + 8 < a < w[3] - 8 and w[2] + 8 < b < w[4] - 8:
                    px, py = v.pt(a, b)
                    sh.dot(px, py, 0.6)
                    sh.line(px, py, px + dx * 0.72, py + dy * 0.72, "dim")
                    flag(sh, px + dx, py + dy + 1.0, i + 1)
        yt = sh.table(tx0, yt, [(13, "c", "tm"), (61, "l", "tl"), (27, "r", "tn"), (29, "r", "tn"), (29, "r", "tn"),
                                (31, "l", "tl")], rows,
                      head=["FLAG", "NEAREST STRUCTURE", "CLEARANCE", "ELEVATION", "TRAVERSE", "MOVING PART"], row_h=5.6,
                      size=2.8, title="MINIMUM CLEARANCES THROUGH THE TRAVEL")
        yt = sh.note_block(tx0, yt + 12.0, "SWEPT VOLUME CHECK", [
            f"THE MOUNT IS SWEPT THROUGH {ctx.sweep['poses']} POSES: ELEVATION {fmt(el0)}° TO {fmt(el1)}° AT ZERO TRAVERSE, "
            f"THEN TRAVERSE ±{fmt(tv)}° AT 0° AND AT {fmt(el0)}°.",
            f"SURFACES ARE SAMPLED AT {fmt(ctx.sweep['sample_spacing_mm'])} mm. REQUIRED CLEARANCE "
            f"{fmt(ctx.sweep['required_mm'])} mm. MINIMUM FOUND {ctx.sweep['min_clearance_mm']:.1f} mm.",
            "FLAGS MARK WHERE EACH MINIMUM OCCURS ON THE FIXED STRUCTURE. THEY ARE CLEARANCES IN SPACE AT THE POSE "
            "LISTED, NOT DISTANCES TO SCALE IN THESE VIEWS.",
        ], size=2.9, lead=1.55, width=186.0)
    rows = [("BARREL", f"Ø{fmt(mt['barrel_od'])} × {fmt(mt['barrel_length'])}"),
            ("ELEVATION", f"{fmt(el0)}° TO {fmt(el1)}°"), ("TRAVERSE", f"±{fmt(tv)}°"),
            ("TRUNNION AXIS ABOVE GROUND", fmt(T[2])), ("TRUNNION AXIS BEHIND HIP AXES", fmt(T[1])),
            ("BORE AXIS FROM CENTRE PLANE", fmt(abs(T[0]))), ("BORE AXIS ABOVE TRUNNION, LEVEL", fmt(rise)),
            ("MUZZLE AHEAD OF TRUNNION, DEPLOYED", fmt(reach)),
            ("OVERALL HEIGHT, STOWED", fmt(env["height"])), ("OVERALL HEIGHT, DEPLOYED", fmt(dep["height"])),
            ("MASS, ASSEMBLY 15", f"{next(a for a in spec['mass']['by_assembly'] if a['assembly'] == '15')['mass_kg']:.2f} kg")]
    sh.table(tx0, yt + 12.0, [(100, "l", "tl"), (90, "l", "tn")], rows, row_h=5.6, size=2.8, title="MOUNT DATA")
    return sh


# ── sheet 4: leg mechanism ───────────────────────────────────────────────────
ARMOUR_KIT = ("Armour", "Guard", "Strike", "Hatch", "Hamstring", "Calf", "Vent Screen", "Carrier Standoffs",
              "Thigh Upper Screws", "Thigh Lower Screws", "Shin Front Screws", "Shin Outer Screws",
              "Shin Inner Screws", "Foot Side Screws")


def clip_to_circle(p, q, c, rad):
    """The part of the paper segment p-q inside a circle, or None."""
    s = clip_segs(np.array([[p[0], p[1], q[0], q[1]]], float), ("circle", c[0], c[1], rad))
    return None if len(s) == 0 else s[0]


def sheet4(ctx):
    from .assemblies import leg as LEG
    k = 0.5
    sh = Sheet(4, scale_text(k))
    poses.set_mount("stowed")
    note = ctx.spec["design_notes"][0]
    inp = note["inputs"]
    hip, thigh, knee, shin, ankle, foot = FR.leg(1)
    objs = ctx.objects(lambda o: o["rj28_assembly"] in ("11", "13"))
    kit = [o for o in objs if any(s in o["rj28_name"] for s in ARMOUR_KIT)]
    mech = [o for o in objs if o not in kit]
    scn = ctx.scene("leg_mech", mech)
    arm = ctx.scene("leg_armour", [o for o in kit if o.get("rj28_material") == "armour"])
    # view along the knee axis from outboard, and from behind
    xk = np.array((knee.to_3x3() @ Vector((1, 0, 0))).normalized())
    u = Z - xk * (Z @ xk)
    u /= np.linalg.norm(u)
    r = np.cross(u, xk)
    K, A, Hp = np.array(knee.translation), np.array(ankle.translation), np.array(hip.translation)
    vS = sh.add_view(View("s4-side", "LEFT LEG, VIEW ALONG THE KNEE AXIS", r, u, k))
    vB = sh.add_view(View("s4-rear", "VIEW FROM BEHIND", -xk, u, k))
    pa, pb, px = scn.V @ r, scn.V @ u, scn.V @ -xk
    floor_b = float(pb.min())
    base = SHEET_H - MARGIN - 30.0
    xs = MARGIN + 46.0
    vS.place(xs - pa.min() * k, base + floor_b * k)
    xb = xs + (pa.max() - pa.min()) * k + 52.0
    vB.place(xb - px.min() * k, base + floor_b * k)
    hid = scn.mask(lambda g: any(s in g.name for s in ("Act Rod", "Crank Pin", "Pin A", "Pin B", "Knee Shaft")))

    def phantom(view, name, window=None):
        ctx.lines(view, lambda: (arm,) + project(arm, view, gap=40.0, small=6.0, window=window),
                  lambda num, meta, state: "pha" if state == 2 else None, name=name)

    for v in (vS, vB):
        ctx.lines(v, lambda v=v: (scn,) + project(scn, v, hidden=hid, step=0.25), std_classes)
        phantom(v, v.id + "-armour")

    # pivots, from the model's own definitions
    def knee_pts(flex):
        p0 = np.array(thigh @ Vector(LEG.KNEE_P0))
        p1 = np.array(knee @ Matrix.Rotation(math.radians(flex), 4, "X") @ Vector(LEG.KNEE_P1))
        return p0, p1

    def lever(p0, p1, c, ax):
        dh = (p1 - p0) / np.linalg.norm(p1 - p0)
        return abs(float(ax @ np.cross(p0 - c, dh)))

    rng = inp["knee_range_deg"]
    p0, p1 = knee_pts(0.0)
    _, p1f = knee_pts(rng)
    L0, Lf = float(np.linalg.norm(p1 - p0)), float(np.linalg.norm(p1f - p0))
    xa = np.array((shin.to_3x3() @ Vector((1, 0, 0))).normalized())
    q0 = np.array(shin @ Vector(LEG.ANKLE_P0))
    q1n = np.array(foot @ Vector(LEG.ANKLE_P1))
    ar = next(j for j in ctx.joints if j["name"] == "ankle_pitch_L")["range"]

    def ankle_p1(deg):
        return np.array(Matrix.Translation(Vector(A)) @ Matrix.Rotation(math.radians(deg), 4, Vector(xa))
                        @ Matrix.Translation(-Vector(A)) @ Vector(q1n))

    La = {d: float(np.linalg.norm(ankle_p1(d) - q0)) for d in (ar[0], 0.0, ar[1])}
    arm_a = lever(q0, q1n, A, xa)

    # ── full leg: axes, actuator lines of action, pin-centre lengths ──
    for p, h in ((Hp, 70), (K, 62), (A, 52)):
        x, y = vS.P(p)
        sh.line(x - h * k, y, x + h * k, y, "ctr", sh.under)
        sh.line(x, y - h * k, x, y + h * k, "ctr", sh.under)
    for j in ctx.joints:
        if j["name"] in ("hip_pitch_L", "knee_pitch_L", "ankle_pitch_L"):
            sh.centre_line(vB, np.array(j["origin"]), np.array(j["axis"]), 150)
    sh.line(*vS.P(p0 + (p0 - p1) / L0 * 30), *vS.P(p1 + (p1 - p0) / L0 * 30), "ctr")
    sh.line(*vS.P(q0 + (q0 - q1n) / La[0.0] * 24), *vS.P(q1n + (q1n - q0) / La[0.0] * 24), "ctr")
    sh.dim_aligned(vS.P(p0), vS.P(p1), 30.0, fmt(L0))
    sh.dim_aligned(vS.P(q0), vS.P(q1n), 24.0, fmt(La[0.0]))
    # the three axes and their heights above ground
    lm = ctx.spec["landmarks"]
    xl = vS.pt(float(pa.min()), 0)[0] - 6.0
    for name, key, p in (("HIP AXIS", "hip_axis", Hp), ("KNEE AXIS", "knee_axis", K), ("ANKLE AXIS", "ankle_axis", A)):
        y = vS.P(p)[1]
        sp = vS.span_at_y(y)
        sh.line((sp[0] if sp else xl + 8) - 1.5, y, xl - 6.0, y, "dim")
        level_mark(sh, xl - 3.0, y, f"{name} {fmt(lm[key])}", side=-1, size=2.8)
    # ground: edge-on from behind, where it shows the abduction of the leg
    hz = np.cross(Z, vB.d)
    g0 = np.array([float(scn.V[:, 0].mean()), float(scn.V[:, 1].mean()), 0.0])
    sh.line(*vB.P(g0 - hz * 150), *vB.P(g0 + hz * 150), "fine", sh.under)
    bS, bB = vS.bbox(), vB.bbox()
    sh.view_title(vS, (bS[0] + bS[2]) / 2, base + 13.0, size=4.0, extra="ARMOUR OUTLINE IN PHANTOM")
    sh.view_title(vB, (bB[0] + bB[2]) / 2, base + 13.0, size=4.0, extra="SQUARE TO THE KNEE AXIS")

    # ── knee and ankle at full size ──
    kc = K + u * 4
    kr = min(100.0, (TITLE_X0 - 8.0 - bB[2] - 16.0) / 2)
    vK = sh.add_view(View("s4-knee", "DETAIL C", r, u, 1.0))
    cxk = bB[2] + 16.0 + kr
    cyk = MARGIN + 22.0 + kr
    vK.place(cxk - float(kc @ r), cyk + float(kc @ u))
    ac = (A + q1n) / 2 + u * 36 - r * 4
    arad = min(96.0, kr)
    vA = sh.add_view(View("s4-ankle", "DETAIL D", r, u, 1.0))
    cxa, cya = cxk, cyk + kr + 38.0 + arad
    vA.place(cxa - float(ac @ r), cya + float(ac @ u))
    for v, c, rad, letter in ((vK, kc, kr, "C"), (vA, ac, arad, "D")):
        w = ("circle", float(c @ r), float(c @ u), rad)
        ctx.lines(v, lambda v=v, w=w: (scn,) + project(scn, v, hidden=hid, window=w, step=0.25), std_classes)
        phantom(v, v.id + "-armour", w)
        sh.circle(*v.pt(w[1], w[2]), rad, "rule")
        qx, qy = vS.pt(w[1], w[2])
        sh.circle(qx, qy, rad * k, "pha")
        sh.text(qx + rad * k * 0.72 + 2.0, qy - rad * k * 0.72 - 1.5, letter, "tt", 4.6, mask=True)

    def cline(v, c, rad, a_, b_, cls_="ctr"):
        s = clip_to_circle(v.P(a_), v.P(b_), v.pt(float(c @ r), float(c @ u)), rad - 1.5)
        if s is not None:
            sh.line(*s, cls_)

    # knee: crank radius, crank travel, moment arm at both ends of the travel
    kx, ky = vK.P(K)
    cline(vK, kc, kr, K - r * 46, K + r * 46)
    cline(vK, kc, kr, K - u * 46, K + u * 46)
    a1 = math.degrees(math.atan2(float((p1 - K) @ u), float((p1 - K) @ r)))
    a2 = math.degrees(math.atan2(float((p1f - K) @ u), float((p1f - K) @ r)))
    sgn = 1 if abs(((a2 - a1) % 360) - rng) < 1.0 else -1
    crank = float(np.linalg.norm(p1 - K))
    sh.arc(kx, ky, crank, a1, a1 + sgn * rng, "pha")
    for pp in (p1, p1f):
        sh.circle(*vK.P(pp), 2.4, "rule")
        sh.line(kx, ky, *vK.P(pp), "ctr")
    sh.dim_angle((kx, ky), crank + 11.0, a1, a1 + sgn * rng, fmt(rng) + "°", mask=True)
    sh.dim_aligned((kx, ky), vK.P(p1), 0.0, fmt(inp["crank_radius_mm"]), mask=True)
    arms_k = inp["moment_arm_by_flexion_mm"]
    ends = [(p1, "0"), (p1f, str(int(rng)))]
    same = abs(arms_k[ends[0][1]] - arms_k[ends[1][1]]) < 1.0      # the crank is phased so both ends share a line
    for n_, (pp, key) in enumerate(ends[:1] if same else ends):
        dh = (pp - p0) / np.linalg.norm(pp - p0)
        ft = p0 + dh * float((K - p0) @ dh)
        seg = clip_to_circle(vK.P(pp + dh * 30), vK.P(pp - dh * 300), (cxk, cyk), kr - 1.5)
        if seg is not None:
            sh.line(*seg, "ctr")
        sh.dim_aligned((kx, ky), vK.P(ft), 0.0, fmt(arms_k[key]), mask=True)
        fx, fy = vK.P(ft)
        e = np.array([kx - fx, ky - fy])
        e /= np.linalg.norm(e)
        d2 = np.array(vK.P(ft + dh * 10)) - np.array([fx, fy])
        d2 /= np.linalg.norm(d2)
        sq = 2.6
        sh.poly([(fx + e[0] * sq, fy + e[1] * sq), (fx + e[0] * sq + d2[0] * sq, fy + e[1] * sq + d2[1] * sq),
                 (fx + d2[0] * sq, fy + d2[1] * sq)], "dim")
        if seg is not None:
            far = np.array(seg[2:4]) if np.hypot(seg[2] - fx, seg[3] - fy) > np.hypot(seg[0] - fx, seg[1] - fy) \
                else np.array(seg[0:2])
            lab = far + (np.array([fx, fy]) - far) / np.linalg.norm(np.array([fx, fy]) - far) * 34.0
            ang = math.degrees(math.atan2(-(fy - lab[1]), fx - lab[0]))
            if ang > 90 or ang <= -90:
                ang += 180 if ang <= -90 else -180
            txt = (f"LINE OF ACTION AT {ends[0][1]}° AND AT {ends[1][1]}°" if same else f"LINE OF ACTION AT {key}°")
            sh.text(lab[0], lab[1] - 1.2, txt, "tl", 2.6, "middle", rot=ang, mask=True)
    if same:
        sh.text(cxk, cyk + kr + 6.0, f"MOMENT ARM {fmt(arms_k[ends[0][1]])} AT {ends[0][1]}°, "
                f"{fmt(arms_k[ends[1][1]])} AT {ends[1][1]}°", "tl", 2.8, "middle")
    sh.view_title(vK, cxk, cyk + kr + 15.0, size=4.0, extra="KNEE CRANK, SEEN ALONG THE AXIS")
    # ankle: moment arm at neutral
    cline(vA, ac, arad, A - r * 40, A + r * 40)
    cline(vA, ac, arad, A - u * 40, A + u * 40)
    dh = (q1n - q0) / np.linalg.norm(q1n - q0)
    ft = q0 + dh * float((A - q0) @ dh)
    cline(vA, ac, arad, q1n + dh * 30, q1n - dh * 260)
    sh.circle(*vA.P(q1n), 2.4, "rule")
    sh.dim_aligned(vA.P(A), vA.P(ft), 0.0, fmt(arm_a), mask=True)
    lab, tip = vA.P(q1n - dh * 88), vA.P(q1n)
    ang = math.degrees(math.atan2(-(tip[1] - lab[1]), tip[0] - lab[0]))
    if ang > 90 or ang <= -90:
        ang += 180 if ang <= -90 else -180
    sh.text(lab[0], lab[1] - 1.2, "LINE OF ACTION, NEUTRAL", "tl", 2.6, "middle", rot=ang, mask=True)
    sh.view_title(vA, cxa, cya + arad + 9.0, size=4.0, extra="ANKLE DRIVE")

    # ── tables and the design note ──
    tx = TITLE_X0
    arms = inp["moment_arm_by_flexion_mm"]
    rows = [("CRANK PIN RADIUS", fmt(inp["crank_radius_mm"])), ("FLEXION RANGE", f"0° TO {fmt(rng)}°"),
            ("PIN CENTRES, KNEE STRAIGHT", fmt(L0)), (f"PIN CENTRES AT {fmt(rng)}°", fmt(Lf)),
            ("STROKE", fmt(inp["actuator_stroke_mm"])), ("ACTUATORS PER KNEE", str(inp["actuators_per_knee"]))]
    rows += [(f"MOMENT ARM AT {f}°", fmt(v)) for f, v in arms.items()]
    yt = sh.table(tx, 28.0, [(110, "l", "tl"), (80, "l", "tn")], rows, row_h=5.3, size=2.8, title="KNEE ACTUATION")
    rows = [("PITCH RANGE", f"{fmt(ar[0])}° TO {fmt(ar[1])}°"), ("PIN CENTRES, NEUTRAL", fmt(La[0.0])),
            (f"PIN CENTRES AT {fmt(ar[0])}° / {fmt(ar[1])}°", f"{fmt(La[ar[0]])} / {fmt(La[ar[1]])}"),
            ("STROKE USED", fmt(abs(La[ar[1]] - La[ar[0]]))), ("MOMENT ARM, NEUTRAL", fmt(arm_a)),
            ("ACTUATORS PER ANKLE", "2, PITCH TOGETHER, ROLL OPPOSED")]
    yt = sh.table(tx, yt + 12.0, [(110, "l", "tl"), (80, "l", "tn")], rows, row_h=5.3, size=2.8, title="ANKLE ACTUATION")
    yy = sh.note_block(tx, yt + 12.0, "DESIGN NOTE 1: " + note["title"].upper(),
                       [f"{i + 1}.  {w}" for i, w in enumerate(note["working"])], size=2.9, lead=1.55, width=184.0)
    yy += 2.0
    for row in wrap(note["verdict"], 184.0, 2.9):
        sh.text(tx, yy, row, "tl", 2.9)
        yy += 2.9 * 1.55
    res = note["result"]
    sh.text(tx, yy + 3.5, f"RESULT  {fmt(res['torque_per_knee_nm'])} N m PER KNEE, "
                          f"{fmt(res['force_per_actuator_kn'])} kN PER ACTUATOR", "tm", 3.0)
    sh.note_block(MARGIN + 10.0, 26.0, "NOTES", [
        "1.  ARMOUR, ITS CARRIERS AND GUARDS ARE OMITTED.",
        "     THEIR OUTLINE IS SHOWN IN PHANTOM.",
        "2.  VIEWS ARE ALONG AND SQUARE TO THE KNEE AXIS:",
        "     PIN CENTRES ARE TRUE LENGTHS.",
        "3.  HIDDEN LINES SHOW RODS, PINS AND THE KNEE SHAFT.",
        "4.  LEFT LEG SHOWN. THE RIGHT LEG IS OPPOSITE HAND.",
    ], size=2.8, lead=1.55)
    return sh


# ── sheet 5: exploded isometric ──────────────────────────────────────────────
def sheet5(ctx):
    spec = ctx.spec
    sh = Sheet(5, "")
    poses.set_mount("stowed")
    # stage 1 of the exploded view: each assembly root at its full offset, parts at home on their root.
    # (explode.pose also zeroes part locations, which would undo the mount's stowed pose.)
    roots = explode.apply()
    for root in roots.values():
        root.location = Vector(root["explode_offset"])
    bpy.context.view_layer.update()
    objs = ctx.objects()
    scn = Scene([geo_from_object(o) for o in objs])
    for root in roots.values():
        root.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    homes = {aa: np.array(off, float) for aa, off in explode.ASM_OFFSET.items()}
    d = np.array([-1.0, -1.0, 1.0]) / math.sqrt(3)       # seen from the front right, above
    u = Z - d * (Z @ d)
    u /= np.linalg.norm(u)
    r = np.cross(u, d)
    a, b = scn.V @ r, scn.V @ u
    avail_w, avail_h = TITLE_X0 - MARGIN - 64.0, SHEET_H - 2 * MARGIN - 56.0
    k = next(s for s in (1 / 5, 1 / 6, 1 / 8, 1 / 10, 1 / 20) if np.ptp(a) * s <= avail_w and np.ptp(b) * s <= avail_h)
    sh.scale = scale_text(k)
    v = sh.add_view(View("s5-exploded", "EXPLODED ISOMETRIC", r, u, k))
    cx = MARGIN + 32.0 + avail_w / 2
    cy = MARGIN + 22.0 + avail_h / 2
    v.place(cx - (a.min() + a.max()) / 2 * k, cy + (b.min() + b.max()) / 2 * k)
    harness = scn.mask(lambda g: g.asm == "16" or g.mat == "braid")
    ctx.lines(v, lambda: (scn,) + project(scn, v, outline_only=harness, tiny=0.5, small=3.0), std_classes)
    # balloons
    items, boxes = [], {}
    bb = v.bbox()
    for aa in sorted(parts.ASSEMBLIES):
        ab_ = v.bbox(numbers={g.number for g in scn.parts if g.asm == aa})
        if ab_ is None:
            continue
        boxes[aa] = ab_
    for aa, ab_ in boxes.items():
        mx, my = (ab_[0] + ab_[2]) / 2, (ab_[1] + ab_[3]) / 2

        def blocked(side):
            """Length of other assemblies' boxes a straight leader to that side would cross."""
            tot = 0.0
            for other, ob_ in boxes.items():
                if other == aa:
                    continue
                if side in ("left", "right"):
                    if ob_[1] < my < ob_[3]:
                        lo_, hi_ = (bb[0], mx) if side == "left" else (mx, bb[2])
                        tot += max(0.0, min(hi_, ob_[2]) - max(lo_, ob_[0]))
                elif ob_[0] < mx < ob_[2]:
                    tot += max(0.0, min(my, ob_[3]) - max(bb[1], ob_[1]))
            return tot

        dist = {"left": mx - bb[0], "right": bb[2] - mx, "top": my - bb[1]}
        side = min(dist, key=lambda s_: (round(blocked(s_) / 2.0), dist[s_]))
        toward = {"left": (-0.7, 0.0), "right": (0.7, 0.0), "top": (0.0, 0.7)}[side]
        p = scn.visible_point(v, scn.mask(lambda g: g.asm == aa), toward=toward)
        if p is not None:
            items.append((aa, None, aa, v.pt(*p), side))
    place_balloons(sh, v, items, bb, ("left", "right", "top"), pitch=14.0, off=10.0)
    sh.view_title(v, MARGIN + 12.0, SHEET_H - MARGIN - 16.0, anchor="start", size=4.0,
                  extra="ASSEMBLIES DISPLACED ALONG THEIR DIRECTION OF REMOVAL")
    # bill of materials
    rows, n_parts, mass = [], 0, 0.0
    counts = {}
    for row in ctx.rows:
        counts[row["assembly"]] = counts.get(row["assembly"], 0) + 1
    for asm in spec["mass"]["by_assembly"]:
        aa = asm["assembly"]
        off = homes.get(aa, np.zeros(3))
        rows.append([aa, asm["name"].upper(), str(counts.get(aa, asm["parts"])), f"{asm['mass_kg']:.2f}",
                     " ".join(f"{c}{fmt(val):>5}" for c, val in zip("XYZ", off)) if np.any(off) else "IN PLACE"])
        n_parts += counts.get(aa, asm["parts"])
        mass += asm["mass_kg"]
    rows.append(["", "TOTAL", str(n_parts), f"{mass:.2f}", ""])
    tx = TITLE_X0
    yt = sh.table(tx, 30.0, [(13, "c", "tm"), (60, "l", "tl"), (17, "r", "tn"), (24, "r", "tn"), (76, "l", "tn")], rows,
                  head=["ASSY", "DESCRIPTION", "PARTS", "MASS kg", "DISPLACEMENT SHOWN, mm"], row_h=5.8, size=2.8,
                  title="BILL OF MATERIALS BY ASSEMBLY")
    m = spec["mass"]
    sh.note_block(tx, yt + 13.0, "NOTES", [
        f"1.  PART COUNTS AND MASSES ARE ROLLED UP FROM THE PARTS DATA: {len(ctx.rows)} PARTS, {m['total_kg']:.2f} kg "
        f"AGAINST A READY MASS OF {fmt(m['target_kg'])} kg.",
        "2.  MASS IS MESH VOLUME × MATERIAL DENSITY × A FILL FACTOR PER MATERIAL CLASS.",
        "3.  PART NUMBERS RUN RJ28-AA-NNN, AA BEING THE ASSEMBLY NUMBER IN THE BALLOON.",
        "4.  ASSEMBLY 17, MARKINGS, IS APPLIED TO ITS HOST PARTS AND IS NOT DRAWN.",
        "5.  DISPLACEMENTS ARE IN ROBOT AXES: X TO THE ROBOT'S LEFT, Y TO THE REAR, Z UP.",
    ], size=2.9, lead=1.55, width=184.0)
    # axis triad
    ox, oy = MARGIN + 30.0, MARGIN + 40.0
    for name, vec in (("X", X), ("Y", Y), ("Z", Z)):
        e = np.array([vec @ r, -(vec @ u)]) * 16.0
        sh.line(ox, oy, ox + e[0], oy + e[1], "rule")
        sh.arrow(ox + e[0], oy + e[1], math.degrees(math.atan2(-e[1], e[0])), L=2.6, w=0.5)
        sh.text(ox + e[0] * 1.25, oy + e[1] * 1.25 + 1.0, name, "tm", 3.0, "middle")
    return sh


SHEETS = {1: sheet1, 2: sheet2, 3: sheet3, 4: sheet4, 5: sheet5}


def run(opts):
    arg = {o.split("=")[0]: o.split("=")[1] for o in opts if "=" in o}
    which = sorted(int(s) for s in arg["sheet"].split(",")) if "sheet" in arg else sorted(SHEETS)
    t0 = time.time()
    blend = ROOT / "blender" / "out" / "model_drawings.blend"
    if "cache" in opts and blend.exists():
        bpy.ops.wm.open_mainfile(filepath=str(blend))
    else:
        from . import model
        model.build()
        if "cache" in opts:
            bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    print(f"DRAWINGS model ready, {len(parts.all_parts())} parts, {time.time() - t0:.1f} s")
    ctx = Ctx(opts)
    ctx.check()
    fonts = font_css()
    OUT.mkdir(parents=True, exist_ok=True)
    index_path = DATA / "sheets.json"
    old = {}
    if index_path.exists():
        try:
            old = {s["number"]: s for s in json.loads(index_path.read_text(encoding="utf-8"))["sheets"]}
        except (ValueError, KeyError):
            old = {}
    for n in which:
        t = time.time()
        sh = SHEETS[n](ctx)
        svg = sh.svg(fonts)
        path = OUT / f"{sh.number}.svg"
        path.write_text(svg, encoding="utf-8", newline="\n")
        old[sh.number] = dict(
            id=f"ga-{n:03d}", number=sh.number, title=sh.title, file=f"drawings/{sh.number}.svg",
            width=SHEET_W, height=SHEET_H, scale=sh.scale,
            views=[dict(id=v.id, title=v.title, scale=v.scale_text,
                        box=[round(c, 1) for c in (v.bbox() or (0, 0, 0, 0))]) for v in sh.views],
            parts=sh.part_index())
        print(f"SHEET {n} {sh.number} {path.stat().st_size / 1e6:.2f} MB, {sh.stats['paths']} paths, "
              f"{sh.stats['points']} points, {time.time() - t:.1f} s")
        if "nopng" not in opts:
            ok = rasterise(path, REVIEW / f"sheet_{n}.png")
            print(f"SHEET {n} png {'written' if ok else 'FAILED'}")
    index = dict(
        note="Sheet coordinates are SVG user units (mm on an A1 sheet, origin top left). parts maps a part number "
             "(RJ28-AA-NNN) or an assembly id (AA) to its places on the sheet: v = view group id, x/y = centre, "
             "w/h = size of its visible line work; b = 1 marks a balloon (tx/ty = where its leader ends).",
        set=dict(file="drawings/RJ28-GA-set.pdf", revision=REVISIONS[-1][0], date=REVISIONS[-1][2], sheets=len(TITLES)),
        sheets=[old[k] for k in sorted(old)])
    index_path.write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8", newline="\n")
    svgs = [OUT / f"RJ28-GA-{n:03d}.svg" for n in sorted(TITLES)]
    if "nopdf" not in opts and all(p.exists() for p in svgs):
        ok = pdf_set(svgs, OUT / "RJ28-GA-set.pdf")
        print(f"SHEET set pdf {'written' if ok else 'FAILED'}")
    poses.set_mount("stowed")
    print(f"DRAWINGS done in {time.time() - t0:.1f} s")
