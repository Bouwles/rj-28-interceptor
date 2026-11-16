"""bmesh construction primitives. All dimensions in mm, all return a BMesh in
local coordinates (hand it to core.obj_from_bm with a placement matrix)."""
import math

import bmesh
import bpy
from mathutils import Vector


def auto_segs(d):
    for lim, n in ((8, 12), (16, 16), (32, 24), (60, 32), (120, 48), (220, 64)):
        if d < lim:
            return n
    return 96


# ── 2D outlines (lists of (x, y), counter-clockwise) ─────────────────────────
def rrect(w, h, r=0.0, n=5):
    if r <= 0:
        return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    r = min(r, w / 2 - 1e-3, h / 2 - 1e-3)
    pts = []
    for cx, cy, a0 in ((w / 2 - r, -h / 2 + r, -90), (w / 2 - r, h / 2 - r, 0),
                       (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def circle(d, n=None, phase=0.0):
    n = n or auto_segs(d)
    return [(d / 2 * math.cos(phase + 2 * math.pi * i / n),
             d / 2 * math.sin(phase + 2 * math.pi * i / n)) for i in range(n)]


def superellipse(w, h, exp=2.5, n=48):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        c, s = math.cos(a), math.sin(a)
        pts.append((w / 2 * math.copysign(abs(c) ** (2 / exp), c),
                    h / 2 * math.copysign(abs(s) ** (2 / exp), s)))
    return pts


def round_poly(pts, r, n=4):
    """Fillet polygon corners. r: one radius or one per corner (0 = keep sharp)."""
    rs = r if isinstance(r, (list, tuple)) else [r] * len(pts)
    out = []
    m = len(pts)
    for i, p in enumerate(pts):
        P = Vector(p)
        A = Vector(pts[i - 1]) - P
        B = Vector(pts[(i + 1) % m]) - P
        rad = rs[i]
        if rad <= 0:
            out.append((P.x, P.y))
            continue
        la, lb = A.length, B.length
        u, v = A / la, B / lb
        phi = math.acos(max(-1.0, min(1.0, u.dot(v))))
        if phi > math.pi - 1e-3:
            out.append((P.x, P.y))
            continue
        t = min(rad / math.tan(phi / 2), 0.45 * la, 0.45 * lb)
        rad = t * math.tan(phi / 2)
        C = P + (u + v).normalized() * (rad / math.sin(phi / 2))
        a0 = math.atan2((P + u * t - C).y, (P + u * t - C).x)
        a1 = math.atan2((P + v * t - C).y, (P + v * t - C).x)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for k in range(n + 1):
            a = a0 + da * k / n
            out.append((C.x + rad * math.cos(a), C.y + rad * math.sin(a)))
    return out


def chamfer_poly(pts, c):
    """Cut every polygon corner by distance c (or per-corner list)."""
    cs = c if isinstance(c, (list, tuple)) else [c] * len(pts)
    out = []
    m = len(pts)
    for i, p in enumerate(pts):
        P = Vector(p)
        A = Vector(pts[i - 1]) - P
        B = Vector(pts[(i + 1) % m]) - P
        d = min(cs[i], 0.45 * A.length, 0.45 * B.length)
        if d <= 0:
            out.append((P.x, P.y))
            continue
        a = P + A.normalized() * d
        b = P + B.normalized() * d
        out += [(a.x, a.y), (b.x, b.y)]
    return out


def mirror_x(pts):
    """Right-half outline (x >= 0, listed bottom to top) -> full symmetric CCW outline."""
    left = [(-x, y) for x, y in reversed(pts) if abs(x) > 1e-6]
    return list(pts) + left


# ── solids ───────────────────────────────────────────────────────────────────
def box(sx, sy, sz):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    return bm


def cyl(d, h, segs=None, d2=None):
    """Cylinder/cone along Z, centred. d at -Z end, d2 at +Z end."""
    bm = bmesh.new()
    d2 = d if d2 is None else d2
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False,
                          segments=segs or auto_segs(max(d, d2)),
                          radius1=d / 2, radius2=d2 / 2, depth=h)
    return bm


def prism(outline, z0, z1):
    """Extrude a 2D outline between z0 and z1."""
    bm = bmesh.new()
    lo = [bm.verts.new((x, y, z0)) for x, y in outline]
    hi = [bm.verts.new((x, y, z1)) for x, y in outline]
    n = len(outline)
    bm.faces.new(lo[::-1])
    bm.faces.new(hi)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    return bm


def loft(sections, cap=True, wrap=False, bm=None):
    """Skin a list of closed 3D point rings (equal counts). wrap joins last to first."""
    bm = bm or bmesh.new()
    rings = [[bm.verts.new(p) for p in sec] for sec in sections]
    n = len(rings[0])
    pairs = list(zip(rings, rings[1:]))
    if wrap:
        pairs.append((rings[-1], rings[0]))
    for a, b in pairs:
        for j in range(n):
            k = (j + 1) % n
            bm.faces.new((a[j], a[k], b[k], b[j]))
    if cap and not wrap:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    return bm


def at_z(outline, z, sx=1.0, sy=1.0, dx=0.0, dy=0.0):
    """Lift a 2D outline to 3D at height z with optional scale/offset."""
    return [(x * sx + dx, y * sy + dy, z) for x, y in outline]


def taper(outline, z0, z1, s0=(1, 1), s1=(1, 1), o0=(0, 0), o1=(0, 0)):
    """Frustum: the same outline scaled/offset differently at each end."""
    return loft([at_z(outline, z0, s0[0], s0[1], o0[0], o0[1]),
                 at_z(outline, z1, s1[0], s1[1], o1[0], o1[1])])


def ring_solid(outer, inner, z0, z1):
    """Plate with a hole: outer and inner outlines must have equal point counts."""
    return loft([at_z(inner, z0), at_z(outer, z0), at_z(outer, z1), at_z(inner, z1)],
                cap=False, wrap=True)


def revolve(profile, segs=48, angle=360.0, bm=None):
    """Spin a closed (r, z) profile about Z. Points on the axis (r=0) are welded."""
    bm = bm or bmesh.new()
    n = len(profile)
    full = abs(angle - 360.0) < 1e-6
    steps = segs if full else segs + 1
    rings = []
    for i in range(steps):
        a = math.radians(angle) * i / segs
        c, s = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((r * c, r * s, z)) for r, z in profile])
    for i in range(segs):
        a, b = rings[i], rings[(i + 1) % steps]
        for j in range(n):
            k = (j + 1) % n
            if profile[j][0] == 0 and profile[k][0] == 0:
                continue
            bm.faces.new((a[j], b[j], b[k], a[k]))
    if not full:
        bm.faces.new(rings[0])
        bm.faces.new(rings[-1][::-1])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    return bm


