"""Assembly 01: head and cap. The signature of the machine.

A faceless sensor head: one raked faceplate with a single slit and an
off-centre lens cluster, under a rigid armoured cap worn backwards. The cap
gets its identity from shape alone: a six-gore crown with raised double seams
meeting under a button, an eyelet vent in every gore, the snapback arch over
the forehead closed by a toothed strap and latch, and a cambered brim with a
rolled edge bolted on over the nape.

Built in body coordinates (FR.torso() applied). Faceplate frame Fm: X lateral,
Y up the plate, +Z out of the face. Cap frame Cm: origin at the centre of the
crown base, +Y to the rear (brim side), +Z up through the crown. Plan angles on
the crown run from +X (robot's left, 0) through the brim (90 degrees) to the
forehead (270 degrees). Brim frame Bm: the cap frame raked down about the nape.
"""
import math

import bmesh
import bpy
from mathutils import Vector

from .. import frames as FR, materials as M, params as PR
from ..lib import armour as A, core as C, detail as D, fittings as F, harness as H, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm, raw

Z0, Z1 = 1538.0, 1632.0                  # skull base, skull top (under the cap)
RAKE = math.tan(math.radians(PR.FACE_RAKE))
ZC = 1598.0                              # faceplate datum height
SHEAR = 14.0                             # crown high point sits this far towards the brim
A_FRONT = 1.5 * math.pi                  # plan angle of the forehead: the arch faces forward
ARCH_A = math.radians(22.5)              # half-width of the arch in plan angle
ARCH_Z = 54.0                            # arch apex above the crown base
PHI_TOP = math.radians(88.6)             # last ring of the crown mesh before the pole
BRIM_SAG, BRIM_DROP = 12.0, 3.8          # camber across the brim; how far the whole bill sits down
BRIM_RAD = ((PR.BRIM_W / 2) ** 2 + BRIM_SAG ** 2) / (2 * BRIM_SAG)
BRIM_ZE = BRIM_RAD * math.cos(PR.BRIM_W / 2 / BRIM_RAD)
NUMBER_AT, NUMBER_N = (-8.0, 40.0), (1, -0.12, 0.35)        # where marks.py aims the unit number: plan angle, height; direction
NECK_ACT = ((42.0, 40.0, 1524.0), (46.0, 64.0, 1580.0))   # neck actuator pivots (left side), as in neck.py


def front(z):
    """Y of the skull's front surface at height z (raked: the top is further forward)."""
    return -86.0 - (z - Z0) * RAKE


def cap_frame():
    tilt = math.degrees(math.atan2(PR.CAP_FRONT_Z - PR.CAP_REAR_Z, PR.CAP_L))
    base_z = (PR.CAP_FRONT_Z + PR.CAP_REAR_Z) / 2
    h = (PR.Z_CROWN - PR.CAP_BUTTON_H * 0.55 - base_z) / math.cos(math.radians(tilt))
    return tilt, h, FR.torso() @ T(0, PR.CAP_Y, base_z) @ R("X", -tilt)


# ── crown: an exact parametrisation, used for the shell and everything that sits on it ──
def side_exp(a):
    """Profile exponent of the crown at plan angle a. The gores over the brim rise
    steeper and flatter than the rest, as the stiffened front of a cap does."""
    s = math.sin(a)
    return 2.5 + 0.4 * s * s if s > 0 else 2.5


def crown_uv(a, phi, h):
    """Point on the crown at plan angle a and latitude phi (0 at the base, pi/2 at the top)."""
    e = 2 / side_exp(a)
    t = math.sin(phi) ** e
    k = math.cos(phi) ** e
    c, s = math.cos(a), math.sin(a)
    return Vector((PR.CAP_W / 2 * math.copysign(abs(c) ** (2 / 2.2), c) * k,
                   PR.CAP_L / 2 * math.copysign(abs(s) ** (2 / 2.2), s) * k + SHEAR * t ** 1.4, h * t))


def crown_normal(a, phi, h):
    """Outward unit normal of the crown at (a, phi)."""
    e = 1e-3
    phi = min(max(phi, 2 * e), math.pi / 2 - 2 * e)
    n = (crown_uv(a + e, phi, h) - crown_uv(a - e, phi, h)).cross(crown_uv(a, phi + e, h) - crown_uv(a, phi - e, h))
    n.normalize()
    return n


def zphi(a, z, h):
    """Latitude of the crown at height z above its base."""
    return math.asin(min(max(z / h, 0.0), 1.0) ** (side_exp(a) / 2))


def crown_pt(a, z, h, grow=0.0):
    """Point on the crown at plan angle a and height z above its base, pushed out by grow."""
    t = min(max(z / h, 0.0), 1.0)
    k = math.cos(zphi(a, z, h)) ** (2 / side_exp(a))
    c, s = math.cos(a), math.sin(a)
    x = PR.CAP_W / 2 * math.copysign(abs(c) ** (2 / 2.2), c) * k
    y = PR.CAP_L / 2 * math.copysign(abs(s) ** (2 / 2.2), s) * k
    r = math.hypot(x, y) or 1.0
    return (x + grow * x / r, y + grow * y / r + SHEAR * t ** 1.4, z)


def surf(a, z, h, grow=0.0):
    """Frame on the crown (cap coordinates) at plan angle a, height z, pushed out by
    grow: +Z along the outward normal, +X round the crown, +Y up it."""
    e = 1e-3
    tan = Vector(crown_pt(a + e, z, h)) - Vector(crown_pt(a - e, z, h))
    return frame(Vector(crown_pt(a, z, h, grow)), crown_normal(a, zphi(a, z, h), h), tan)


def arc_phis(a, h, lo, hi, m):
    """m + 1 latitudes from lo to hi on the meridian at a, evenly spaced along the surface."""
    n = 96
    ph = [lo + (hi - lo) * (i / n) ** 1.6 for i in range(n + 1)]
    pts = [crown_uv(a, p, h) for p in ph]
    run = [0.0]
    for p, q in zip(pts, pts[1:]):
        run.append(run[-1] + (q - p).length)
    out, k = [], 0
    for j in range(m + 1):
        s = run[-1] * j / m
        while k < n - 1 and run[k + 1] < s:
            k += 1
        f = (s - run[k]) / max(run[k + 1] - run[k], 1e-9)
        out.append(ph[k] + (ph[k + 1] - ph[k]) * min(max(f, 0.0), 1.0))
    return out


