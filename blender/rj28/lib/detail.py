"""Secondary mechanical detail: machined pockets, links, covers, sensors, stops.
Dimensions mm. Everything here has a job on the robot; nothing is decoration.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import prims as P
from .core import MM, T, R, boolean_cut, cutter, frame


def seats_on(target, points, direction, x_hint=(0, 0, 1)):
    """Drop points onto target's surface along -direction. Returns placement
    matrices (mm) with +Z on the surface normal, ready for mech.fasteners."""
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    bvh = BVHTree.FromObject(target, dg)
    d = Vector(direction).normalized()
    out = []
    for p in points:
        hit = bvh.ray_cast((Vector(p) + d * 60.0) * MM, -d, 0.6)
        if hit[0] is None:
            continue
        n = hit[1].normalized()
        if n.dot(d) < 0:
            n = -n
        out.append(frame(hit[0] / MM, n, x_hint))
    return out


def pocket_grid(target, matrix, nx, ny, w, h, px, py, depth=5.0, r=None, lip=0.35):
    """Machined lightening pockets: nx x ny rounded rectangles (w x h) on pitches
    (px, py) in the XY plane of matrix, cut `depth` deep along its -Z."""
    r = min(w, h) * 0.28 if r is None else r
    cut = bmesh.new()
    for i in range(nx):
        for j in range(ny):
            x = (i - (nx - 1) / 2) * px
            y = (j - (ny - 1) / 2) * py
            P.merge(cut, P.prism(P.rrect(w, h, r, 4), -depth, 12.0), T(x, y, 0))
    return boolean_cut(target, cutter(cut, matrix), lip=lip)


def link_bm(length, r=10.0, hole_r=4.0, t=6.0):
    """Dog-bone link in the XY plane: pivots at x=0 and x=length, thickness along Z."""
    bm = P.lug(r, hole_r, length / 2 + 0.01, t, 24)
    bm.transform(R("Z", 180))
    other = P.lug(r, hole_r, length / 2 + 0.01, t, 24)
    P.merge(bm, other, T(length, 0, 0))
    return bm


def link_between(p0, p1, axis, r=10.0, hole_r=4.0, t=6.0):
    """Link bm placed in world space between two pivot points; pivots turn about `axis`."""
    p0, p1 = Vector(p0), Vector(p1)
    x = (p1 - p0)
    L = x.length
    x.normalize()
    z = Vector(axis) - x * x.dot(Vector(axis))
    z.normalize()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = p0
    bm = link_bm(L, r, hole_r, t)
    bm.transform(m)
    return bm


def bolted_cover_profile(r, t, bore=0.0, land=13.0, boss=5.0):
    """(r, z) profile of a round bearing cover: flat bolt land at the rim, raised
    boss in the middle. Returns (profile, bolt_circle_radius, land_z)."""
    c = 3.0
    prof = [(bore, 0.0), (r, 0.0), (r, t - c), (r - c, t), (r - land, t), (r - land - boss, t + boss),
            (bore, t + boss)]
    return prof, r - c / 2 - land / 2, t


def encoder_bm(d=44.0):
    """Joint encoder: flat puck with a cable gland on its edge. Seat at z=0, +Z out.
    Slot 0 housing, slot 1 gland."""
    r = d / 2
    bm = P.revolve([(0, 0), (r, 0), (r, 6.0), (r - 2.0, 8.5), (r * 0.5, 8.5), (r * 0.45, 10.0), (0, 10.0)],
                   P.auto_segs(d))
    gland = P.revolve([(0, 0), (4.5, 0), (4.5, 7), (6, 8), (6, 13), (3.4, 15), (0, 15)], 12)
    P.merge(bm, gland, T(r - 1.0, 0, 4.2) @ R("Y", 90), mat_index=1)
    return bm


def hard_stop_bm(w=30.0, h=22.0, t=18.0):
    """Hard stop block with a rubber bumper face. Mount face z=0, bumper faces +X.
    Slot 0 block, slot 1 bumper."""
    bm = P.prism(P.chamfer_poly(P.rrect(t, w), [0, 5, 5, 0]), 0.0, h)
    pad = P.prism(P.rrect(4.0, w - 8.0, 1.5, 3), 3.0, h - 3.0)
    P.merge(bm, pad, T(t / 2 + 1.6, 0, 0), mat_index=1)
    return bm


def rib_ring_bm(sections, thickness=3.0, inset=10.5):
    """Thin carrier rib that follows the inside of an armour shell: sections are the
    same outline points as the shell, shrunk by `inset` towards their centroid."""
    bm = P.loft(sections, cap=False)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    c = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
    sign = 1.0 if sum((v.co - c).dot(v.normal) for v in bm.verts) >= 0 else -1.0
    for v in bm.verts:
        n = v.normal * sign
        v.co -= n * inset * v.calc_shell_factor()
    return P.thicken(bm, thickness)


def finned_block_bm(w, d, h, fins=8, fin_h=None, base=None):
    """Heat sink: base slab w x d with `fins` plate fins running along Y, total height h."""
    fin_h = fin_h or h * 0.6
    base = base or h - fin_h
    bm = P.box(w, d, base)
    bm.transform(T(0, 0, base / 2))
    pitch = w / fins
    for i in range(fins):
        f = P.box(pitch * 0.42, d - 2.0, fin_h + 0.5)
        P.merge(bm, f, T(-w / 2 + pitch * (i + 0.5), 0, base + fin_h / 2 - 0.25))
    return bm
