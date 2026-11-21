"""Assemblies 07 / 08: arm, left / right.

Shoulder roll actuator in its cradle, roll yoke, shoulder armour on its carrier,
shoulder yaw actuator, upper-arm member and half-shell, elbow joint, forearm frame
with the hand drive, forearm armour, forearm roll actuator and bearing. The
thorax owns the shoulder pitch actuator (output face at x = +/-(SX - 77)); the
hand (09 / 10) owns the wrist.

Frames (rj28.frames.arm, with the torso offset applied): upper-arm and forearm
frames have +X lateral, +Y to the rear and -Z running down the limb. "Outer"
is s * X. The elbow axis is local X at z = -UPPER_ARM of the upper-arm frame.

Shoulder armour. Three plates on one carrier: a top cap, a main outer plate
tucked 13 mm under the cap's lower edge, and a skirt lame hanging outside the
main plate on a full-length hinge. The carrier is a saddle screwed to the shoulder
roll housing (and, on the left, bolted to the end of the idler journal), so the
armour turns with shoulder pitch only. The plates are trays: 10 mm skin with an
edge return wherever an edge is free. Left and right are not mirror images: the
left is taller, longer, has a rear cheek and a long lame; the right is lower,
stops short at the rear where the mount swings, and has a short lame.

Kinematic notes
- Shoulder roll (abduction) turns the yoke and everything below it inside the
  fixed armour. The upper-arm armour (left) or the shoulder of the yaw housing
  (right) lifts the skirt lame on its hinge; about 15 degrees beyond the rest
  pose the yaw housing meets the lower edge of the main plate.
- Forearm roll is at the wrist end, so the forearm armour never turns against
  the elbow. The finger tendons pass through the hollow roll shaft.
- Elbow: 0 deg (stop) to about 105 deg of flexion before the forearm armour
  meets the upper-arm half-shell.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from .. import frames as FR, params as PR
from ..lib import armour as A, core as C, detail as D, fittings as F, harness as H, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm, raw

# forearm armour sections: (z, width, depth, dy, corner radius, crown of the side faces, crown of front and back)
FORE = [(-40, 150, 160, 0, 40, 5, 3), (-112, 192, 198, 4, 50, 7, 4), (-214, 176, 182, 2, 46, 7, 4),
        (-262, 134, 140, 0, 38, 4, 2)]


def _dir(m, v):
    return (m.to_3x3() @ Vector(v)).normalized()


def _local(m, ob):
    lo, hi = C.bounds_mm([ob])
    return m.inverted() @ ((lo + hi) / 2)


def _drop(ob):
    me = ob.data
    bpy.data.objects.remove(ob)
    if me.users == 0:
        bpy.data.meshes.remove(me)


def _copy(ob):
    c = ob.copy()
    c.data = ob.data.copy()
    for col in ob.users_collection:
        col.objects.link(c)
    return c


def _lerp(p, q, t):
    return tuple(a + (b - a) * t for a, b in zip(p, q))


def _round_polyline(pts, radii, n=5):
    """Fillet the interior corners of an open 2D polyline."""
    out = [tuple(pts[0])]
    for i in range(1, len(pts) - 1):
        p = Vector(pts[i])
        u = Vector(pts[i - 1]) - p
        v = Vector(pts[i + 1]) - p
        r = radii[i]
        if r <= 0:
            out.append(tuple(p))
            continue
        la, lb = u.length, v.length
        u, v = u / la, v / lb
        phi = math.acos(max(-1.0, min(1.0, u.dot(v))))
        t = min(r / math.tan(phi / 2), 0.45 * la, 0.45 * lb)
        r = t * math.tan(phi / 2)
        c = p + (u + v).normalized() * (r / math.sin(phi / 2))
        s0, s1 = p + u * t - c, p + v * t - c
        a0, a1 = math.atan2(s0.y, s0.x), math.atan2(s1.y, s1.x)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for k in range(n + 1):
            a = a0 + da * k / n
            out.append((c.x + r * math.cos(a), c.y + r * math.sin(a)))
    out.append(tuple(pts[-1]))
    return out


def _offset(pts, d):
    """Offset an open 2D polyline to its right-hand side by d (miter joins)."""
    q = [Vector(p) for p in pts]

    def nrm(a, b):
        t = (b - a).normalized()
        return Vector((t.y, -t.x))

    out = []
    for i in range(len(q)):
        if i == 0:
            m, k = nrm(q[0], q[1]), 1.0
        elif i == len(q) - 1:
            m, k = nrm(q[-2], q[-1]), 1.0
        else:
            n0, n1 = nrm(q[i - 1], q[i]), nrm(q[i], q[i + 1])
            m = (n0 + n1).normalized()
            k = 1.0 / max(0.3, m.dot(n0))
        out.append(tuple(q[i] + m * d * k))
    return out


def _isect(p1, p2, p3, p4):
    """Intersection of the 2D lines p1-p2 and p3-p4."""
    d1 = (p2[0] - p1[0], p2[1] - p1[1])
    d2 = (p4[0] - p3[0], p4[1] - p3[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    t = ((p3[0] - p1[0]) * d2[1] - (p3[1] - p1[1]) * d2[0]) / den
    return (p1[0] + d1[0] * t, p1[1] + d1[1] * t)


# ── armour plates as trays ────────────────────────────────────────────────────
def _skin(rows):
    """Open surface through rows of 3D points (equal counts)."""
    bm = bmesh.new()
    vs = [[bm.verts.new(p) for p in r] for r in rows]
    for a, b in zip(vs, vs[1:]):
        for j in range(len(a) - 1):
            bm.faces.new((a[j], a[j + 1], b[j + 1], b[j]))
    return bm


def _clip(bm, co, no):
    """Trim an open surface: everything on the side of the plane that `no` points to goes."""
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-4, plane_co=Vector(co),
                           plane_no=Vector(no).normalized(), clear_outer=True)


def _score(bm, co, no):
    """Split the faces of a surface along a plane without removing anything."""
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-4, plane_co=Vector(co),
                           plane_no=Vector(no).normalized())


def _tray(bm, t, lip, center, keep=None):
    """Armour plate from a trimmed skin: fold an edge return `lip` deep inward along the free edges
    (those whose midpoint passes `keep`), then give everything thickness t. `center` is a point on the inside."""
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.3)
    bmesh.ops.dissolve_degenerate(bm, dist=0.05, edges=bm.edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    c = Vector(center)
    if sum((f.calc_center_median() - c).dot(f.normal) * f.calc_area() for f in bm.faces) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
        bm.normal_update()
    if lip:
        edges = [e for e in bm.edges
                 if e.is_boundary and (keep is None or keep((e.verts[0].co + e.verts[1].co) / 2))]
        new = {}
        for e in edges:
            for v in e.verts:
                if v not in new:
                    new[v] = bm.verts.new(v.co - v.normal * lip)
        for e in edges:
            a, b = e.verts
            bm.faces.new((a, b, new[b], new[a]))
    return P.thicken(bm, t, center=center)


def _crown_sec(z, w, d, dx=0.0, dy=0.0, r=30.0, cx=0.0, cy=0.0, n=5, m=5):
    """Rounded-rectangle section with crowned faces: the side (X) faces bulge by cx and the front and back by cy
    at mid-span, running tangent into the corner radii. w and d are measured over the crowns.
    Always 4 * (n + 1 + m) points: per corner, its arc and then the face that follows it (+X, +Y, -X, -Y)."""
    hx, hy = w / 2 - cx, d / 2 - cy
    r = min(r, hx - 1.0, hy - 1.0)
    corners = ((hx - r, -hy + r, -90), (hx - r, hy - r, 0), (-hx + r, hy - r, 90), (-hx + r, -hy + r, 180))
    pts = []
    for k, (ox, oy, a0) in enumerate(corners):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((ox + r * math.cos(a), oy + r * math.sin(a)))
        p = pts[-1]
        qx, qy, qa = corners[(k + 1) % 4]
        q = (qx + r * math.cos(math.radians(qa)), qy + r * math.sin(math.radians(qa)))
        ux, uy = ((1, 0), (0, 1), (-1, 0), (0, -1))[k]
        c = cy if k % 2 else cx
        for i in range(1, m + 1):
            t = i / (m + 1)
            b = c * math.sin(math.pi * t) ** 2
            pts.append((p[0] + (q[0] - p[0]) * t + ux * b, p[1] + (q[1] - p[1]) * t + uy * b))
    return [(x + dx, y + dy, z) for x, y in pts]


def _fore_at(z):
    """Forearm section parameters at height z."""
    for a, b in zip(FORE, FORE[1:]):
        if b[0] <= z <= a[0]:
            t = (z - a[0]) / (b[0] - a[0])
            return [u + (v - u) * t for u, v in zip(a, b)]
    raise ValueError(z)


def _fore_sec(z, grow=0.0):
    _, w, d, dy, r, cx, cy = _fore_at(z)
    return _crown_sec(z, w + 2 * grow, d + 2 * grow, 0, dy, r + grow, cx, cy)


# ── elbow parts ───────────────────────────────────────────────────────────────
def _elbow_housing_bm():
    """Elbow actuator housing: clamp land in the middle, cooling fins either side."""
    r = 69.0
    prof = [(0, -62), (60, -62), (63, -59), (63, -53)]
    for z0 in (-52, -47, -42, -37):
        prof += [(61, z0), (61, z0 + 1.6), (r, z0 + 2.2), (r, z0 + 4.2)]
    prof += [(61, -32.5), (61, -31), (r, -30), (r, 30), (61, 31), (61, 32.5)]
    for z0 in (33, 38, 43, 48):
        prof += [(r, z0 - 0.2), (r, z0 + 1.8), (61, z0 + 2.4), (61, z0 + 4.0)]
    prof += [(63, 53), (63, 59), (60, 62), (0, 62)]
    return P.revolve(prof, 64)


def _half_clamp(lower):
    """Half of the split clamp around the elbow housing, with its bolt ears.
    Built on the elbow frame: axis X, split plane z = 0."""
    bm = P.revolve(P.ring_profile(69.3, 84.0, -27, 27, 1.0), 48, angle=180)
    bm.transform(R("Y", 90) @ R("Z", -90 if lower else 90))
    for o in (1, -1):
        P.merge(bm, P.box(54, 22, 13.5), T(0, o * 94, -6.75 if lower else 6.75))
    return bm


def _hub_cover_bm():
    """Elbow hub cover: six-lobed clamp plate. Seat at z = 0, +Z out; the lobes (and the bolts) are at
    0, 60, ... degrees."""
    lobes = []
    for k in range(120):
        a = math.radians(3 * k)
        rr = 44 + 11 * (0.5 + 0.5 * math.cos(6 * a)) ** 1.5
        lobes.append((rr * math.cos(a), rr * math.sin(a)))
    return P.prism(lobes, 0.0, 7.0)


def _hub_cap_bm():
    """Ribbed cap in the middle of the hub cover: shallow dome, centre boss, six ribs between the bolts.
    Sits on the cover's face at z = 7."""
    bm = P.revolve([(0, 6.5), (36, 6.5), (36, 9), (32, 11), (14, 11), (12, 18), (0, 18)], 48)
    for k in range(6):
        rib = P.prism([(11, 6.5), (40, 6.5), (40, 9.5), (13, 19), (11, 19)], -3.0, 3.0)
        P.merge(bm, rib, R("Z", 30 + 60 * k) @ R("X", 90))
    return bm