def arch_z(a):
    """Height of the arch edge above the crown base at plan angle a (0 outside the arch)."""
    u = ((a - A_FRONT + math.pi) % (2 * math.pi) - math.pi) / ARCH_A
    return ARCH_Z * math.sqrt(1.0 - u * u) if abs(u) < 1.0 else 0.0


def crown_bm(h, n_out=168, n_in=16, rows=48):
    """Crown surface as one structured grid with the arch built into the topology:
    meridians bunch up towards the two jambs so the arch edge stays smooth, and
    the rows over the arch start on its edge. No boolean, so nothing to pinch."""
    cols = [A_FRONT + ARCH_A + (2 * math.pi - 2 * ARCH_A) * i / n_out for i in range(n_out)]
    for k in range(2 * n_in):
        u = -1 + (k / n_in) ** 1.5 if k <= n_in else 1 - ((2 * n_in - k) / n_in) ** 1.5
        cols.append(A_FRONT + 2 * math.pi + u * ARCH_A)
    bm = bmesh.new()
    grid = []
    for a in cols:
        grid.append([bm.verts.new(crown_uv(a, p, h)) for p in arc_phis(a, h, zphi(a, arch_z(a), h), PHI_TOP, rows)])
    top = bm.verts.new((0, SHEAR, h))
    n = len(cols)
    for i in range(n):
        ca, cb = grid[i], grid[(i + 1) % n]
        for j in range(rows):
            bm.faces.new((ca[j], cb[j], cb[j + 1], ca[j + 1]))
        bm.faces.new((ca[rows], cb[rows], top))
    return bm


def band_bm(h, z0, z1, grow, thick, a0=None, a1=None, n=48, rows=2):
    """Strip that hugs the crown between heights z0 and z1: a full ring, or an arc a0..a1."""
    bm = bmesh.new()
    full = a0 is None
    cnt = n if full else n + 1
    a0, a1 = (0.0, 2 * math.pi) if full else (a0, a1)
    grid = [[bm.verts.new(crown_pt(a0 + (a1 - a0) * i / n, z0 + (z1 - z0) * j / (rows - 1), h, grow))
             for i in range(cnt)] for j in range(rows)]
    for j in range(rows - 1):
        for i in range(n):
            k = (i + 1) % cnt
            bm.faces.new((grid[j][i], grid[j][k], grid[j + 1][k], grid[j + 1][i]))
    return P.thicken(bm, thick, center=(0, 0, (z0 + z1) / 2))


def strap_bm(h, stations):
    """Solid that follows the crown round its base. stations: (plan angle in degrees,
    inner offset, outer offset, z0, z1), lofted in order."""
    secs = []
    for d, gi, go, z0, z1 in stations:
        a = math.radians(d)
        secs.append([crown_pt(a, z0, h, gi), crown_pt(a, z0, h, go), crown_pt(a, z1, h, go), crown_pt(a, z1, h, gi)])
    return P.loft(secs, cap=True)


def rib_bm(a, phi0, phi1, h, n=44):
    """Raised double seam along the meridian at a: two beads either side of the seam line."""
    w = PR.SEAM_W / 2
    bead = [(w, -0.4), (w + 0.4, 1.4), (3.8, 1.4), (4.6, -0.4)]
    left, right = [], []
    for p_ in arc_phis(a, h, phi0, phi1, n):
        o, nr = crown_uv(a, p_, h), crown_normal(a, p_, h)
        tan = (crown_uv(a, p_ + 1e-3, h) - crown_uv(a, p_ - 1e-3, h)).normalized()
        side = tan.cross(nr)
        right.append([tuple(o + side * s + nr * z) for s, z in bead])
        left.append([tuple(o - side * s + nr * z) for s, z in reversed(bead)])
    return P.merge(P.loft(left, cap=True), P.loft(right, cap=True))


def knurl_ring_bm(od, id_, z0, z1):
    """Lock ring with a straight knurl round its rim and a chamfered top."""
    n = 2 * max(12, round(od * 1.7))
    ang = [2 * math.pi * i / n for i in range(n)]
    outer = [((od / 2 - (0.45 if i % 2 else 0.0)) * math.cos(t), (od / 2 - (0.45 if i % 2 else 0.0)) * math.sin(t))
             for i, t in enumerate(ang)]
    lip = [(x * (1 - 1.1 / od), y * (1 - 1.1 / od)) for x, y in outer]
    inner = [(id_ / 2 * math.cos(t), id_ / 2 * math.sin(t)) for t in ang]
    return P.loft([P.at_z(inner, z0), P.at_z(outer, z0), P.at_z(outer, z1 - 0.55), P.at_z(lip, z1), P.at_z(inner, z1)],
                  cap=False, wrap=True)


# ── brim: built flat, then cambered ──────────────────────────────────────────
def camber_pt(x, y, z):
    """Where a point of the flat brim ends up once the bill is cambered."""
    th = x / BRIM_RAD
    rr = BRIM_RAD + z
    return Vector((rr * math.sin(th), y, rr * math.cos(th) - BRIM_ZE - BRIM_DROP))


def camber(bm, slices=0):
    if slices:
        P.slice_axis(bm, 0, slices)
    for v in bm.verts:
        v.co = camber_pt(*v.co)
    return bm


def camber_frame(x, y, z):
    """Rigid placement that follows the camber, for small parts on the brim."""
    return T(*camber_pt(x, y, z)) @ R("Y", math.degrees(x / BRIM_RAD))


def brim_top(x):
    """Height of the brim's upper surface (brim frame) at lateral position x."""
    rr = BRIM_RAD + PR.BRIM_T
    return math.sqrt(rr * rr - x * x) - BRIM_ZE - BRIM_DROP


def inset(path, d):
    """Offset an open 2D path by d to its left."""
    out = []
    for i, p in enumerate(path):
        t = (Vector(path[min(i + 1, len(path) - 1)]) - Vector(path[max(i - 1, 0)])).normalized()
        out.append((p[0] - t.y * d, p[1] + t.x * d))
    return out


def _drop(ob):
    me = ob.data
    bpy.data.objects.remove(ob)
    if me.users == 0:
        bpy.data.meshes.remove(me)


def _mid(ob):
    lo, hi = C.bounds_mm([ob])
    return (lo + hi) / 2