def ring_profile(r0, r1, z0, z1, c=0.5):
    """Chamfered rectangle in the (r, z) plane, for revolve()."""
    c = min(c, (r1 - r0) / 2.01, (z1 - z0) / 2.01)
    return [(r0 + c, z0), (r1 - c, z0), (r1, z0 + c), (r1, z1 - c),
            (r1 - c, z1), (r0 + c, z1), (r0, z1 - c), (r0, z0 + c)]


def tube(od, id_, h, c=0.5, segs=None):
    return revolve(ring_profile(id_ / 2, od / 2, -h / 2, h / 2, c), segs or auto_segs(od))


def torus(major_d, minor_d, segs=None, ring=12):
    R, r = major_d / 2, minor_d / 2
    prof = [(R + r * math.cos(2 * math.pi * i / ring), r * math.sin(2 * math.pi * i / ring))
            for i in range(ring)]
    return revolve(prof, segs or auto_segs(major_d))


def lug(outer_r, hole_r, length, thickness, n=32):
    """Flat lug: round end with a hole at the origin, square root at x = -length.
    Lies in XY, thickness along Z (centred)."""
    corner = math.atan2(outer_r, -length)
    angs = sorted(set([2 * math.pi * i / n - math.pi for i in range(n)] + [corner, -corner]))
    outer, inner = [], []
    for a in angs:
        c, s = math.cos(a), math.sin(a)
        if c >= 0:
            r = outer_r
        else:
            r = min(length / -c, outer_r / abs(s) if abs(s) > 1e-9 else 1e9)
        outer.append((r * c, r * s))
        inner.append((hole_r * c, hole_r * s))
    return ring_solid(outer, inner, -thickness / 2, thickness / 2)