def _encoder_pod_bm():
    """Elbow encoder: read head on the axis and its electronics pod beside it, cable gland at the far end.
    Seat at z = 0, +Z out, pod towards +Y. Slot 0 housing, slot 1 gland."""
    bm = P.cyl(44, 8, 32)
    bm.transform(T(0, 0, 4))
    P.merge(bm, P.revolve([(0, 8), (14, 8), (12, 11), (0, 11)], 24))
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(34, 30), 4), 0, 13), T(0, 30, 0))
    P.merge(bm, P.prism(P.rrect(26, 22, 3), 13, 15), T(0, 30, 0))
    gland = P.revolve([(0, 0), (4.5, 0), (4.5, 7), (6, 8), (6, 13), (3.4, 15), (0, 15)], 12)
    P.merge(bm, gland, T(0, 45, 6.5) @ R("X", -90), mat_index=1)
    return bm


def build(s):
    a = Asm("07" if s > 0 else "08")
    n = "L" if s > 0 else "R"
    left = s > 0
    zp = f"pauldron_{n}"
    W = FR.torso()
    sv0, au0, af0, ah0 = FR.arm(s)
    Au, Af = W @ au0, W @ af0
    S = W @ sv0                                  # shoulder centre
    El = Au @ T(0, 0, -PR.UPPER_ARM)             # elbow, upper-arm orientation
    Ts = T(*S)
    sx = PR.SX
    zs = PR.Z_SHOULDER

    # ── shoulder roll actuator, held in a cradle on the pitch output ────────
    d = mech.rotary_actuator("_roll", 150, 122, Ts @ T(0, 61, 0) @ R("X", 90), bolts=0)
    _drop(d.pop("connector"))                    # its cable leaves on the axis instead (no twist in roll)
    a.take_rotary(d, "Shoulder_Roll", "shoulder roll")
    cr = a.add("Shoulder_Roll_Cradle", P.prism(P.rrect(27, 92, 9, 6), -46, 46),
               "Cradle clamping the shoulder roll housing to the shoulder pitch output.", "ti",
               Ts @ T(-s * 63.5, 8, 0), bevel=0.8)
    C.boolean_cut(cr, C.cutter(P.cyl(151.4, 240, 64), Ts @ R("X", 90)), lip=0.5)
    band = P.revolve(P.ring_profile(75.4, 79.5, -7, 7, 0.6), 64)
    P.merge(band, P.box(22, 12, 14), T(0, 84.5, 0))
    bandm = Ts @ T(0, -27, 0) @ R("X", 90)
    a.add("Shoulder_Roll_Clamp_Band", band, "Clamp band holding the shoulder roll housing down in its cradle.", "ti",
          bandm, bevel=0.5)
    a.take(mech.fasteners("_cb", [bandm @ T(s * 11, 84.5, 0) @ R("Y", s * 90)], "M6"), "Shoulder_Roll_Clamp_Screw",
           "Screw drawing the shoulder roll clamp band tight.")
    cn, _ = H.connector("_rc", S + Vector((0, 61, 0)), (0, 1, 0), 12.0)
    a.take(cn, "Shoulder_Roll_Connector", "Power and encoder connector on the shoulder roll axis.")
    jl = 14.0 if left else 9.4                                # the right one stays short: the mount swings close behind
    a.add("Shoulder_Roll_Idler_Journal", P.tube(59.6, 36, jl, 0.8),
          "Hollow journal on the back of the roll housing: the yoke's rear plate turns on it, the cable passes through it.",
          "steel", Ts @ T(0, 61 + jl / 2, 0) @ R("X", 90), bevel=0)

    # ── roll yoke: front plate on the output flange, rear plate on the idler, bridge below ──
    yk = bmesh.new()
    P.merge(yk, P.lug(62, 22, 102, 14, 40), frame((0, -71, 0), (0, 1, 0), (0, 0, 1)))
    P.merge(yk, P.lug(52, 30, 102, 8, 40), frame((0, 66, 0), (0, 1, 0), (0, 0, 1)))
    P.merge(yk, P.prism(P.chamfer_poly(P.rrect(150, 148), 14), -100, -84), T(0, -4, 0))
    yoke = a.add("Shoulder_Yoke", yk, "Roll yoke: hangs the arm from the shoulder roll output and its rear idler.", "ti",
                 Au, bevel=1.0)
    D.pocket_grid(yoke, Au @ T(0, -78.2, -70) @ R("X", 90), 1, 1, 70, 14, 0, 0, depth=5)
    for o in (1, -1):
        D.pocket_grid(yoke, Au @ T(o * 75.2, -3, -92) @ R("Y", o * 90), 1, 2, 8, 46, 0, 62, depth=5)
    seats = mech.ring((0, -78, 0), (0, -1, 0), 44, 10, x_hint=(1, 0, 0))
    a.take(mech.fasteners("_yb", seats, "M6", target=yoke, matrix=Au), "Shoulder_Yoke_Bolts",
           "Screws clamping the roll yoke to the shoulder roll output flange.")

    # ── shoulder armour ─────────────────────────────────────────────────────
    # Built in body coordinates with X = s * x (outboard positive), then mirrored into place by Mp.
    out = PR.PAULDRON_L_OUT if left else PR.PAULDRON_R_OUT
    top = PR.PAULDRON_TOP_Z - (0.0 if left else PR.PAULDRON_R_DROP)
    yf, yr = (-132.0, 118.0) if left else (-124.0, 20.0)      # right stops short at the rear to clear the mount
    zh, zl = (1388.0, 1296.0) if left else (1400.0, 1360.0)   # hinge line and lower edge of the skirt lame
    ymid = (yf + yr) / 2
    Mp = W @ Matrix.Diagonal((s, 1.0, 1.0, 1.0))

    def Bp(X, y, z):
        return W @ Vector((s * X, y, z))

    def Bd(X, y, z):
        return Vector((s * X, y, z)).normalized()

    # top cap: inner flank, top slab, outer shoulder, short outer wall; the ends fall away in a facet
    fk = 1.0 if left else 0.54                               # right flank stops short: it sits lower, close over the housing
    c0, c1, c2, c3 = (sx - 14 - 44 * fk, top - 54 * fk), (sx - 14, top), (out - 66, top), (out - 6, top - 54)
    wd = Vector((6.0, 1400.0 - c3[1])).normalized()
    c4 = (c3[0] + wd.x * 22, c3[1] + wd.y * 22)
    Xo, zc = c4                                               # lower outer edge of the cap
    prof = _round_polyline([c0, c1, c2, c3, c4], [0, 16, 30, 22, 0], 5)
    bm = _skin([[(X, y, z + dz) for X, z in prof] for y, dz in ((yf, -12), (yf + 28, 0), (yr - 28, 0), (yr, -12))])
    _clip(bm, (0, 0, zc), (0, 0, -1))
    _clip(bm, (c0[0], 0, c0[1]), (c0[0] - c1[0], 0, c0[1] - c1[1]))
    _clip(bm, (Xo - 28, yf, 0), (1, -1, 0))
    _clip(bm, (Xo - (28 if left else 44), yr, 0), (1, 1, 0))
    _clip(bm, (c0[0] + 18, yf, 0), (-1, -1, 0))
    _clip(bm, (c0[0] + 18, yr, 0), (-1, 1, 0))

    def cap_edge(m):                                          # no return where another plate or the housing is close
        return m.z > c3[1] + 3 and (left or not (m.y > yr - 30 and m.x < sx - 6))

    cap = a.add("Pauldron_Cap", _tray(bm, 10.0, 20.0, (sx + 30, ymid, zs), cap_edge),
                "Top cap of the shoulder armour, lapping over the main plate and both cheeks.", "armour", Mp,
                bevel=1.2, seg=3, zone=zp)

    # main outer plate: one calm face, tucked under the cap, wrapped in at the ends
    Xmc = Xo - 13.0
    km = (out - 13.5 - Xmc) / (zc - (zh + 2))

    def Xm(z):
        return Xmc + km * (zc - z)

    zlow = zh - 12
    ya0, yb0 = yf + 6, (yr - 6 if left else yr - 12)
    st = [(ya0, -10), (ya0 + 24, 0)] + ([(yb0 - 24, 0), (yb0, -10)] if left else [(yb0, 0)])
    bm = _skin([[(Xm(z) + dX, y, z) for z in (zc + 16, zlow)] for y, dX in st])
    _clip(bm, (0, ya0, zc - 22), (0, -1, 1))
    _clip(bm, (0, yb0, zc - (22 if left else 40)), (0, 1, 1))
    _clip(bm, (0, ya0, zlow + 18), (0, -1, -1))
    _clip(bm, (0, yb0, zlow + (18 if left else 10)), (0, 1, -1))
    main = a.add("Pauldron_Shell", _tray(bm, 10.0, 18.0, (sx, ymid, zs + 20), lambda m: zlow + 1 < m.z < zc + 15.5),
                 "Main outer plate of the shoulder armour; carries the unit designation on the left.", "armour", Mp,
                 bevel=1.2, seg=3, zone=zp)

    # skirt lame: hangs outside the main plate from a full-length hinge
    ly0, ly1 = (-96.0, 82.0) if left else (-88.0, -4.0)
    lyc = (ly0 + ly1) / 2
    lc = 22 if left else 12
    bm = _skin([[(out, y, z) for z in (zh - 2, zl)] for y in (ly0, ly1)])
    _clip(bm, (0, ly0, zl + lc), (0, -1, -1))
    _clip(bm, (0, ly1, zl + lc), (0, 1, -1))
    _score(bm, (0, 0, zh - 16), (0, 0, 1))
    lame = a.add("Pauldron_Skirt",
                 _tray(bm, 10.0, 16.0, (sx, lyc, (zh + zl) / 2),
                       lambda m: abs(m.y - lyc) > (ly1 - ly0) / 2 - 1 and m.z < zh - 16),
                 "Skirt lame of the shoulder armour: swings up on its hinge when the arm abducts.", "armour", Mp,
                 bevel=1.2, seg=3, zone=zp)
    hl = (ly1 - ly0) - 28
    a.add("Pauldron_Skirt_Hinge", F.hinge_bm(5.0, hl, 9 if left else 5, 0.0),
          "Hinge barrel and pin along the top of the skirt lame.", ["alu", "steel"], Mp @ T(out - 6, lyc, zh), bevel=0,
          zone=zp)
    leaf_o = [(out - 14.5, zh - 1.5), (out - 8, zh - 1.5), (out - 8, zh + 15), (out - 11, zh + 20), (out - 14.5, zh + 20)]
    leaf = a.add("Pauldron_Skirt_Hinge_Leaf", P.prism(leaf_o, -hl / 2, hl / 2),
                 "Fixed hinge leaf screwed to the main plate, carrying the skirt lame.", "ti",
                 Mp @ T(0, lyc, 0) @ R("X", 90), bevel=0.5, zone=zp)
    seats = [frame(Bp(out - 8, lyc + dy, zh + 9), Bd(1, 0, 0), (0, 1, 0))
             for dy in ((-57, -19, 19, 57) if left else (-17, 17))]
    a.take(mech.fasteners("_hs", seats, "M4", "csk", target=leaf), "Pauldron_Skirt_Hinge_Screws",
           "Countersunk screws fixing the hinge leaf to the main plate.", zone=zp)
    a.add("Pauldron_Skirt_Rub_Strip", P.box(3, max(30.0, (ly1 - ly0) - 60), 14),
          "Rubber strip on the back of the skirt lame where the arm bears on it in abduction.", "rubber",
          Mp @ T(out - 11.5, lyc, zl + 9), bevel=0.4, seg=1, zone=zp)

    # cheeks: flat end plates under the cap, arched to show the roll actuator
    def mline(off, z):
        return (Xm(z) - off, z)

    zb = 1404.0 if left else 1412.0
    Ra = 70.0
    fo = _offset([c0, c1, c2, c3], 14.0)
    x0 = max(sx - 34.0, fo[0][0] + 8.0)
    chk = [(x0, fo[0][1] + (fo[1][1] - fo[0][1]) * (x0 - fo[0][0]) / (fo[1][0] - fo[0][0])), fo[1], fo[2],
           _isect(fo[2], fo[3], mline(23, zc + 16), mline(23, zb)), mline(23, zb)]
    a_end = math.degrees(math.acos((x0 - sx) / Ra))
    chk += [(sx + Ra * math.cos(math.radians(-20 + (a_end + 20) * k / 24)),
             zs + Ra * math.sin(math.radians(-20 + (a_end + 20) * k / 24))) for k in range(25)]
    cheeks = [("Front", yf + 24, -1)] + ([("Rear", yr - 34, 1)] if left else [])
    cheek_obs = {}
    for tag, y0, fy in cheeks:
        cheek_obs[tag] = a.add(f"Pauldron_Cheek_{tag}", P.prism(chk, 0.0, 10.0),
                               f"{tag} cheek of the shoulder armour, arched to show the roll actuator.", "armour",
                               Mp @ T(0, y0 + 10, 0) @ R("X", 90), bevel=1.0, seg=3, zone=zp)

    # carrier: a saddle on the roll housing, a spine over it, a rib behind each cheek; on the left a rear
    # spoke to a hub bolted on the idler journal, on the right a short rib inside the rear edge
    def rib_path(off_main, z_end, flank=True):
        g = _offset([c0, c1, c2, c3], 16.5)
        j = _isect(g[2], g[3], mline(off_main, zc + 16), mline(off_main, z_end))
        return ([g[0], g[1]] if flank else [(sx + 16, g[1][1])]) + [g[2], j, mline(off_main, z_end)]

    ribs = [("Front", yf + 34, yf + 43, 20.0, 25.5, zh + 24, True)]
    ribs += [("Rear", yr - 43, yr - 34, 20.0, 25.5, zh + 24, True)] if left else [("Rear", -19, -10, 8.0, 21.0, zs - 14, False)]
    car = bmesh.new()
    rib_mid = {}
    for tag, y0, y1, bandw, off, z_end, flank in ribs:
        path = rib_path(off, z_end, flank)
        P.merge(car, P.prism(path + _offset(path, bandw)[::-1], 0.0, y1 - y0), T(0, y1, 0) @ R("X", 90))
        rib_mid[tag] = _offset(path, bandw / 2)
    gap = 12.0 if left else 8.0                               # spine top to the underside of the cap
    zsp = top - 10 - gap - 12
    ys, ye = ribs[0][1], ribs[1][2]
    P.merge(car, P.box(30, ye - ys, 12), T(sx + 31, (ys + ye) / 2, zsp + 6))
    r0, cw, yc = 75.4, (16.0 if left else 18.0), -48.0
    P.merge(car, P.revolve(P.ring_profile(r0, r0 + 10.6, -cw / 2, cw / 2, 0.8), 40, angle=108),
            T(sx, yc, zs) @ R("X", 90) @ R("Z", -8))      # saddle: from 8 deg below horizontal outboard, over the top
    rm = r0 + 5
    web = [(sx + 16, zs + math.sqrt(rm * rm - 16 * 16)), (sx + 46, zs + math.sqrt(rm * rm - 46 * 46)), (sx + 46, zsp + 2),
           (sx + 16, zsp + 2)]
    P.merge(car, P.prism(web, 0.0, cw), T(0, yc + cw / 2, 0) @ R("X", 90))
    if left:
        P.merge(car, P.tube(76, 36, 9, 0.8), T(sx, 79.5, zs) @ R("X", 90))
        P.merge(car, P.box(18, 9, (top - 30) - (zs + 34)), T(sx, 79.5, (top - 30 + zs + 34) / 2))
    carrier = a.add("Pauldron_Carrier", car,
                    "Carrier arm of the shoulder armour: saddle screwed to the roll housing, spine and ribs.", "ti", Mp,
                    bevel=0.8, zone=zp)
    seats = [frame(Bp(sx + (r0 + 10.6) * math.cos(q), yc, zs + (r0 + 10.6) * math.sin(q)),
                   Bd(math.cos(q), 0, math.sin(q)), (0, 1, 0)) for q in (math.radians(v) for v in (6, 32, 92))]
    a.take(mech.fasteners("_pcl", seats, "M6", target=carrier), "Pauldron_Carrier_Saddle_Screws",
           "Screws fixing the carrier saddle to the shoulder roll housing.", zone=zp)
    if left:
        seats = mech.ring(tuple(Bp(sx, 84, zs)), (0, 1, 0), 24, 6, x_hint=(0, 0, 1))
        a.take(mech.fasteners("_pch", seats, "M4", target=carrier), "Pauldron_Carrier_Hub_Screws",
               "Screws fixing the carrier's rear hub to the idler journal; the hub also retains the yoke.", zone=zp)
    else:
        rt = a.add("Shoulder_Roll_Idler_Retainer", P.tube(76, 36, 3.6, 0.5),
                   "Retaining plate screwed to the end of the idler journal, keeping the yoke's rear plate on it.", "ti",
                   Ts @ T(0, 72.2, 0) @ R("X", 90), bevel=0.3)
        seats = mech.ring(tuple(S + Vector((0, 74, 0))), (0, 1, 0), 24, 6, x_hint=(0, 0, 1))
        a.take(mech.fasteners("_ir", seats, "M4", "csk", target=rt), "Shoulder_Roll_Idler_Retainer_Screws",
               "Countersunk screws holding the idler retaining plate.")

    # standoffs between carrier and plates, and the screws through them
    so = bmesh.new()
    cap_pts = [(X, (ribs[0][1] + ribs[0][2]) / 2) for X in (sx + 4, out - 84)]
    cap_pts += [(X, (ribs[1][1] + ribs[1][2]) / 2) for X in ((sx + 4, out - 84) if left else (sx + 32,))]
    for X, y in cap_pts:
        P.merge(so, P.cyl(14, 6.5, 16), T(X, y, top - 13.25))
    main_pts = [((ribs[0][1] + ribs[0][2]) / 2, z, ribs[0][4]) for z in (zc - 14, zh + 34)]
    main_pts += [((ribs[1][1] + ribs[1][2]) / 2, z, ribs[1][4]) for z in ((zc - 14, zh + 34) if left else (zc - 42,))]
    for y, z, off in main_pts:
        P.merge(so, P.cyl(14, off - 10, 16), T(Xm(z) - 10 - (off - 10) / 2, y, z) @ R("Y", 90))
    a.add("Pauldron_Standoffs", so, "Standoff posts between the carrier and the cap and main plate.", "alu", Mp,
          bevel=0.4, seg=1, zone=zp)
    pts = [Bp(X, y, top + 60) for X, y in cap_pts]
    a.take(mech.fasteners("_ps", D.seats_on(cap, pts, (0, 0, 1), x_hint=(1, 0, 0)), "M6", target=cap),
           "Pauldron_Cap_Screws", "Screws fixing the top cap to the carrier.", zone=zp)
    pts = [Bp(out + 60, y, z) for y, z, _ in main_pts]
    a.take(mech.fasteners("_pm", D.seats_on(main, pts, Bd(1, 0, 0), x_hint=(0, 1, 0)), "M6", target=main),
           "Pauldron_Shell_Screws", "Screws fixing the main plate to the carrier.", zone=zp)
    for tag, y0, fy in cheeks:
        mid = rib_mid[tag]
        spots = [_lerp(mid[0], mid[1], 0.55), _lerp(mid[1], mid[2], 0.5), _lerp(mid[3], mid[4], 0.6)]
        pts = [Bp(X, y0 + 5 + fy * 70, z) for X, z in spots]
        a.take(mech.fasteners("_pc", D.seats_on(cheek_obs[tag], pts, (0, fy, 0), x_hint=(1, 0, 0)), "M4",
                              target=cheek_obs[tag]),
               f"Pauldron_Cheek_Screws_{tag}", f"Screws fixing the {tag.lower()} cheek to the carrier rib behind it.",
               zone=zp)

    # ── shoulder yaw actuator: the finned drum at the top of the upper arm ──
    d = mech.rotary_actuator("_yaw", 164, 96, Au @ T(0, 0, -100) @ R("X", 180), bolts=0, connector_angle=270 - 45 * s)
    a.take_rotary(d, "Shoulder_Yaw", "shoulder yaw")

    # ── upper-arm member: flange on the yaw output, neck, upper half of the elbow clamp ──
    bm = bmesh.new()
    P.merge(bm, P.cyl(132, 10, 48), T(0, 0, -204))
    P.merge(bm, P.loft([A.csec(-207, 84, 84, 0, 0, 0.16), A.csec(-246, 92, 106, 0, 0, 0.16)]))
    P.merge(bm, _half_clamp(False), T(0, 0, -PR.UPPER_ARM))
    P.merge(bm, P.box(40, 14, 30), T(0, 46, -232))                                   # connector boss
    um = a.add("Upper_Arm_Member", bm, "Upper-arm member: bolts to the yaw output and clamps the elbow actuator.", "alu",
               Au, bevel=1.0)
    for o in (1, -1):
        D.pocket_grid(um, Au @ T(o * 44.2, 0, -228) @ R("Y", o * 90), 1, 1, 22, 50, 0, 0, depth=6)
    seats = mech.ring((0, 0, -209), (0, 0, -1), 54, 8, x_hint=(1, 0, 0))
    a.take(mech.fasteners("_ub", seats, "M6", target=um, matrix=Au), "Upper_Arm_Flange_Bolts",
           "Screws clamping the upper-arm member to the shoulder yaw output flange.")

    # upper-arm armour: crowned outer half-shell; on the left its top edge runs up inside the skirt lame
    zt, wu = (-150, 97.0) if left else (-136, 102.0)

    def usec(z):
        f = (z + 100) / -154.0
        return _crown_sec(z, 2 * (wu - 9 * f), 2 * (93 - 12 * f), 0, 0, 50 - 6 * f, 6, 3)

    usecs = [usec(zt), usec(-254)]

    def open_upper(ob, lip=0.6):
        C.boolean_cut(ob, C.cutter(P.box(300, 400, 400), Au @ T(s * (38 - 150), 0, -200)), lip=lip)
        C.boolean_cut(ob, C.cutter(P.cyl(152, 500, 64), El @ R("Y", 90)), lip=lip)

    ush = a.add("Upper_Arm_Armour", A.shell(usecs, 10.0), "Armour half-shell over the outer side of the upper arm.",
                "armour", Au, bevel=1.2, seg=3)
    open_upper(ush)
    ucar = a.add("Upper_Arm_Armour_Carrier", A.hoops(usecs, (-222,), band=18.0),
                 "Carbon rib bonded inside the upper-arm armour.", "cfrp", Au, bevel=0.3, seg=1)
    open_upper(ucar, lip=None)
    posts = bmesh.new()
    pl = (wu - 9 * 0.79 - 18.8) - 42.5                        # from the member to the inside of the hoop
    for y in (-30, 30):
        P.merge(posts, P.cyl(14, pl, 16), T(s * (42.5 + pl / 2), y, -222) @ R("Y", 90))
    a.add("Upper_Arm_Carrier_Standoffs", posts, "Standoff posts fixing the upper-arm armour carrier to the member.", "alu",
          Au, bevel=0.4, seg=1)
    pts = [Au @ Vector((s * 160, y, z)) for y in (-48, 48) for z in (zt - 20, -240)]
    a.take(mech.fasteners("_us", D.seats_on(ush, pts, _dir(Au, (s, 0, 0))), "M6", target=ush), "Upper_Arm_Armour_Screws",
           "Screws fixing the upper-arm armour to its carrier.")
    F.panel_cut(ush, [Au @ Vector((s * X, y, z)) for X, y, z in usec(-204)[2:15]], 1.5, 2.0)

    # ── elbow: finned actuator clamped by the upper arm, forearm hung on its two ends ──
    a.add("Elbow_Housing", _elbow_housing_bm(), "Cycloidal elbow actuator housing with cooling fins.", "alu",
          El @ R("Y", 90), bevel=0)
    a.add("Elbow_Clamp_Cap", _half_clamp(True), "Lower half of the split clamp holding the elbow actuator.", "ti", El,
          bevel=0.8)
    seats = [El @ T(x, y, -13.5) @ R("X", 180) for x in (-16, 16) for y in (-94, 94)]
    a.take(mech.fasteners("_ec", seats, "M10", washer=True), "Elbow_Clamp_Bolts",
           "Bolts closing the split clamp around the elbow actuator.")
    a.add("Elbow_Hard_Stop", D.hard_stop_bm(20, 30, 16), "Bumpered stop that limits elbow extension.", ["ti", "rubber"],
          El @ frame((s * 27, 94, 7), (s, 0, 0), (0, 0, -1)), bevel=0.5)
    cn, _ = H.connector("_ecn", Au @ Vector((0, 53, -232)), _dir(Au, (0, 1, 0)), 14.0)
    a.take(cn, "Elbow_Connector", "Power and encoder connector for the elbow actuator.")

    # ── forearm frame: hangers on the elbow, spine carrying the hand drive, roll actuator seat ──
    bm = bmesh.new()
    P.merge(bm, P.lug(56, 26, 106, 10, 40), frame((s * 68, 0, 0), (1, 0, 0), (0, 0, 1)))
    P.merge(bm, P.lug(50, 22, 106, 8, 40), frame((-s * 67, 0, 0), (1, 0, 0), (0, 0, 1)))
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(158, 92), 12), -126, -100))
    P.merge(bm, P.loft([A.csec(-124, 72, 66, 0, 0, 0.16), A.csec(-204, 62, 60, 0, 0, 0.16)]))
    P.merge(bm, P.cyl(112, 8, 48), T(0, 0, -206))
    P.merge(bm, P.box(10, 56, 12), T(s * 68, 76, -12))                                # arm that meets the elbow hard stop,
    P.merge(bm, P.box(33, 30, 12), T(s * 56.5, 89, -12))                              # reaching in behind the housing
    ff = a.add("Forearm_Frame", bm, "Forearm frame: hangs from the elbow actuator and carries the hand drive.", "alu",
               Af, bevel=1.0)
    for o in (1, -1):
        D.pocket_grid(ff, Af @ T(0, o * 31.8, -164) @ R("X", o * 90), 1, 1, 44, 56, 0, 0, depth=6)
    D.pocket_grid(ff, Af @ T(s * 73.2, 0, -82) @ R("Y", s * 90), 1, 1, 30, 38, 0, 0, depth=4)
    Eo = Af @ T(s * 73, 0, 0) @ R("Y", s * 90)                  # outer face of the outer hanger, +Z out
    hc = a.add("Elbow_Hub_Cover", _hub_cover_bm(),
               "Ribbed cover clamping the forearm hanger to the elbow output flange.", "alu", Eo, bevel=0.6)
    a.take(mech.fasteners("_eh", mech.ring((0, 0, 7), (0, 0, 1), 46, 6), "M6", target=hc, matrix=Eo),
           "Elbow_Hub_Cover_Screws", "Screws through the hub cover into the elbow output flange.")
    a.add("Elbow_Hub_Cap", _hub_cap_bm(), "Ribbed dust cap over the elbow output bearing, pressed into the hub cover.",
          "alu", Eo, bevel=0.5)
    Ei = Af @ T(-s * 71, 0, 0) @ R("Y", -s * 90)                # outer face of the inner hanger; local +Y is rearward
    a.add("Elbow_Encoder_Pod", _encoder_pod_bm(),
          "Absolute encoder on the idler end of the elbow, with its electronics pod and cable gland.",
          ["alu", "fastener"], Ei, bevel=0.5)
    a.take(mech.fasteners("_el", [Ei @ T(x, 30 + y, 15) for x in (-9, 9) for y in (-7, 7)], "M4"),
           "Elbow_Encoder_Pod_Screws", "Screws holding the lid of the elbow encoder pod.")

    # hand drive: six motors on the spine, their controller, tendons down into the roll shaft
    mb = bmesh.new()
    tend = bmesh.new()
    for y in (-46, 46):
        for x in (-25, 0, 25):
            P.merge(mb, P.revolve([(0, 0), (13, 0), (13, 52), (11, 54), (11, 60), (5, 62), (0, 62)], 20), T(x, y, -194))
            path = P.catmull([(x, y, -194), (x * 0.7, y * 0.8, -203), (x * 0.36, y * 0.22, -209)], step=3.0)
            P.merge(tend, P.sweep(path, 3.2, 8))
        P.merge(mb, P.box(84, 6, 16), T(0, y * 0.74, -150))
        P.merge(mb, P.box(84, 6, 10), T(0, y * 0.74, -186))
    a.add("Hand_Drive_Motors", mb, "Six motors driving the finger and thumb tendons.", "alu", Af, bevel=0.4, seg=1)
    a.add("Hand_Drive_Tendons", tend, "Sheathed tendons running from the hand drive into the hollow roll shaft.", "rubber",
          Af, bevel=0)
    a.add("Hand_Drive_Controller", D.finned_block_bm(64, 84, 20, 8), "Motor controller for the hand drive, with its heat sink.",
          "alu", Af @ T(s * 33, 0, -164) @ R("Y", s * 90) @ R("Z", 90), bevel=0.3, seg=1)

    # forearm roll: hollow-shaft actuator and the bearing that carries the wrist
    d = mech.rotary_actuator("_fr", 100, 50, Af @ T(0, 0, -210) @ R("X", 180), bolts=8, connector_angle=270)
    a.take_rotary(d, "Forearm_Roll", "forearm roll")
    a.add("Forearm_End_Ring", P.tube(126, 113, 12, 1.0), "End ring of the forearm, seating the wrist bearing.", "alu",
          Af @ T(0, 0, -257), bevel=0)
    a.take(mech.bearing("_rb", 112, 82, 10, Af @ T(0, 0, -262)), "Forearm_Roll_Bearing",
           "Bearing carrying the wrist on the end of the forearm.")

    # ── forearm armour: crowned shell, clamshell split, an outer plate standing off it over the heat sink ──
    fsecs = [_fore_sec(z) for z, *_ in FORE]
    Mf = Af @ Matrix.Diagonal((s, 1.0, 1.0, 1.0))
    xo, yo = _dir(Af, (s, 0, 0)), _dir(Af, (0, 1, 0))

    def open_fore(ob, lip=0.6):
        C.boolean_cut(ob, C.cutter(P.cyl(220, 500, 64), Af @ R("Y", 90)), lip=lip)          # room for the elbow
        C.boolean_cut(ob, C.cutter(P.box(400, 130, 100), Af @ T(0, -105, -50)), lip=lip)    # front trimmed for flexion

    fsh = raw(A.shell(fsecs, 10.0), Af, "armour", 1.2, 3)
    open_fore(fsh)
    A.gap_cut(fsh, Af @ Vector((0, 0, -150)), _dir(Af, (1, 0, 0)))
    pieces = sorted(A.islands(fsh), key=lambda o: -len(o.data.vertices))[:2]
    inner_h, outer_h = sorted(pieces, key=lambda o: _local(Af, o).x * s)
    a.take(outer_h, "Forearm_Armour_Outer", "Outer half of the forearm armour, open over the hand drive controller.")
    a.take(inner_h, "Forearm_Armour_Inner", "Inner half of the forearm armour.")

    # outer plate: follows the shell 2 mm off it, exhaust slots over the heat sink
    bm = _skin([_fore_sec(z, 10.0)[3:14] for z in (-142, -178, -214, -224)])      # the +X face and 36 deg of each corner
    ys_ = [p[1] for p in _fore_sec(-142, 10.0)[3:14]]
    for ye_, ny in ((min(ys_), -1), (max(ys_), 1)):
        _clip(bm, (0, ye_, -142 - 16), (0, ny, 1))
        _clip(bm, (0, ye_ - ny * 6, -224 + 20), (0, ny, -1))
    plate = a.add("Forearm_Outer_Plate", _tray(bm, 8.0, 0.0, (0, 0, -180)),
                  "Outer forearm plate standing off the shell over the controller's heat sink, slotted for its exhaust.",
                  "armour", Mf, bevel=1.2, seg=3)
    vent_pt = [Af @ Vector((s * 180, 0, -182))]
    A.slots(plate, D.seats_on(plate, vent_pt, xo, x_hint=yo)[0], 4, 56, 6, 13, depth=12)
    seat = D.seats_on(outer_h, vent_pt, xo, x_hint=yo)[0]
    A.opening(outer_h, P.rrect(70, 58, 6), seat, depth=30, above=4)
    vb = P.prism(P.rrect(78, 66, 4), -0.4, 0.4)
    uv = vb.loops.layers.uv.new("UVMap")
    for fc in vb.faces:
        for lp in fc.loops:
            lp[uv].uv = (lp.vert.co.x * C.MM, lp.vert.co.y * C.MM)
    a.add("Forearm_Vent_Screen", vb, "Mesh screen across the cooling opening, bonded inside the shell.", "mesh",
          seat @ T(0, 0, -11.0), bevel=0)
    pts = [Af @ Vector((s * 180, y, z)) for y in (-50, 50) for z in (-153, -213)]
    seats = D.seats_on(plate, pts, xo)
    sp = bmesh.new()
    for m in seats:
        P.merge(sp, P.cyl(16, 2.4, 16), m @ T(0, 0, -9.0))
    a.add("Forearm_Outer_Plate_Spacers", sp, "Spacers holding the outer forearm plate off the shell.", "alu", None,
          bevel=0.3, seg=1)
    a.take(mech.fasteners("_fp", seats, "M6", target=plate), "Forearm_Outer_Plate_Screws",
           "Screws fixing the outer forearm plate through its spacers.")

    # access doors: cut from the shell itself, so they follow its crown
    for ob, o, tag in ((outer_h, s, "Front"), (inner_h, -s, "Rear")):
        fy = -1 if tag == "Front" else 1
        fwd = _dir(Af, (0, fy, 0))
        xh = _dir(Af, (1, 0, 0))

        def on(target, x, z):
            return D.seats_on(target, [Af @ Vector((x, fy * 170, z))], fwd, x_hint=xh)[0]

        dw, dh, dx, dz = 54.0, 84.0, o * 36.0, -166.0
        seat = on(ob, dx, dz)
        door = _copy(ob)
        C.boolean_intersect(door, C.cutter(P.prism(P.rrect(dw, dh, 6), -40, 30), seat), lip=0.5)
        C.boolean_cut(ob, C.cutter(P.prism(P.rrect(dw + 3, dh + 3, 7.5), -40, 30), seat), lip=0.5)
        a.take(door, f"Forearm_Hatch_{tag}", f"{tag} access door over the hand drive motors.")
        hm = on(ob, dx - o * (dw / 2 + 5.5), dz)
        a.add(f"Forearm_Hatch_{tag}_Hinge", F.hinge_bm(3.0, dh * 0.72, 5, 0.0),
              f"Hinge of the {tag.lower()} forearm access door.", ["alu", "steel"], hm @ T(0, 0, 2.4), bevel=0)
        seats = [on(door, dx + o * (dw / 2 - 9), dz + k * (dh / 2 - 12)) for k in (-1, 0, 1)]
        a.take(mech.fasteners("_fq", seats, "M6", "quarter"), f"Forearm_Hatch_{tag}_Quarter_Turns",
               f"Quarter-turn fasteners latching the {tag.lower()} forearm access door.")

    # wear strip on the rear outer shoulder of the forearm, where it rubs past the body
    bm = _skin([_fore_sec(z, 5.0)[14:18] for z in (-132, -173, -214, -232)])
    wear = a.add("Forearm_Wear_Plate", _tray(bm, 5.5, 0.0, (0, 0, -180)),
                 "Replaceable wear strip on the rear outer edge of the forearm.", "ti", Mf, bevel=0.6)
    pts = [Af @ Vector((s * 40, 170, z)) for z in (-144, -181, -218)]
    a.take(mech.fasteners("_fw", D.seats_on(wear, pts, yo, x_hint=_dir(Af, (0, 0, -1))), "M6", "csk", target=wear),
           "Forearm_Wear_Plate_Screws", "Countersunk screws holding the forearm wear strip.")

    fcar = a.add("Forearm_Armour_Carrier", A.hoops(fsecs, (-130, -238), band=18.0),
                 "Carbon ribs bonded inside the forearm armour.", "cfrp", Af, bevel=0.3, seg=1)
    open_fore(fcar, lip=None)
    posts = bmesh.new()
    for x in (-52, 52):
        P.merge(posts, P.cyl(14, 15, 16), T(x * 1.1, 0, -238) @ R("Y", 90))
        P.merge(posts, P.cyl(14, 40, 16), T(x * 1.16, 0, -130) @ R("Y", 90))
    a.add("Forearm_Carrier_Standoffs", posts, "Standoff posts fixing the forearm armour carrier to the frame.", "alu", Af,
          bevel=0.4, seg=1)
    for ob, o, tag in ((outer_h, s, "Outer"), (inner_h, -s, "Inner")):
        pts = [Af @ Vector((o * 150, y, z)) for y in (-62, 62) for z in (-124, -238)]
        a.take(mech.fasteners("_fs", D.seats_on(ob, pts, _dir(Af, (o, 0, 0))), "M6", target=ob), f"Forearm_{tag}_Screws",
               f"Screws fixing the {tag.lower()} forearm armour half to its carrier.")
    F.panel_cut(inner_h, [Af @ Vector((-s * 104, y, -176)) for y in range(-60, 61, 8)], 1.5, 2.0)
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    s = 1 if a.aa == "07" else -1
    W = FR.torso()
    sv0, au0, af0, _ = FR.arm(s)
    S = W @ sv0
    sh = [o for o in objs if "Shoulder" in o.name or "Pauldron" in o.name]
    RV.closeup(sh, out / f"{a.aa}_shoulder_front_clay{tag}.jpg", f"{a.aa} shoulder, front", (s * 0.45, -1, 0.12), "clay",
               target=S + Vector((s * 20, 0, -30)), dist=5.0)
    RV.closeup(sh, out / f"{a.aa}_shoulder_rear_final{tag}.jpg", f"{a.aa} shoulder, rear", (s * 0.6, 1, 0.15), "final",
               target=S + Vector((s * 20, 0, -30)), dist=5.0, isolate=True)
    RV.closeup(sh, out / f"{a.aa}_shoulder_side_clay{tag}.jpg", f"{a.aa} shoulder armour, outer side", (s * 1.0, -0.3, 0.12),
               "clay", target=S + Vector((s * 60, 0, 0)), dist=5.0, isolate=True)
    RV.closeup(sh, out / f"{a.aa}_shoulder_under_clay{tag}.jpg", f"{a.aa} shoulder armour, from below and behind",
               (s * 0.5, 0.9, -0.1), "clay", target=S + Vector((s * 30, 0, 10)), dist=3.4, isolate=True)
    el = [o for o in objs if "Elbow" in o.name or "Forearm" in o.name or "Upper_Arm" in o.name or "Hand_Drive" in o.name]
    ec = (W @ au0 @ T(0, 0, -PR.UPPER_ARM)).translation
    RV.closeup(el, out / f"{a.aa}_elbow_outer_clay{tag}.jpg", f"{a.aa} elbow, outer three-quarter", (s * 1.0, -0.55, 0.1),
               "clay", target=ec + Vector((0, 0, -60)), dist=4.4)
    RV.closeup(el, out / f"{a.aa}_elbow_rear_final{tag}.jpg", f"{a.aa} elbow, rear three-quarter", (s * 0.7, 0.9, 0.1),
               "final", target=ec + Vector((0, 0, -60)), dist=4.4)
    RV.closeup(objs, out / f"{a.aa}_arm_inner_clay{tag}.jpg", f"{a.aa} arm, inner side", (-s * 1.0, -0.35, 0.05), "clay",
               res=(1000, 1500), dist=5.0, isolate=True)