def build():
    a = Asm("01")
    W = FR.torso()
    rake = math.radians(PR.FACE_RAKE)
    Pm = W @ T(0, front(ZC) - 1, ZC) @ R("X", 90 + PR.FACE_RAKE)        # back face of the faceplate
    Fm = Pm @ T(0, 0, 7)                                                 # its outer face
    dz = (PR.Z_SLIT - ZC) / math.cos(rake)                               # slit centre, up the plate
    tilt, h, Cm = cap_frame()

    # ── skull: frame inside, three-piece shell outside ──────────────────────
    bm = bmesh.new()
    P.merge(bm, P.revolve(P.ring_profile(34, 62, Z0 + 8, Z0 + 16, 1.5), 48), T(0, 4, 0))     # seat of the neck's head yoke
    side = [(front(Z0 + 8) + 16, Z0 + 8), (62, Z0 + 8), (70, Z1 + 6), (front(Z1 + 6) + 16, Z1 + 6)]
    for o in (1, -1):
        P.merge(bm, P.prism(P.chamfer_poly(side, 8), -3, 3), T(o * 66, 0, 0) @ R("Z", 90) @ R("X", 90))
        P.merge(bm, P.box(22, 16, 18), T(o * 48, 64, 1603))                      # neck actuator fork seats
        P.merge(bm, P.box(5.5, 12, 60), T(o * 60.25, 64, 1582))                  # ... tied into the side plates
    P.merge(bm, P.box(128, 150, 6), T(0, -12, Z1 + 5))                            # top deck under the cap
    P.merge(bm, P.box(126, 5, 76), T(0, front(1590) + 20, 1590) @ R("X", PR.FACE_RAKE))   # sensor bulkhead
    P.merge(bm, P.box(126, 8, 8), T(0, 30, Z0 + 12))                              # base cross-tie, level with the yoke seat
    sf = a.add("Skull_Frame", bm, "Machined frame carrying the faceplate, sensors, electronics and cap.", "alu", W,
               bevel=0.6)
    for o in (1, -1):
        D.pocket_grid(sf, W @ T(o * 69.2, -4, 1590) @ R("Y", o * 90), 2, 2, 28, 44, 38, 58, depth=3.2)
    C.boolean_cut(sf, C.cutter(P.box(134, 30, 9), Pm @ T(0, dz, -24)), lip=0.3)   # camera window in the bulkhead
    C.boolean_cut(sf, C.cutter(P.box(44, 42, 9), Pm @ T(43, -17, -24)), lip=0.3)  # ... and one for the lens cluster's units
    cut = bmesh.new()
    for o in (1, -1):                                                             # clearance bores round the neck actuators
        p0, p1 = Vector((o * NECK_ACT[0][0], *NECK_ACT[0][1:])), Vector((o * NECK_ACT[1][0], *NECK_ACT[1][1:]))
        ax = (p1 - p0).normalized()
        P.merge(cut, P.cyl(25, 58, 32), frame(p0 + ax * 15, ax))
    C.boolean_cut(sf, C.cutter(cut, W), lip=0.3)
    C.boolean_cut(sf, C.cutter(P.cyl(38, 30, 32), W @ T(0, 78, Z0 + 12)), lip=0.3)   # ... and the neck yaw motor

    secs = []
    for zz, w, back, r in ((Z0, 148, 78, 26), (1590, 164, 88, 34), (Z1, 170, 91, 42)):   # top kept narrow: the barrel traverses past it
        d = back - front(zz)
        secs.append(A.rsec(zz, w, d, 0, (back + front(zz)) / 2, r))
    bay = P.chamfer_poly([(-54, -43), (57, -43), (66, 29), (-64, 29)], 10)

    def trim(ob, lip=0.5):
        """Sensor bay opening, and a slanted top that tucks under the cap."""
        A.opening(ob, bay, Fm, depth=40, above=12, lip=lip)
        C.boolean_cut(ob, C.cutter(P.box(420, 420, 200), Cm @ T(0, 0, 100 - 3.0)), lip=lip)

    sk = raw(A.shell(secs, 6.0), W, "armour", 1.0, 3)
    trim(sk)
    A.gap_cut(sk, W @ Vector((0, 18, 1590)), (0, 1, 0))                           # front / rear break
    pieces = sorted(A.islands(sk), key=lambda o: -len(o.data.vertices))
    for ob in pieces[2:]:
        _drop(ob)
    front_sh, rear = sorted(pieces[:2], key=lambda o: C.bounds_mm([o])[0].y)
    # jaw line: square to the faceplate, so it falls towards the chin
    A.gap_cut(front_sh, W @ Vector((0, 18, 1584)), (0, -math.sin(rake), math.cos(rake)))
    pieces = A.islands(front_sh)
    for ob in [o for o in pieces if len(o.data.vertices) < 60]:
        _drop(ob)
    pieces = sorted([o for o in pieces if len(o.data.vertices) >= 60], key=lambda o: _mid(o).z)
    assert len(pieces) == 2, f"front skull shell split into {len(pieces)} pieces"
    jaw, front_sh = pieces
    a.take(front_sh, "Skull_Shell_Front", "Front skull shell: seats the faceplate and wraps the cheeks.")
    a.take(jaw, "Skull_Shell_Jaw", "Lower front shell below the jaw line; comes off alone to reach the neck gimbal.")
    a.take(rear, "Skull_Shell_Rear", "Rear skull shell closing the back of the head above the neck.")
    liner = a.add("Skull_Liner", D.rib_ring_bm(secs, 1.6, 6.6), "Carbon liner behind the skull shells; backs the panel seams.",
                  "cfrp", W, bevel=0.2, seg=1)
    trim(liner, lip=None)

    # right cheek: louvred intake. Air goes in here, over the heat spreader, out through the cap.
    vs = D.seats_on(front_sh, [W @ Vector((-140, -36, 1607))], (-1, 0, 0), x_hint=(0, -1, 0))[0]
    floor_d = (abs(vs.translation.x) - 66.1) / abs(vs.col[2].x)                   # depth of the frame pocket behind it
    v = F.vent("_cv", 34, 16, vs @ T(0, 0, -1.0), kind="slats", count=4, depth=11.0, target=front_sh, corner=3.0)
    A.opening(liner, P.rrect(35, 17, 3.5), vs, depth=20, above=2, lip=None)
    for key, mat in (("bezel", "armour"), ("slats", "ti")):                       # nothing bright beside the slit
        v[key].data.materials[0] = M.get(mat)
    a.take(v["bezel"], "Cheek_Vent_Bezel", "Frame of the right cheek intake, set flush in the shell.")
    a.take(v["slats"], "Cheek_Vent_Louvres", "Rain-shedding louvres of the cheek intake that feeds the heat spreader.")
    _drop(v["back"])
    a.add("Cheek_Vent_Filter", P.prism(P.rrect(38, 20, 4), -floor_d, -8.3),
          "Filter cassette behind the cheek louvres, held between the liner and the frame.", "cavity", vs, bevel=0)
    # left cheek: hatch behind the lens cluster
    hs = D.seats_on(front_sh, [W @ Vector((140, -36, 1607))], (1, 0, 0), x_hint=(0, 1, 0))[0]
    hc = F.hatch("_ch", 40, 24, hs, target=front_sh, hinge_side="R", fasteners=1, corner=4.0)
    a.take(hc["door"], "Lens_Service_Door", "Door behind the lens cluster: its units come out here without disturbing the "
           "faceplate.")
    a.take(hc["hinge"], "Lens_Service_Hinge", "Hinge of the lens service door.")
    a.take(hc["fasteners"], "Lens_Service_Latch", "Quarter-turn fastener latching the lens service door.")
    seat = D.seats_on(rear, [W @ Vector((0, 220, 1581))], (0, 1, 0), x_hint=(1, 0, 0))[0]
    hd = F.hatch("_dh", 46, 26, seat, target=rear, hinge_side="L", fasteners=1, corner=4.0)
    a.take(hd["door"], "Data_Port_Door", "Door over the maintenance data port at the back of the head.")
    a.take(hd["hinge"], "Data_Port_Hinge", "Hinge of the data port door.")
    a.take(hd["fasteners"], "Data_Port_Latch", "Quarter-turn fastener latching the data port door.")

    def side_seats(target, pts):
        out = []
        for o in (1, -1):
            out += D.seats_on(target, [W @ Vector((o * 140, y, z)) for y, z in pts], (o, 0, 0), x_hint=(0, 0, 1))
        return out

    # screws sit over the webs of the frame's side plates, not over its pockets
    s_front = side_seats(front_sh, ((-3, 1612), (-58, 1583)))
    s_jaw = side_seats(jaw, ((-3, 1562), (-58, 1552)))
    s_rear = side_seats(rear, ((51, 1608), (51, 1558)))
    so = bmesh.new()
    for m in s_front + s_jaw + s_rear:
        ln = (abs(m.translation.x) - 69.0) / max(abs(m.col[2].x), 0.5) - 7.8
        if ln > 1.0:
            P.merge(so, P.cyl(9.0, ln, 6), m @ T(0, 0, -7.8 - ln / 2))
    a.add("Shell_Standoffs", so, "Hex standoffs from the frame's side plates that the shell screws run into.", "alu",
          bevel=0.2, seg=1)
    a.take(mech.fasteners("_fs", s_front, "M4", target=front_sh), "Front_Shell_Screws",
           "Counterbored screws holding the front shell to the frame.")
    a.take(mech.fasteners("_js", s_jaw, "M4", target=jaw), "Jaw_Shell_Screws",
           "Counterbored screws holding the jaw shell to the frame.")
    a.take(mech.fasteners("_rs", s_rear, "M4", target=rear), "Rear_Shell_Screws",
           "Counterbored screws holding the rear shell to the frame.")

    # ── faceplate: one flat raked plate, one slit, one off-centre lens cluster ──
    lc = (43.0, -13.0)                                                   # lens cluster centre on the plate
    Lm = Fm @ T(lc[0], lc[1], 0)
    bz = P.chamfer_poly([(-17, -23), (17, -23), (17, 23), (-17, 23)], [5, 4, 4, 4])
    # name, x, y, barrel radius, barrel height, glass depth, convex, function
    lenses = (("Thermal_Imager_Lens", 0.5, 8.5, 11.0, 7.5, 4.5, True,
               "Germanium objective of the thermal imager, set deep in its barrel."),
              ("Lidar_Window", -7.0, -13.0, 7.5, 6.2, 2.2, False, "Flat window of the scanning lidar in its barrel."),
              ("Spotter_Camera_Lens", 9.5, -15.5, 5.5, 10.5, 6.0, True,
               "Objective of the long-focus spotter camera at the bottom of its hood."))
    fp = P.chamfer_poly([(-62, -50), (62, -50), (72.5, 36), (-72.5, 36)], [16, 16, 10, 10])
    face = raw(P.plate(fp, 7), Pm, "armour", 1.2, 3)
    A.recess(face, P.rrect(128, 19, 5), Fm @ T(0, dz, 0), depth=2.0)
    A.opening(face, P.rrect(PR.SLIT_W + 2, PR.SLIT_H + 2, 4), Fm @ T(0, dz, 0), depth=14, above=6, lip=0.4)
    A.recess(face, [(x * 1.035, y * 1.026) for x, y in bz], Lm, depth=1.2)
    cut = bmesh.new()
    for _n, x, y, rb, *_rest in lenses:
        P.merge(cut, P.cyl(2 * rb + 0.6, 40, 32), T(x, y, 0))
    C.boolean_cut(face, C.cutter(cut, Lm), lip=0.3)
    a.take(face, "Faceplate", "Raked composite faceplate; the only openings are the sensor slit and the lens cluster.")
    # the plate is flat and the shell's corners fall away behind it: a frame closes that wedge
    a.add("Faceplate_Carrier", P.ring_solid([(x * 0.975, y * 0.965) for x, y in fp],
                                            P.chamfer_poly([(-56, -43), (59, -43), (66.5, 31), (-66.5, 31)], [14, 8, 6, 6]),
                                            -11.0, 0.3),
          "Frame behind the faceplate's edge: seats the flat plate on the curved front shell and seals the sensor bay.",
          "cfrp", Pm, bevel=0.4, seg=1)
    a.add("Slit_Bezel", P.ring_solid(P.rrect(128, 19, 5), P.rrect(PR.SLIT_W, PR.SLIT_H, 3), -7.0, -2.0),
          "Recessed bezel framing the sensor slit and clamping its window.", "alu", Fm @ T(0, dz, 0), bevel=0.4)
    a.add("Slit_Window", P.prism(P.rrect(PR.SLIT_W + 4, PR.SLIT_H + 3, 3.5), -PR.SLIT_RECESS - 1.6, -PR.SLIT_RECESS),
          "Smoked window set back in the slit, protecting the stereo cameras.", "glass", Fm @ T(0, dz, 0), bevel=0.2,
          seg=1)
    a.add("Slit_Emitter", P.prism(P.rrect(108, 2.2, 1.0), -8.4, -7.8), "Cyan status strip along the foot of the slit, "
          "behind the window.", "emissive", Fm @ T(0, dz - 3.4, 0), bevel=0)
    a.add("Camera_Bracket", P.prism(P.chamfer_poly(P.rrect(120, 18), 4), -26.0, -22.0),
          "Bracket holding the stereo camera pair at a fixed baseline behind the slit.", "alu", Fm @ T(0, dz, 0),
          bevel=0.4)
    for o, tag in ((1, "Left"), (-1, "Right")):
        cam = P.cyl(15, 13, 24)
        cam.transform(T(0, 0, -15.5))
        P.merge(cam, P.cyl(11, 1.2, 24), T(0, 0, -8.6), mat_index=1)
        a.add(f"Stereo_Camera_{tag}", cam, f"{tag} camera of the forward stereo pair.", ["fastener", "glass"],
              Fm @ T(o * 38, dz + 0.8, 0), bevel=0.3, seg=1)

    # lens cluster: machined plate let into the faceplate, three barrels of different bore and
    # height through it, each locked by a knurled ring, glass well down inside
    bez = a.add("Lens_Cluster_Bezel", P.prism(bz, -1.2, 2.4),
                "Machined plate let into the left cheek that carries the three lens barrels.", "alu", Lm, bevel=0.5)
    cut = bmesh.new()
    for _n, x, y, rb, *_rest in lenses:
        P.merge(cut, P.cyl(2 * rb + 0.2, 30, 48), T(x, y, 0))
    C.boolean_cut(bez, C.cutter(cut, Lm), lip=0.3)
    rings = bmesh.new()
    for n, x, y, rb, zb, rec, convex, fn in lenses:
        ri = rb - 1.8
        lens = P.revolve([(ri, -9.0), (rb, -9.0), (rb, zb - 0.6), (rb - 0.6, zb), (ri + 0.5, zb), (ri, zb - 0.5)], 48)
        zg, rg = zb - rec, ri + 0.2
        if convex:
            gp = [(0, zg - 1.6), (rg, zg - 1.6), (rg, zg - 0.9)]
            gp += [(rg * math.cos(math.radians(d)), zg - 0.9 + 0.9 * math.sin(math.radians(d))) for d in (22, 45, 68)]
            gp += [(0, zg)]
        else:
            gp = [(0, zg - 1.6), (rg, zg - 1.6), (rg, zg), (0, zg)]
        P.merge(lens, P.revolve(gp, 48), mat_index=1)
        a.add(n, lens, fn, ["fastener", "glass"], Lm @ T(x, y, 0), bevel=0)
        P.merge(rings, knurl_ring_bm(2 * rb + 2.4, 2 * rb - 0.2, 2.4, 5.6), T(x, y, 0))
    a.add("Lens_Retaining_Rings", rings, "Three knurled rings locking the lens barrels down onto the bezel.", "ti", Lm,
          bevel=0)
    a.add("Lidar_Unit", P.cyl(20, 34, 32), "Scanning lidar body behind its cheek window.", "alu",
          Lm @ T(-7.0, -13.0, -26), bevel=0.8)
    a.add("Thermal_Imager_Core", P.box(24, 18, 24), "Uncooled thermal imager core behind its objective.", "alu",
          Lm @ T(1.5, 9.5, -21), bevel=0.8)
    a.add("Spotter_Camera_Body", P.cyl(12, 26, 24), "Long-focus spotter camera body behind its hood.", "alu",
          Lm @ T(9.5, -15.5, -22), bevel=0.6)

    jawg = a.add("Jaw_Guard", P.loft([A.csec(0, 62, 30, 0, 0, 0.2), A.csec(13, 50, 20, 0, -1, 0.24)]),
                 "Short guard under the slit with two louvred intakes for the sensor bay.", "armour",
                 Fm @ T(-8, -33, 0), bevel=1.0, seg=3)
    for o in (1, -1):
        A.slots(jawg, Fm @ T(-8 + o * 12, -34, 13), 3, 14, 2.2, 4.6, depth=8, lip=0.2)

    # ── electronics under the cap ───────────────────────────────────────────
    Bd = W @ T(0, -32, Z1 + 16)
    a.add("Processor_Board", P.box(98, 72, 2), "Sensor fusion board under the cap, on standoffs above the skull frame.",
          "cfrp", Bd, bevel=0.2, seg=1)
    so, seats = bmesh.new(), []
    for x in (-45, 45):
        for y in (-32, 32):
            P.merge(so, P.cyl(6.5, 7.0, 6), T(x, y, -4.5))
            seats.append(Bd @ T(x, y, 1.0))
    a.add("Board_Standoffs", so, "Four hex standoffs lifting the processor board off the frame's top deck.", "alu", Bd,
          bevel=0.2, seg=1)
    a.take(mech.fasteners("_bs", seats, "M4"), "Board_Screws", "Screws through the processor board into its standoffs.")
    a.add("Heat_Spreader", D.finned_block_bm(82, 58, 20, fins=10), "Finned heat spreader on the processor; its air "
          "leaves through the cap's arch mesh and eyelets.", "alu", W @ T(0, -32, Z1 + 17), bevel=0.3, seg=1)
    # off the centreline: the neck yaw motor stands directly below the middle of the skull base
    conn, tail = H.connector("_nc", W @ Vector((-24, 56, Z0 + 2)), (0, 0, -1), 11.0)
    a.take(conn, "Neck_Connector", "Bulkhead connector carrying head power and data down through the neck.")
    for i, x in enumerate((-16, 16)):
        pts = [W @ Vector((x, 2, Z1 + 16)), W @ Vector((x * 1.4, 34, Z1 - 6)), W @ Vector((x * 0.9, 54, 1590)),
               W @ Vector((-24 + x * 0.25, 56, Z0 + 14))]
        a.take(H.cable("_hc", pts, 3.2, sag=0.0), f"Head_Harness_{'AB'[i]}",
               "Braided harness from the processor board to the neck connector.")

    # ── cap: crown ──────────────────────────────────────────────────────────
    crown = raw(P.thicken(crown_bm(h), PR.CAP_SHELL), Cm, "cap", 1.0, 3)
    eye_z = 0.70 * h
    cut, gr = bmesh.new(), bmesh.new()
    grommet = [(2.6, -4.7), (3.25, -4.7), (3.25, 0.0), (5.6, 0.0), (5.6, 0.5), (5.0, 1.0), (3.4, 1.0), (2.6, 0.4)]
    for k in range(6):                                           # one vent in the middle of every gore
        m = surf(math.radians(60 * k), eye_z, h)
        P.merge(cut, P.cyl(6.6, 20, 20), m)
        P.merge(gr, P.revolve(grommet, 24), m @ T(0, 0, -0.15))
    C.boolean_cut(crown, C.cutter(cut, Cm), lip=0.3)
    # recessed flat on the left gore for the unit number: a stencil draped over a handful of vertices needs
    # a face that is straight up and down, and the recess keeps the paint clear of whatever the cap brushes
    pn = (Cm.to_3x3() @ Vector(NUMBER_N)).normalized()
    ps = D.seats_on(crown, [Cm @ Vector(crown_pt(math.radians(NUMBER_AT[0]), NUMBER_AT[1], h, 20.0))], pn,
                    x_hint=(0, 1, 0))[0]
    hw, hh, ncol = 28.5, 20.5, 24
    xs = [-hw + 2 * hw * i / ncol for i in range(ncol + 1)]
    ends = D.seats_on(crown, [ps @ Vector((x, y, 0.0)) for x in xs for y in (-hh, hh)], ps.col[2].xyz)
    assert len(ends) == 2 * len(xs), "number flat: a sample missed the crown"
    inv, secs = ps.inverted(), []
    for i, x in enumerate(xs):
        z0, z1 = ((inv @ ends[2 * i + k].translation).z - 0.35 for k in (0, 1))
        hy = hh - max(0.0, abs(x) - (hw - 4.0))                  # clipped corners
        f0, f1 = (z0 + (z1 - z0) * (y + hh) / (2 * hh) for y in (-hy, hy))
        secs.append([(x, -hy, f0), (x, hy, f1), (x, hy, f1 + 14.0), (x, -hy, f0 + 14.0)])
        if i == ncol // 2:
            print("MEASURE number_flat_depth", round(-(z0 + z1) / 2, 2), "of", PR.CAP_SHELL)
    C.boolean_cut(crown, C.cutter(P.loft(secs, cap=True), ps), lip=0.3)
    a.take(crown, "Cap_Crown", "Rigid six-gore crown shell: armour over the cranium and housing for the head electronics; "
           "the recessed flat on its left gore carries the unit number.", zone="cap")
    a.add("Cap_Eyelets", gr, "Six flanged eyelets, one per gore, venting warm air from the heat spreader.", "ti", Cm,
          bevel=0, zone="cap")

    Brel = T(0, 96, 0) @ R("X", -(PR.BRIM_RAKE - tilt)) @ T(0, -96, -1)
    Bm, Binv = Cm @ Brel, Brel.inverted()

    def join_z(ang, g, lift=0.0):
        """Height on the crown (pushed out by g) that lies `lift` above the brim's top surface."""
        z = 6.0
        for _ in range(10):
            pb = Binv @ Vector(crown_pt(ang, z, h, g))
            z -= pb.z - (brim_top(pb.x) + lift)
        return z

    def on_brim(ang, g, lift):
        return Vector(crown_pt(ang, join_z(ang, g, lift), h, g))

    # seams: six raised double seams from the rim to the button, the forehead one stopping at the arch
    ribs = bmesh.new()
    for k in range(6):
        ang = math.radians(30 + 60 * k)
        z_lo = 10.4
        if k == 1:
            z_lo = join_z(ang, 0.0) + 14.6                       # above the brim flange
        elif k == 4:
            z_lo = ARCH_Z + 1.2                                  # above the arch
        rpl = math.hypot(PR.CAP_W / 2 * abs(math.cos(ang)) ** (2 / 2.2), PR.CAP_L / 2 * abs(math.sin(ang)) ** (2 / 2.2))
        phi_hi = math.acos((20.8 / rpl) ** (side_exp(ang) / 2))  # ends against the button's gasket
        P.merge(ribs, rib_bm(ang, zphi(ang, z_lo, h), phi_hi, h))
    a.add("Cap_Seam_Ribs", ribs, "Raised double seams over the six gore joints: they stiffen the crown and seal the bond "
          "lines.", "cap", Cm, bevel=0.3, seg=1, zone="cap")

    # button: the antenna, where a cap has its button
    top = Vector((0, SHEAR, h))
    rb_, hb = PR.CAP_BUTTON_D / 2, PR.CAP_BUTTON_H * 0.7
    rd = rb_ * 0.7
    btn = [(0, -2.0), (rb_, -2.0), (rb_, 0.9), (rb_ - 0.9, 1.8), (rd + 0.8, 1.8)]
    btn += [(rd * math.cos(math.radians(d)), 1.8 + (hb - 1.8) * math.sin(math.radians(d))) for d in range(0, 90, 9)]
    btn += [(0, hb)]
    a.add("Cap_Button", P.revolve(btn, 64), "Domed antenna radome where a cap has its button; the six seams meet under "
          "its collar.", "cap", Cm @ T(*top), bevel=0.4, zone="cap")
    a.add("Button_Gasket", P.revolve(P.ring_profile(rb_ - 0.5, rb_ + 2.2, -1.6, 1.0, 0.4), 64),
          "Gasket sealing the antenna button to the crown.", "rubber", Cm @ T(*top), bevel=0, zone="cap")

    # ── cap: rim ────────────────────────────────────────────────────────────
    a.add("Cap_Carrier", band_bm(h, -0.4, 16.0, -4.0, 3.0, n=144, rows=3),
          "Carbon ring inside the crown that bolts the cap to the skull frame.", "cfrp", Cm, bevel=0.3, seg=1, zone="cap")
    rim_o = [crown_pt(2 * math.pi * i / 96, 0.0, h, -0.6)[:2] for i in range(96)]
    rim_i = [crown_pt(2 * math.pi * i / 96, 0.0, h, -27.0)[:2] for i in range(96)]
    a.add("Cap_Base_Flange", P.ring_solid(rim_o, rim_i, -2.6, -0.4), "Flange closing the underside of the cap rim onto the "
          "skull.", "cfrp", Cm, bevel=0.3, seg=1, zone="cap")
    sb = a.add("Cap_Sweatband", band_bm(h, 0.0, 10.0, 0.9, 1.6, math.radians(-53.6), math.radians(233.6), 168, 2),
               "Clamp band round the base of the crown, in a satin finish; it ends at the strap anchors.", "cfrp", Cm,
               bevel=0.4, seg=1, zone="cap")
    seats = [Cm @ surf(math.radians(d), 5.0, h, 0.9) for d in (18, 162, 222, 318)]
    a.take(mech.fasteners("_cs", seats, "M4", "csk", target=sb), "Cap_Retaining_Screws",
           "Four countersunk screws holding the cap to the skull frame through the band.", zone="cap")

    # ── cap: snapback arch. Mesh-backed exhaust above, toothed strap and latch across its foot ──
    a0, a1 = A_FRONT - ARCH_A - math.radians(3), A_FRONT + ARCH_A + math.radians(3)
    mesh = bmesh.new()
    uv = mesh.loops.layers.uv.new("UVMap")
    grid = [[mesh.verts.new(crown_pt(a0 + (a1 - a0) * i / 24, 58 * j / 12, h, -7.3)) for i in range(25)]
            for j in range(13)]
    for j in range(12):
        for i in range(24):
            f = mesh.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
            for lp in f.loops:
                lp[uv].uv = (lp.vert.co.x * C.MM, lp.vert.co.z * C.MM)
    a.add("Cap_Arch_Mesh", mesh, "Fine mesh across the forehead arch: exhaust for the head electronics.", "mesh", Cm,
          bevel=0, zone="cap")
    baffle = band_bm(h, -0.4, 60.0, -13.0, 1.5, a0 - 0.02, a1 + 0.02, 20, 7)
    for ang in (a0 - 0.02, a1 + 0.02):                           # cheeks that seat it against the carrier and the crown
        wall = bmesh.new()
        rows_ = [(wall.verts.new(crown_pt(ang, -0.4 + 60.4 * j / 6, h, -4.1)),
                  wall.verts.new(crown_pt(ang, -0.4 + 60.4 * j / 6, h, -14.5))) for j in range(7)]
        for (p, q), (r_, s_) in zip(rows_, rows_[1:]):
            wall.faces.new((p, q, s_, r_))
        P.merge(baffle, P.thicken(wall, 1.5, center=crown_pt(A_FRONT, 30.0, h, -9.0)))
    a.add("Cap_Arch_Baffle", baffle, "Dark light trap behind the arch mesh, standing on the base flange: air passes over "
          "it, the electronics stay out of sight.", "cavity", Cm, bevel=0, zone="cap")

    def steps(d0, d1, step):
        n = max(1, round(abs(d1 - d0) / step))
        return [d0 + (d1 - d0) * i / n for i in range(n + 1)]

    st = [(d, 0.0, 2.2, 2.0, 15.0) for d in steps(259.0, 274.6, 1.3)]
    for t in steps(276.4, 290.8, 1.6):                           # saw teeth, clear of the latch
        st += [(t - 0.55, 0.0, 2.2, 2.0, 15.0), (t - 0.45, 0.0, 3.5, 2.0, 15.0), (t + 0.5, 0.0, 2.3, 2.0, 15.0)]
    st += [(291.8, 0.0, 2.2, 2.0, 15.0), (292.4, 0.0, 2.2, 2.0, 15.0)]
    st += [(d, 0.0, 5.6, 1.5, 15.5) for d in steps(293.2, 306.0, 1.6)]
    ladder = a.add("Cap_Strap_Ladder", strap_bm(h, st), "Toothed strap from the left of the arch: the latch bites its "
                   "teeth to draw the crown rim tight.", "rubber", Cm, bevel=0.3, seg=1, zone="cap")
    st = [(d, 0.0, 5.6, 1.5, 15.5) for d in steps(234.0, 246.8, 1.6)]
    st += [(d, 2.4, 4.6, 2.0, 15.0) for d in steps(247.6, 270.4, 1.2)]
    band = a.add("Cap_Strap_Band", strap_bm(h, st), "Plain strap from the right of the arch, overlapping the toothed one "
                 "and carrying the latch.", "rubber", Cm, bevel=0.3, seg=1, zone="cap")
    st = [(d, 4.7, 6.2, 1.2, 15.8) for d in steps(261.6, 270.4, 1.1)]
    st += [(d, 2.3, 6.2, 1.2, 15.8) for d in steps(270.6, 274.6, 1.0)]       # pawl block, down on the ladder
    latch = strap_bm(h, st)
    for z0, z1 in ((1.2, 3.4), (13.6, 15.8)):                                # rails either side of the lever
        P.merge(latch, strap_bm(h, [(d, 6.0, 8.4, z0, z1) for d in steps(262.4, 274.6, 1.1)]))
    st = [(262.0, 6.6, 10.0, 3.9, 13.1), (262.9, 6.6, 10.0, 3.9, 13.1), (263.4, 6.6, 8.2, 3.9, 13.1)]   # thumb tab
    for t in (264.4, 265.5, 266.6):                                          # grip ridges
        st += [(t - 0.3, 6.6, 8.2, 3.9, 13.1), (t - 0.2, 6.6, 8.9, 3.9, 13.1), (t + 0.2, 6.6, 8.9, 3.9, 13.1),
               (t + 0.3, 6.6, 8.2, 3.9, 13.1)]
    st += [(d, 6.6, 8.2, 3.9, 13.1) for d in steps(267.4, 273.6, 1.03)]
    P.merge(latch, strap_bm(h, st))
    a.add("Cap_Strap_Latch", latch, "Latch on the end of the plain strap: its pawl holds the ladder, its lever lets the "
          "cap off for service.", "ti", Cm, bevel=0.4, seg=1, zone="cap")
    a.add("Cap_Strap_Latch_Pin", P.cyl(3.0, 17.4, 16), "Pivot pin of the strap latch lever, through both rails.", "steel",
          Cm @ surf(math.radians(272.8), 8.5, h, 7.3) @ R("X", -90), bevel=0.2, seg=1, zone="cap")
    for part, angs, tag in ((ladder, (297.0, 302.6), "Left"), (band, (237.4, 243.0), "Right")):
        seats = [Cm @ surf(math.radians(d), 8.5, h, 5.6) for d in angs]
        a.take(mech.fasteners("_ss", seats, "M4", target=part), f"Cap_Strap_Screws_{tag}",
               f"Two screws anchoring the {tag.lower()} strap end to the crown.", zone="cap")

    # ── cap: brim. Cambered bill over the nape, rolled edge, ribs underneath, bolted flange ──
    b_a0 = math.acos((PR.BRIM_W / PR.CAP_W) ** 1.1)
    ys = crown_pt(b_a0, 0, h)[1]
    n_ = 2.8
    tip = PR.CAP_L / 2 + PR.BRIM_L
    edge = [(PR.BRIM_W / 2 * math.copysign(abs(math.cos(u)) ** (2 / n_), math.cos(u)),
             ys - 4 + (tip - ys + 4) * max(math.sin(u), 0.0) ** (2 / n_)) for u in [math.pi * i / 64 for i in range(65)]]
    inner = [(x * 0.97, y - 3.0) for x, y, _z in (crown_pt(b_a0 + (math.pi - 2 * b_a0) * (1 - i / 36), 0, h)
                                                   for i in range(1, 36))]
    yc = tip - 17.0                                              # centreline of the sensor bar under the lip

    def rib(x, y0, y1, d0, d1, w):
        prof = [(y0, 0.3), (y1, 0.3), (y1, -d1), (y0, -d0)]
        return P.loft([[(x - w / 2, y, z) for y, z in prof], [(x + w / 2, y, z) for y, z in prof]], cap=True)

    brim = P.prism(inset(edge, 1.5) + inner, 0.0, PR.BRIM_T)
    for o in (1, -1):
        P.merge(brim, rib(o * 29, 106, 166, 7.0, 1.5, 3.0))      # gussets down to the cap's base flange
        P.merge(brim, rib(o * 58, 93, 148, 5.0, 1.5, 3.0))
    P.merge(brim, rib(0, 109, yc - 5.5, 5.5, 5.5, 9.0))           # hollow centre rib: the sensor lead runs in it
    camber(brim, 36)
    bead = P.sweep([(x, y, PR.BRIM_T / 2) for x, y in inset(edge, 3.0)], 3.0, 16)
    P.merge(brim, camber(bead))
    a.add("Cap_Brim", brim, "Cambered brim over the nape with a rolled edge and stiffening ribs: shades and shelters the "
          "rear-aspect sensors under its lip.", "cap", Bm, bevel=0.6, seg=2, zone="cap")

    f0 = b_a0 + math.radians(8)
    f1 = math.pi - f0
    secs = []
    for i in range(57):
        ang = f0 + (f1 - f0) * i / 56
        u = min(1.0, min(ang - f0, f1 - ang) / math.radians(22))
        gf = 7.0 + 10.0 * u * u * (3 - 2 * u)                    # the foot narrows where the brim does
        zc = join_z(ang, 0.0)
        secs.append([on_brim(ang, -0.3, -0.6), on_brim(ang, gf, -0.6), on_brim(ang, gf, 2.8), on_brim(ang, 5.4, 2.8),
                     Vector(crown_pt(ang, zc + 14.0, h, 5.4)), Vector(crown_pt(ang, zc + 14.0, h, -0.3))])
    fl = a.add("Brim_Flange", P.loft(secs, cap=True), "Angle flange joining brim to crown: one leg screwed to the crown, "
               "the foot screwed down on the brim.", "ti", Cm, bevel=0.6, seg=2, zone="cap")
    seats = []
    for d in (48, 69, 90, 111, 132):
        ang = math.radians(d)
        seats.append(Cm @ surf(ang, join_z(ang, 0.0) + 8.4, h, 5.4))
    a.take(mech.fasteners("_fc", seats, "M4", target=fl), "Brim_Flange_Screws", "Five screws through the flange's upright "
           "leg into the crown.", zone="cap")
    seats = []
    for d in (66, 82, 98, 114):
        p = on_brim(math.radians(d), 11.2, 2.8)
        th = (Binv @ p).x / BRIM_RAD
        seats.append(Cm @ frame(p, Brel.to_3x3() @ Vector((math.sin(th), 0, math.cos(th))), (1, 0, 0)))
    a.take(mech.fasteners("_ff", seats, "M4", "csk", target=fl), "Brim_Foot_Screws", "Four countersunk screws through the "
           "flange's foot into the brim.", zone="cap")

    pod = P.prism(P.chamfer_poly(P.rrect(104, 13), 3), -8.5, 0.3)
    pod.transform(T(0, yc, 0))
    bar = a.add("Rear_Sensor_Bar", camber(pod, 20), "Housing for the three rear-aspect sensors, following the camber "
                "under the brim lip.", "alu", Bm, bevel=0.5, zone="cap")
    seats = [Bm @ camber_frame(x, yc, -8.5) @ R("X", 180) for x in (-42, 42)]
    a.take(mech.fasteners("_sp", seats, "M4", target=bar), "Rear_Sensor_Screws", "Two screws holding the rear sensor "
           "bar up into the brim.", zone="cap")
    for i, x in enumerate((-31, 0, 31)):
        a.add(f"Rear_Sensor_Window_{i + 1}", P.prism(P.rrect(19, 4.6, 1.6, 3), 0, 1.2),
              "Flush window of a rear-aspect sensor.", "glass", Bm @ camber_frame(x, yc + 5.6, -4.3) @ R("X", -90),
              bevel=0, zone="cap")
    for i, x in enumerate((-46.5, 46.5)):
        a.add(f"Brim_Status_LED_{i + 1}", P.cyl(3.2, 1.2, 12), "Status indicator visible from behind.", "emissive",
              Bm @ camber_frame(x, yc + 6.2, -4.3) @ R("X", -90), bevel=0, zone="cap")
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    lo, hi = C.bounds_mm([o for o in objs if o.get("zone") == "cap"])
    print("MEASURE cap_top_z", round(hi.z, 2), "cap_x", round(lo.x, 2), round(hi.x, 2), "cap_y", round(lo.y, 2),
          round(hi.y, 2))
    W = FR.torso()
    c = W @ Vector((0, 10, 1640))
    shots = (("front", (-0.45, -1.0, 0.12), "clay", c, 2.4),
             ("right", (-1.0, -0.45, 0.1), "clay", c, 2.4),
             ("left", (1.0, -0.4, 0.12), "clay", c, 2.4),
             ("rear", (0.55, 1.0, 0.25), "clay", c, 2.4),
             ("under", (-0.45, 1.0, -0.3), "clay", W @ Vector((0, 90, 1620)), 2.0),
             ("top", (0.08, -0.5, 1.0), "clay", W @ Vector((0, 20, 1690)), 2.4),
             ("strap", (-0.3, -1.0, 0.15), "clay", W @ Vector((0, -105, 1650)), 1.05),
             ("lens", (0.45, -1.0, 0.05), "clay", W @ Vector((43, -112, 1586)), 0.8),
             ("front_final", (-0.5, -1.0, 0.1), "final", c, 2.4),
             ("rear_final", (0.6, 1.0, 0.3), "final", c, 2.4))
    for name, d, mode, target, dist in shots:
        RV.closeup(objs, out / f"01_head_{name}{tag}.jpg", f"01 head and cap, {name}", d, mode, isolate=True,
                   target=target, dist=dist, res=(1300, 1100))