def dome(w, l, h, segs=48, rings=10, exp_plan=2.2, exp_side=2.4, z_base=0.0):
    """Half superellipsoid: w along X, l along Y, h tall. Open surface (no base)."""
    bm = bmesh.new()
    plan = superellipse(w, l, exp_plan, segs)
    rows = []
    for j in range(rings):
        t = j / rings                       # 0 at base, 1 at pole
        a = t * math.pi / 2
        k = math.cos(a) ** (2 / exp_side)
        z = z_base + h * math.sin(a) ** (2 / exp_side)
        rows.append([bm.verts.new((x * k, y * k, z)) for x, y in plan])
    top = bm.verts.new((0, 0, z_base + h))
    for a, b in zip(rows, rows[1:]):
        for i in range(segs):
            k = (i + 1) % segs
            bm.faces.new((a[i], a[k], b[k], b[i]))
    for i in range(segs):
        bm.faces.new((rows[-1][i], rows[-1][(i + 1) % segs], top))
    return bm


# ── operations ───────────────────────────────────────────────────────────────
def thicken(bm, t):
    """Turn an open surface into a solid shell by offsetting inward by t."""
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    verts, faces = bm.verts[:], bm.faces[:]
    bound = [e for e in bm.edges if e.is_boundary]
    new = {v: bm.verts.new(v.co - v.normal * t * v.calc_shell_factor()) for v in verts}
    for f in faces:
        bm.faces.new([new[v] for v in reversed(f.verts)])
    for e in bound:
        a, b = e.verts
        bm.faces.new((a, b, new[b], new[a]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def slice_axis(bm, axis, n):
    """Cut the mesh by n-1 evenly spaced planes perpendicular to axis (0=X,1=Y,2=Z)."""
    vals = [v.co[axis] for v in bm.verts]
    lo, hi = min(vals), max(vals)
    no = [0, 0, 0]
    no[axis] = 1
    for k in range(1, n):
        co = [0, 0, 0]
        co[axis] = lo + (hi - lo) * k / n
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                               dist=1e-6, plane_co=co, plane_no=no)
    return lo, hi


def bend(bm, axis, sagitta, slices=12):
    """Cylindrical crown: bow the mesh upward (+Z) across `axis` (0=X or 1=Y) so the
    middle rises by `sagitta` while the ends stay put. Thickness is preserved."""
    if not sagitta:
        return bm
    lo, hi = slice_axis(bm, axis, slices)
    half, mid = (hi - lo) / 2, (hi + lo) / 2
    s = abs(sagitta)
    rad = (half * half + s * s) / (2 * s)
    sign = 1 if sagitta > 0 else -1
    z_edge = rad * math.cos(half / rad)
    for v in bm.verts:
        th = (v.co[axis] - mid) / rad
        rr = rad + sign * v.co.z
        v.co[axis] = mid + rr * math.sin(th)
        v.co.z = sign * (rr * math.cos(th) - z_edge)
    return bm


def plate(outline, thickness, crown=0.0, crown_axis=0, crown2=0.0, slices=12):
    """Armour plate from a 2D outline. Outer face ends up at z = thickness (plus
    crown); crown/crown2 are sagittas across crown_axis and the other axis."""
    bm = prism(outline, 0.0, thickness)
    bend(bm, crown_axis, crown, slices)
    bend(bm, 1 - crown_axis, crown2, slices)
    return bm


def merge(dst, src, matrix=None, mat_index=None):
    """Append src into dst (optionally transformed / retagged); frees src."""
    if matrix is not None:
        src.transform(matrix)
    if mat_index is not None:
        for f in src.faces:
            f.material_index = mat_index
    me = bpy.data.meshes.new("_tmp")
    src.to_mesh(me)
    src.free()
    dst.from_mesh(me)
    bpy.data.meshes.remove(me)
    return dst


def catmull(points, step=6.0, sag=0.0):
    """Smooth polyline through 3D points (centripetal Catmull-Rom), sampled about
    every `step` mm. sag (mm, or one per span) droops each span along -Z."""
    P = [Vector(p) for p in points]
    if len(P) < 2:
        return P
    sags = sag if isinstance(sag, (list, tuple)) else [sag] * (len(P) - 1)
    ext = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = ext[i:i + 4]
        t0 = 0.0
        t1 = t0 + max((p1 - p0).length, 1e-6) ** 0.5
        t2 = t1 + max((p2 - p1).length, 1e-6) ** 0.5
        t3 = t2 + max((p3 - p2).length, 1e-6) ** 0.5
        n = max(2, int((p2 - p1).length / step))
        for k in range(n):
            u = k / n
            t = t1 + (t2 - t1) * u
            a1 = p0 * ((t1 - t) / (t1 - t0)) + p1 * ((t - t0) / (t1 - t0))
            a2 = p1 * ((t2 - t) / (t2 - t1)) + p2 * ((t - t1) / (t2 - t1))
            a3 = p2 * ((t3 - t) / (t3 - t2)) + p3 * ((t - t2) / (t3 - t2))
            b1 = a1 * ((t2 - t) / (t2 - t0)) + a2 * ((t - t0) / (t2 - t0))
            b2 = a2 * ((t3 - t) / (t3 - t1)) + a3 * ((t - t1) / (t3 - t1))
            c = b1 * ((t2 - t) / (t2 - t1)) + b2 * ((t - t1) / (t2 - t1))
            c.z -= sags[i] * 4 * u * (1 - u)
            out.append(c)
    out.append(P[-1].copy())
    return out


def sweep(path, radius, sides=10, cap=True, uv_scale=1.0):
    """Tube along a 3D polyline with rotation-minimising frames. radius may be a
    function of path parameter 0..1. Writes UVs (u around, v = length in m)."""
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    P = [Vector(p) for p in path]
    n = len(P)
    tang = [((P[min(i + 1, n - 1)] - P[max(i - 1, 0)]).normalized()) for i in range(n)]
    nrm = tang[0].orthogonal().normalized()
    rings, dist, d = [], [], 0.0
    for i in range(n):
        if i:
            d += (P[i] - P[i - 1]).length
            nrm = (nrm - tang[i] * nrm.dot(tang[i]))
            nrm = nrm.normalized() if nrm.length > 1e-9 else tang[i].orthogonal().normalized()
        bi = tang[i].cross(nrm)
        r = radius(i / (n - 1)) if callable(radius) else radius
        rings.append([bm.verts.new(P[i] + (nrm * math.cos(2 * math.pi * k / sides)
                                           + bi * math.sin(2 * math.pi * k / sides)) * r)
                      for k in range(sides)])
        dist.append(d)
    for i in range(n - 1):
        for k in range(sides):
            j = (k + 1) % sides
            f = bm.faces.new((rings[i][k], rings[i][j], rings[i + 1][j], rings[i + 1][k]))
            us = (k / sides, (k + 1) / sides, (k + 1) / sides, k / sides)
            vs = (dist[i], dist[i], dist[i + 1], dist[i + 1])
            for loop, u_, v_ in zip(f.loops, us, vs):
                loop[uv].uv = (u_ * uv_scale, v_ * 0.001 * uv_scale)
    if cap:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    return bm
