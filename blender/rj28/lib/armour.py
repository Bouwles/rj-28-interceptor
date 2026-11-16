"""Armour and shell construction. Dimensions mm.

Armour on this robot is thick, smooth and single-curvature: flat faces joined
by generous radii, with crisp bevelled edges where a panel stops. Panels are
real ~10 mm solids on carriers, separated by even 2 mm gaps.
"""
import bmesh
import bpy
from mathutils import Matrix, Vector

from . import prims as P
from .core import MM, T, add_bevel, boolean_cut, cutter, shade

GAP = 2.0
PLATE = 10.0


def rsec(z, w, d, dx=0.0, dy=0.0, r=30.0, n=5):
    """Rounded-rectangle section: w along X, d along Y, corner radius r (mm), at height z.
    Always 4 * (n + 1) points, so sections with different sizes loft cleanly."""
    return [(x + dx, y + dy, z) for x, y in P.rrect(w, d, max(r, 0.5), n)]


def csec(z, w, d, dx=0.0, dy=0.0, c=0.2):
    """Chamfered-rectangle (octagon) section; c is the chamfer as a fraction of each side."""
    h = 0.5
    pts = [(h - c, -h), (h, -h + c), (h, h - c), (h - c, h), (-h + c, h), (-h, h - c), (-h, -h + c), (-h + c, -h)]
    return [(x * w + dx, y * d + dy, z) for x, y in pts]


def shell(sections, thickness=PLATE, capped=False):
    """Hollow armour shell skinned over sections (open at both ends unless capped),
    thickened inward so the designed outline is the outer surface."""
    bm = P.loft(sections, cap=capped)
    return P.thicken(bm, thickness)


def solid(sections):
    """Closed solid skinned over sections."""
    return P.loft(sections, cap=True)


def gap_cut(target, point, normal, gap=GAP, size=1500.0, lip=0.5):
    """Slice a panel gap through target with a slab of the given width."""
    from .core import frame
    slab = P.box(size, size, gap)
    return boolean_cut(target, cutter(slab, frame(point, normal)), lip=lip)


def islands(ob):
    """Split an object into one object per connected piece (after gap cuts).
    Returns the pieces sorted by centroid (z, then x, then y). Modifiers,
    materials and custom properties carry over."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    seen, groups = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        seen.add(v.index)
        stack, comp = [v], []
        while stack:
            u = stack.pop()
            comp.append(u.index)
            for e in u.link_edges:
                w = e.other_vert(u)
                if w.index not in seen:
                    seen.add(w.index)
                    stack.append(w)
        groups.append(comp)
    if len(groups) == 1:
        bm.free()
        return [ob]
    bevel = float(ob.get("bevel_mm", 0.0))
    segs = next((m.segments for m in ob.modifiers if m.type == "BEVEL"), 2)
    out = []
    for comp in groups:
        keep = set(comp)
        b2 = bm.copy()
        bmesh.ops.delete(b2, geom=[v for v in b2.verts if v.index not in keep], context="VERTS")
        me = bpy.data.meshes.new(ob.name)
        b2.to_mesh(me)
        c = sum((v.co for v in b2.verts), Vector()) / max(1, len(b2.verts))
        b2.free()
        new = bpy.data.objects.new(ob.name, me)
        for col in ob.users_collection:
            col.objects.link(new)
        for m in ob.data.materials:
            me.materials.append(m)
        for k in ob.keys():
            if k not in {"_RNA_UI"}:
                new[k] = ob[k]
        shade(me)
        add_bevel(new, bevel, segs)
        out.append((round(c.z, 4), round(c.x, 4), round(c.y, 4), new))
    bm.free()
    old = ob.data
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(old)
    out.sort(key=lambda t: t[:3])
    return [t[3] for t in out]


def hoops(secs, levels, band=14.0, thickness=3.0, inset=10.6):
    """Carrier hoops lining the inside of a shell built from `secs`, at the given
    heights. One bmesh, same local frame as the shell."""
    from . import detail as D
    bm = bmesh.new()
    for zc in levels:
        i = next(k for k in range(len(secs) - 1)
                 if min(secs[k][0][2], secs[k + 1][0][2]) <= zc <= max(secs[k][0][2], secs[k + 1][0][2]))
        z0, z1 = secs[i][0][2], secs[i + 1][0][2]
        rings = []
        for z in (zc + band / 2, zc - band / 2):
            t = (z - z0) / (z1 - z0)
            rings.append([tuple(Vector(p) * (1 - t) + Vector(q) * t) for p, q in zip(secs[i], secs[i + 1])])
        P.merge(bm, D.rib_ring_bm(rings, thickness, inset))
    return bm


def opening(target, outline, matrix, depth=40.0, above=20.0, lip=0.5):
    """Cut an opening through/into target: outline (2D, mm) in the XY plane of
    matrix, cutting from +above down to -depth along its Z."""
    return boolean_cut(target, cutter(P.prism(outline, -depth, above), matrix), lip=lip)


def recess(target, outline, matrix, depth=3.0, lip=0.4):
    """Shallow pocket (for flush hatches, plates, labels)."""
    return boolean_cut(target, cutter(P.prism(outline, -depth, 20.0), matrix), lip=lip)


def slots(target, matrix, count, length, width, pitch, depth=30.0, lip=0.3):
    """Row of rounded vent slots: slot length along local X, stacked along local Y,
    cut along local -Z from the surface."""
    cut = bmesh.new()
    for i in range(count):
        y = (i - (count - 1) / 2) * pitch
        P.merge(cut, P.prism(P.rrect(length, width, width / 2 - 0.01, 4), -depth, 10.0), T(0, y, 0))
    return boolean_cut(target, cutter(cut, matrix), lip=lip)
