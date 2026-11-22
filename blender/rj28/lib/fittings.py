"""Panel-level fittings: panel gaps, vents, hatches, hinges, lifting eyes,
decal labels. Dimensions mm. Fittings are built in a local frame where XY is
the host surface and +Z points out of it; pass `matrix` to place them.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from .. import materials as M
from . import prims as P
from .core import MM, T, R, boolean_cut, cutter, obj_from_bm
from . import mech

DECALS = []          # filled by label(); consumed by markings.build_atlas()


def _bvh(target):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    return BVHTree.FromObject(target, dg)


# ── panel gap ────────────────────────────────────────────────────────────────
def panel_cut(target, path, width=1.5, depth=2.0, lip=0.3, closed=False, snap=True,
              normal=None):
    """Cut a constant-width groove along `path` (3D points, mm) on target's
    surface. The lips get a small chamfer built into the cutter profile, so the
    groove catches a highlight without needing a bevel.

    normal: fixed outward normal; default takes it from the surface per point.
    """
    pts = [Vector(p) for p in path]
    norms = []
    if snap or normal is None:
        bvh = _bvh(target)
        for i, p in enumerate(pts):
            loc, nrm, _, _ = bvh.find_nearest(p * MM)
            # the path is given just outside the surface: the outward normal is the
            # one facing the given point, whatever face the nearest hit landed on
            out = p - loc / MM
            nrm = nrm.normalized()
            if out.length > 1e-4 and nrm.dot(out) < 0:
                nrm = -nrm
            if norms and nrm.dot(norms[-1]) < 0.2:
                nrm = norms[-1]
            if snap:
                pts[i] = loc / MM
            norms.append(Vector(normal).normalized() if normal is not None else nrm)
    else:
        norms = [Vector(normal).normalized()] * len(pts)
    n = len(pts)
    w, up = width / 2, 3.0
    prof = [(-w, -depth), (w, -depth), (w, -lip), (w + lip, 0.0), (w + lip, up),
            (-w - lip, up), (-w - lip, 0.0), (-w, -lip)]
    secs = []
    for i in range(n):
        a = pts[(i - 1) % n] if (closed or i > 0) else pts[i]
        b = pts[(i + 1) % n] if (closed or i < n - 1) else pts[i]
        tan = (b - a).normalized()
        nr = (norms[i] - tan * norms[i].dot(tan)).normalized()
        side = tan.cross(nr)
        o = pts[i]
        if not closed and i == 0:
            o = o - tan * 0.01
        secs.append([tuple(o + side * s + nr * h) for s, h in prof])
    bm = P.loft(secs, cap=not closed, wrap=closed)
    return boolean_cut(target, cutter(bm))


# ── vents ────────────────────────────────────────────────────────────────────
def vent(name, w, h, matrix=None, kind="slats", count=None, depth=12.0, target=None,
         collection=None, corner=3.0):
    """Recessed vent. kind 'slats' (angled louvres) or 'mesh' (alpha-tested mesh
    over a dark cavity). Returns dict(bezel, slats|mesh, back)."""
    matrix = matrix or Matrix.Identity(4)
    if target is not None:
        cut = P.prism(P.rrect(w + 1.0, h + 1.0, corner + 0.5), -depth, 6.0)
        boolean_cut(target, cutter(cut, matrix), lip=0.35)
    out = {}
    bz = P.ring_solid(P.rrect(w + 9.0, h + 9.0, corner + 4.5), P.rrect(w - 1.0, h - 1.0, corner), -3.0, 1.2)
    out["bezel"] = obj_from_bm(name + "_Bezel", bz, matrix, collection, M.get("alu"), bevel=0.5)
    out["back"] = obj_from_bm(name + "_Cavity", P.prism(P.rrect(w, h, corner), -depth + 0.2, -depth + 1.2),
                              matrix, collection, M.get("cavity"), bevel=0.0)
    if kind == "slats":
        n = count or max(3, round(h / 9.0))
        pitch = h / n
        bm = bmesh.new()
        for i in range(n):
            blade = P.box(w - 0.6, 1.4, min(depth - 2.0, pitch * 1.25))
            P.merge(bm, blade, T(0, -h / 2 + pitch * (i + 0.5), -depth * 0.42) @ R("X", 58))
        out["slats"] = obj_from_bm(name + "_Louvres", bm, matrix, collection, M.get("alu"),
                                   bevel=0.25, segments=1)
    else:
        bm = bmesh.new()
        uv = bm.loops.layers.uv.new("UVMap")
        vs = [bm.verts.new((x, y, -2.0)) for x, y in P.rrect(w - 0.6, h - 0.6, corner)]
        f = bm.faces.new(vs)
        for loop in f.loops:
            loop[uv].uv = (loop.vert.co.x * MM, loop.vert.co.y * MM)
        out["mesh"] = obj_from_bm(name + "_Mesh", bm, matrix, collection, M.get("mesh"), bevel=0.0)
    return out


# ── hinges, hatches ──────────────────────────────────────────────────────────
def hinge_bm(pin_d=3.0, length=60.0, knuckles=5, leaf=0.0):
    """Hinge barrel along Y, centred at the origin. Slot 0 body, slot 1 pin."""
    od = pin_d * 2.3
    k = length / knuckles
    bm = bmesh.new()
    for i in range(knuckles):
        c = P.revolve(P.ring_profile(pin_d / 2, od / 2, -k / 2 + 0.25, k / 2 - 0.25, 0.3),
                      P.auto_segs(od * 2))
        P.merge(bm, c, T(0, -length / 2 + k * (i + 0.5), 0) @ R("X", 90))
    pin = P.revolve([(0, -length / 2 - 1.2), (pin_d * 0.7, -length / 2 - 1.2), (pin_d * 0.7, -length / 2),
                     (pin_d / 2, -length / 2), (pin_d / 2, length / 2), (pin_d * 0.7, length / 2),
                     (pin_d * 0.7, length / 2 + 1.2), (0, length / 2 + 1.2)], P.auto_segs(od * 2))
    P.merge(bm, pin, R("X", 90), mat_index=1)
    if leaf:
        for sgn in (1, -1):
            lf = P.box(leaf, length, 1.2)
            P.merge(bm, lf, T(sgn * (leaf / 2 + pin_d * 0.3), 0, -od / 2 + 0.6))
    return bm


def hinge(name, pin_d=3.0, length=60.0, knuckles=5, leaf=0.0, matrix=None, collection=None):
    return obj_from_bm(name, hinge_bm(pin_d, length, knuckles, leaf), matrix, collection,
                       [M.get("alu"), M.get("steel")], bevel=0.0)


def hatch(name, w, h, matrix=None, target=None, hinge_side="L", fasteners=3, thickness=3.0,
          gap=1.5, corner=5.0, collection=None, material="armour"):
    """Flush service hatch: door in a pocket with an even gap, a hinge down one
    side and quarter-turn fasteners down the other. Returns dict(door, hinge, fasteners)."""
    matrix = matrix or Matrix.Identity(4)
    if target is not None:
        pocket = P.prism(P.rrect(w + 2 * gap, h + 2 * gap, corner + gap), -(thickness + 0.6), 6.0)
        boolean_cut(target, cutter(pocket, matrix), lip=0.3)
    out = {}
    out["door"] = obj_from_bm(name + "_Door", P.prism(P.rrect(w, h, corner), -thickness, 0.0), matrix,
                              collection, M.get(material), bevel=0.5)
    sgn = -1 if hinge_side == "L" else 1
    out["hinge"] = hinge(name + "_Hinge", 3.0, h * 0.72, 5, 0.0,
                         matrix @ T(sgn * (w / 2 + gap / 2), 0, 1.6), collection)
    x = -sgn * (w / 2 - 9.0)
    seats = mech.row((x, -h / 2 + 10.0, 0.0), (x, h / 2 - 10.0, 0.0), fasteners, (0, 0, 1))
    out["fasteners"] = mech.fasteners(name + "_Quarter_Turns", seats, "M6", "quarter",
                                      collection=collection, matrix=matrix)
    return out


# ── lifting eye ──────────────────────────────────────────────────────────────
def lifting_eye_bm(d=34.0):
    """Collared eye bolt: seat at z=0, eye plane = XZ."""
    bar = d * 0.28
    bm = P.revolve([(0, 0), (d * 0.42, 0), (d * 0.42, 2.0), (d * 0.36, 3.0), (d * 0.36, 3.0), (0, 3.0)],
                   P.auto_segs(d))
    P.merge(bm, P.cyl(d * 0.62, d * 0.2, 6), T(0, 0, 3.0 + d * 0.1))
    P.merge(bm, P.cyl(bar * 1.3, d * 0.2), T(0, 0, 3.0 + d * 0.28))
    P.merge(bm, P.torus(d, bar, 40, 12), T(0, 0, 3.0 + d * 0.2 + d / 2 + bar * 0.2) @ R("X", 90))
    return bm


def lifting_eye(name, matrix=None, d=34.0, collection=None):
    return obj_from_bm(name, lifting_eye_bm(d), matrix, collection, M.get("ti"), bevel=0.0)


# ── decal labels ─────────────────────────────────────────────────────────────
_FONT = None
_METRICS = {}


def font():
    global _FONT
    from pathlib import Path
    try:
        if _FONT is not None and _FONT.name:
            return _FONT
    except ReferenceError:
        pass
    path = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "SairaStencilOne-Regular.ttf"
    _FONT = bpy.data.fonts.load(str(path))
    return _FONT


def text_metrics(text):
    """(width, height, centre x, centre y) of `text` at size 1.0 in the stencil
    face, measured from the real glyph outlines."""
    if text in _METRICS:
        return _METRICS[text]
    cu = bpy.data.curves.new("_measure", "FONT")
    cu.body = text
    cu.font = font()
    cu.size = 1.0
    ob = bpy.data.objects.new("_measure", cu)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    xs = [c[0] for c in ob.bound_box]
    ys = [c[1] for c in ob.bound_box]
    out = (max(xs) - min(xs), max(ys) - min(ys), (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2)
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    _METRICS[text] = out
    return out


def text_size(text):
    return text_metrics(text)[:2]


def label(name, text, height=8.0, matrix=None, color="white", target=None, collection=None,
          offset=0.12, aspect=None):
    """Decal quad carrying `text` with cap height `height` mm, centred on the
    local origin, text reading along +X, facing +Z. With a target it is draped
    onto the surface. Texture comes from the decal atlas (markings.build_atlas).
    With `aspect` (width / height) the quad is a picture `height` mm tall and
    `text` names the drawing in markings.PICTURES."""
    matrix = matrix or Matrix.Identity(4)
    if aspect:
        pad, w, h = 0.0, height * aspect, height
    else:
        tw, th = text_size(text)
        k = height / th
        pad = height * 0.25
        w, h = tw * k + 2 * pad, height + 2 * pad
    nx = max(1, round(w / 10.0)) if target is not None else 1
    ny = 2 if target is not None else 1
    if aspect and target is not None:                # a picture is tall: follow the surface in both directions
        nx, ny = max(1, round(w / 3.0)), max(1, round(h / 3.0))
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    grid = [[bm.verts.new((-w / 2 + w * i / nx, -h / 2 + h * j / ny, offset)) for i in range(nx + 1)]
            for j in range(ny + 1)]
    for j in range(ny):
        for i in range(nx):
            f = bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
            for loop in f.loops:
                c = loop.vert.co
                loop[uv].uv = ((c.x + w / 2) / w, (c.y + h / 2) / h)
    bm.transform(matrix)
    if target is not None:
        bvh = _bvh(target)
        nrm = (matrix.to_3x3() @ Vector((0, 0, 1))).normalized()
        for v in bm.verts:
            hit = bvh.ray_cast((v.co + nrm * 25.0) * MM, -nrm, 0.06)
            if hit[0] is not None:
                v.co = hit[0] / MM + hit[1].normalized() * offset
    ob = obj_from_bm(name, bm, None, collection, None, bevel=0.0)
    for m in list(ob.modifiers):
        ob.modifiers.remove(m)
    ob["rj28_decal"] = True
    DECALS.append(dict(obj=ob, text=text, color=color, w=w, h=h, pad=pad, cap=height))   # the object itself: it gets renamed on registration
    return ob
