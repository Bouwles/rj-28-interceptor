"""Assembly 15: interceptor mount.

A swing-arm mount with one main axis. The trunnion sits low behind the right
shoulder; the cannon rides BORE_RISE above it on a swing arm. Level, the
barrel lies over the shoulder armour; swung up 90 degrees it stands behind
the shoulder. The weapon itself is a prop described at headline level; the
engineering here is the mechanism that carries and moves it.

Groups: "elev" parts turn about the trunnion and ride the traverse, "trav"
parts turn about the slewing ring only, everything else is fixed.

Frames:
  Cn  cannon frame on the bore above the trunnion: +Z forward, +Y up, +X inboard.
  A0  side-plate frame on the inboard face of the swing arm, at the trunnion:
      +X forward, +Y up, +Z outboard.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from .. import frames as FR, params as PR, poses
from ..lib import armour as A, core as C, detail as D, fittings as F, mech, prims as P
from ..lib.core import MM, T, R, frame
from ..parts import Asm, raw

E, TV = "elev", "trav"
ZE, ZT, ZF, ZP, ZL, ZC = "mount_elev", "mount_trav", "mount_fix", "mount_pin", "lock", "mount_chain"

CHAIN_X_OFF = 23.0            # chain plane: centre of the feed box, inboard of the breech flank
CHAIN_FIX = (152.0, 1432.0)   # fixed end on the backpack side (world y, z); the chain leaves it upward
CHAIN_LEN = 166.0             # just over the longer of the two end-state paths, so neither state kinks
CHAIN_LINKS = 10
YZ = Matrix(((0, 0, -1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))     # outline drawn in world (y, z), extruded along -X

# hardpoint flange on the backpack's right side (the backpack cuts matching holes in its pad and panel)
FLANGE_Y_OFF = 8.0            # flange centre aft of the trunnion (world y)
FLANGE_LEN = 80.0
HP_BOLT_DY = (-16.0, 16.0)
HP_BOLT_Z = (1214.0, 1252.0, 1290.0)


def _ends(outline, z0, z1, end=14.0, k=0.9):
    """Prism whose two ends are pulled in, giving the end faces a broad chamfer."""
    cx = sum(p[0] for p in outline) / len(outline)
    cy = sum(p[1] for p in outline) / len(outline)
    small = [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in outline]
    return P.loft([P.at_z(small, z0), P.at_z(outline, z0 + end), P.at_z(outline, z1 - end), P.at_z(small, z1)])


def _union(pieces, matrix, mat, bevel=1.0, seg=2, lip=0.6):
    """Weld overlapping pieces into one clean solid. Merged-but-overlapping shells
    break later boolean cuts, so anything that will be cut is unioned first."""
    ob = raw(pieces[0], matrix, mat, bevel, seg)
    for bm in pieces[1:]:
        C.boolean_join(ob, C.cutter(bm, matrix), lip=lip)
    return ob


def _arc(r, a0, a1, n=24):
    return [(r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


# ── energy chain ─────────────────────────────────────────────────────────────
def _hermite(p0, t0, p1, t1, k, n=160):
    pts = []
    for i in range(n + 1):
        t = i / n
        h00, h10 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t
        h01, h11 = -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
        pts.append(p0 * h00 + t0 * (k * h10) + p1 * h01 + t1 * (k * h11))
    return pts


def _path_of_length(p0, t0, p1, t1, length):
    """Smooth path from p0 (leaving along t0) to p1 (arriving along t1) with a
    given arc length: the slack goes into the bend, as it does in a real carrier."""
    def plen(k):
        pts = _hermite(p0, t0, p1, t1, k)
        return sum((b - a).length for a, b in zip(pts, pts[1:])), pts
    lo, hi = 1.0, 1500.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if plen(mid)[0] < length:
            lo = mid
        else:
            hi = mid
    return plen((lo + hi) / 2)[1]


def _link_frames(path, n):
    """n link frames evenly along a path: local X across the chain, Y along it."""
    d = [0.0]
    for a, b in zip(path, path[1:]):
        d.append(d[-1] + (b - a).length)
    out = []
    for i in range(n):
        s = d[-1] * (i + 0.5) / n
        j = max(1, next(k for k, v in enumerate(d) if v >= s))
        f = (s - d[j - 1]) / max(1e-9, d[j] - d[j - 1])
        pos = path[j - 1].lerp(path[j], f)
        tan = (path[j] - path[j - 1]).normalized()
        nrm = Vector((1, 0, 0)).cross(tan)
        m = Matrix((Vector((1, 0, 0)), tan, nrm)).transposed().to_4x4()
        m.translation = pos
        out.append(m)
    return out


def chain_ends(elev):
    """Fixed end, its tangent, moving end and arrival tangent (mm, world) at an elevation."""
    Cn = FR.cannon()
    hw = PR.BREECH_W / 2
    Em = poses.elev_matrix(elev)
    m1 = Em @ (Cn @ Vector((hw + CHAIN_X_OFF, -49.0, 30.0)))
    t1 = (Em.to_3x3() @ (Cn.to_3x3() @ Vector((0, 1, 0)))).normalized()
    p0 = Vector((m1.x, CHAIN_FIX[0], CHAIN_FIX[1]))
    return p0, Vector((0, 0, 1)), m1, t1


def _link_bm():
    """One carrier link: chamfered frame with a pivot boss each side."""
    ln = CHAIN_LEN / CHAIN_LINKS - 1.2
    bm = P.prism(P.chamfer_poly(P.rrect(ln, 13.0), 2.6), -12.0, 12.0)       # section (along, normal), extruded across
    bm.transform(Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1))))   # -> X across, Y along, Z normal
    for sgn in (1, -1):
        P.merge(bm, P.cyl(8.0, 2.4, 12), T(sgn * 13.2, ln / 2 - 4.0, 0) @ R("Y", 90))
    return bm


def _chain(a):
    lay_name = "rj28_link"
    frames = {e: _link_frames(_path_of_length(*chain_ends(e), CHAIN_LEN), CHAIN_LINKS) for e in (0.0, 90.0)}
    template = _link_bm()
    me = bpy.data.meshes.new("_link")
    template.to_mesh(me)
    template.free()
    bm = bmesh.new()
    lay = bm.verts.layers.int.new(lay_name)
    for i, m in enumerate(frames[0.0]):
        n0 = len(bm.verts)
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        for v in bm.verts[n0:]:
            v.co = m @ v.co
            v[lay] = i
    bpy.data.meshes.remove(me)
    n = len(bm.verts)
    ob = a.add("Energy_Chain", bm, "Flexible cable carrier taking power and data from the backpack to the breech.",
               "rubber", None, bevel=0, zone=ZC)
    mesh = ob.data
    assert len(mesh.vertices) == n, "energy chain lost vertices"
    idx = [d.value for d in mesh.attributes[lay_name].data]
    ob.shape_key_add(name="Basis")
    key = ob.shape_key_add(name="stowed")
    for vi, v in enumerate(mesh.vertices):
        i = idx[vi]
        local = frames[0.0][i].inverted() @ (v.co / MM)
        key.data[vi].co = (frames[90.0][i] @ local) * MM
    ob["mount_morph"] = "stowed"
    return ob


# ── build ────────────────────────────────────────────────────────────────────
def build():
    a = Asm("15")
    xb, yt, zt, rise = PR.BORE_X, PR.TRUNNION_Y, PR.TRUNNION_Z, PR.BORE_RISE
    fwd, aft = PR.BREECH_FWD, PR.BREECH_AFT
    hw, hh = PR.BREECH_W / 2, PR.BREECH_H / 2
    r = PR.BARREL_OD / 2
    z1 = fwd + PR.BARREL_L
    rod_l = min(300.0, PR.BARREL_L * 0.58)
    Cn = FR.cannon()
    A0 = T(xb - hw - 5, yt, zt) @ FR.side_plate()
    zb = zt - PR.YOKE_DROP                         # top of the yoke base

    def el(short, bm, fn, mat, m, bevel=0.8, seg=2, zone=ZE):
        return a.add(short, bm, fn, mat, m, bevel=bevel, seg=seg, zone=zone, group=E)

    def tr(short, bm, fn, mat, m, bevel=0.8, seg=2):
        return a.add(short, bm, fn, mat, m, bevel=bevel, seg=seg, zone=ZT, group=TV)

    def el_take(ob, short, fn, zone=ZE):
        return a.take(ob, short, fn, zone=zone, group=E)

    def tr_take(ob, short, fn):
        return a.take(ob, short, fn, zone=ZT, group=TV)

    # ── breech housing ──────────────────────────────────────────────────────
    pieces = [_ends(P.chamfer_poly(P.rrect(PR.BREECH_W, PR.BREECH_H), 26), -aft, fwd, 20, 0.88)]
    roof = P.prism(P.chamfer_poly(P.rrect(64, 24), [0, 0, 8, 8]), -8, 58)                             # recoil unit seat
    roof.transform(T(0, hh + 6, 0))
    pieces.append(roof)
    for sx in (1, -1):                                              # guide rod anchor blocks on the roof
        blk = P.prism(P.chamfer_poly(P.rrect(30, 14), [0, 0, 5, 5]), 14, 62)
        blk.transform(T(sx * 46, hh + 1, 0))
        pieces.append(blk)
    breech = el_take(_union(pieces, Cn, "alu", 1.2, 3), "Breech_Housing",
                     "Breech housing: carries the barrel, the recoil gear and the feed, and bolts to the swing arm.")
    C.boolean_cut(breech, C.cutter(P.cyl(2 * r + 22.4, 16), Cn @ T(0, 0, fwd)), lip=0.5)             # barrel socket
    C.boolean_cut(breech, C.cutter(P.cyl(50.6, 80), Cn @ T(0, 106, 26)), lip=0.4)                    # recoil cylinder seat
    for sx in (1, -1):
        C.boolean_cut(breech, C.cutter(P.cyl(24.4, 80), Cn @ T(sx * 34, 76, 46)), lip=0.3)           # guide rod sockets
    D.pocket_grid(breech, Cn @ T(0, -hh, -16) @ R("X", 90), 2, 2, 46, 58, 60, 74, depth=8)           # underside lightening
    Mr = Cn @ T(0, 0, -aft) @ R("X", 180)                                                             # rear face, +Z aft
    A.recess(breech, P.rrect(100, 106, 10), Mr, depth=6.4)
    rc = el("Breech_Rear_Cover", P.prism(P.rrect(97, 103, 8.5), -6.0, 0.0),
            "Rear cover closing the breech mechanism, removable for inspection.", "alu", Mr, bevel=0.6)
    seats = [Mr @ T(sx * 39, sy * 42, 0) for sx in (1, -1) for sy in (1, 0, -1)]
    el_take(mech.fasteners("_rcs", seats, "M4", target=rc), "Breech_Rear_Cover_Screws",
            "Screws holding the breech rear cover.")
    Ms = Cn @ T(hw, 0, -60) @ R("Y", 90)                                                              # inboard flank, aft of the feed box
    A.recess(breech, P.rrect(56, 104, 6), Ms, depth=3.2)
    sc = el("Breech_Side_Cover", P.prism(P.rrect(53, 101, 4.5), -3.0, 0.0),
            "Flush cover over the breech drive on the inboard flank.", "alu", Ms, bevel=0.4)
    seats = [Ms @ T(sx * 19, sy * 43, 0) for sx in (1, -1) for sy in (1, -1)]
    el_take(mech.fasteners("_scs", seats, "M4", "csk", target=sc), "Breech_Side_Cover_Screws",
            "Countersunk screws holding the breech side cover.")

    # ── barrel: tube, lock collar, reinforce, muzzle ring ───────────────────
    zs0, zs1 = fwd + rod_l - 43.0, fwd + rod_l - 1.0             # groove the saddle and its strap seat in
    prof = [(38, fwd - 4), (r, fwd - 4), (r, zs0), (r - 3, zs0 + 1.5), (r - 3, zs1 - 1.5), (r, zs1), (r, z1 - 5),
            (r - 3, z1 - 3), (41, z1 - 3), (38, z1 - 6)]
    el("Barrel", P.revolve(prof, 64), "Interceptor cannon barrel.", "ti", Cn, bevel=0.6)
    collar = el("Barrel_Lock_Collar", P.revolve(P.ring_profile(r + 0.2, r + 10, fwd - 3.5, fwd + 17, 1.2), 64),
                "Castellated collar locking the barrel into the breech.", "fastener", Cn, bevel=0.4, seg=1)
    cut = bmesh.new()
    for i in range(8):
        P.merge(cut, P.box(10, 9, 30), R("Z", 45 * i + 22.5) @ T(r + 9, 0, fwd + 12))
    C.boolean_cut(collar, C.cutter(cut, Cn), lip=0.3)
    rp = [(r + 0.2, fwd + 17.5), (r + 10, fwd + 17.5), (r + 10, fwd + 34)]
    for i in range(3):                                           # shallow hoop grooves
        z = fwd + 36 + i * 14
        rp += [(r + 8.6, z), (r + 8.6, z + 4), (r + 10, z + 6), (r + 10, z + 12)]
    rp += [(r + 10, fwd + 84), (r + 1.2, fwd + 104), (r + 0.2, fwd + 104)]
    el("Barrel_Reinforce", P.revolve(rp, 64), "Reinforcing sleeve shrunk over the chamber end of the barrel.", "ti", Cn,
       bevel=0.5)
    mp = [(r + 0.2, z1 - 54), (r + 9, z1 - 54), (r + 12, z1 - 50), (r + 12, z1 - 30), (r + 11, z1 - 29.4),
          (r + 11, z1 - 27.6), (r + 12, z1 - 27), (r + 12, z1 - 5), (r + 8, z1), (r - 2.6, z1), (r - 2.6, z1 - 3),
          (r + 0.2, z1 - 3)]
    el("Muzzle_Ring", P.revolve(mp, 64), "Plain reinforcing ring protecting the muzzle.", "ti", Cn, bevel=0.5)

    # ── soft-recoil cradle on top of the barrel ─────────────────────────────
    for sx in (1, -1):
        rodp = [(0, fwd - 70), (10, fwd - 70), (12, fwd - 68), (12, fwd + rod_l - 2), (10, fwd + rod_l), (0, fwd + rod_l)]
        el(f"Guide_Rod_{'Inboard' if sx > 0 else 'Outboard'}", P.revolve(rodp, 24),
           "Polished guide rod the cradle saddle rides on.", "steel", Cn @ T(sx * 34, 76, 0), bevel=0)
    cyp = [(0, fwd - 90), (23, fwd - 90), (25, fwd - 88), (25, fwd - 62), (23.5, fwd - 61), (23.5, fwd + 112),
           (25, fwd + 114), (25, fwd + 136), (22, fwd + 140), (0, fwd + 140)]
    el("Recoil_Cylinder", P.revolve(cyp, 40), "Soft-recoil buffer cylinder.", "alu", Cn @ T(0, 106, 0), bevel=0.4, seg=1)
    el("Recoil_Rod", P.revolve([(0, fwd + 138), (9, fwd + 138), (9, fwd + rod_l - 6), (7, fwd + rod_l - 4),
                                (0, fwd + rod_l - 4)], 20),
       "Polished buffer rod tying the recoil cylinder to the cradle saddle.", "steel", Cn @ T(0, 106, 0), bevel=0)
    sad = P.chamfer_poly([(-58, 0), (56, 0), (56, 60), (48, 96), (24, 120), (-24, 120), (-48, 96), (-58, 60)],
                         [0, 0, 6, 7, 7, 7, 7, 6])
    Msd = Cn @ T(0, 0, fwd + rod_l - 44)
    saddle = el("Cradle_Saddle", P.prism(sad, 0, 44), "Cradle saddle: ties the barrel to the guide rods and the buffer rod.",
                "alu", Msd, bevel=1.0)
    C.boolean_cut(saddle, C.cutter(P.cyl(2 * r - 5.6, 80), Msd @ T(0, 0, 22)), lip=0.4)
    for sx in (1, -1):
        C.boolean_cut(saddle, C.cutter(P.cyl(24.5, 80), Msd @ T(sx * 34, 76, 22)), lip=0.3)
    C.boolean_cut(saddle, C.cutter(P.cyl(18.5, 80), Msd @ T(0, 106, 22)), lip=0.3)
    D.pocket_grid(saddle, Msd @ T(0, 50, 44), 1, 1, 28, 20, 0, 0, depth=5)
    seats = []
    for sx in (1, -1):
        d = (Cn.to_3x3() @ Vector((sx * 0.7071, 0.7071, 0))).normalized()
        seats += D.seats_on(saddle, [Msd @ Vector((sx * 36, 108, z)) for z in (11, 33)], d,
                            x_hint=Cn.to_3x3() @ Vector((0, 0, 1)))
    el_take(mech.fasteners("_sds", seats, "M6", target=saddle), "Cradle_Saddle_Screws",
            "Clamp screws closing the saddle on the guide rods.")
    el("Cradle_Saddle_Strap", P.revolve(P.ring_profile(r - 2.9, r - 0.1, 3.0, 40.0, 0.6), 64, angle=180.0),
       "Lower strap seated in the barrel groove, closing the saddle around the barrel.", "ti", Msd @ R("Z", 180), bevel=0)

    # ── feed box on the inboard flank, facing the backpack ──────────────────
    fb = el("Feed_Box", P.prism(P.chamfer_poly(P.rrect(46, 90), 9), -15, 75),
            "Feed box on the breech flank facing the backpack.", "alu", Cn @ T(hw + 23, 0, 0), bevel=1.0)
    C.boolean_cut(fb, C.cutter(P.box(12.6, 14.6, 12.6), Cn @ T(hw + 40, -38, -9)), lip=0.4)          # travel lock notch
    Mf = Cn @ T(hw + 46, 4, 30) @ R("Y", 90)
    h = F.hatch("_fh", 62, 58, Mf, target=fb, hinge_side="L", fasteners=2, thickness=3.0, material="alu")
    el_take(h["door"], "Feed_Box_Door", "Loading door of the feed box.")
    el_take(h["hinge"], "Feed_Box_Door_Hinge", "Hinge of the feed box door.")
    el_take(h["fasteners"], "Feed_Box_Quarter_Turns", "Quarter-turn fasteners latching the feed box door.")

    # ── tracking head beside the barrel root ────────────────────────────────
    xo = -(r + 10 + 8 + 45)
    bk = [P.prism(P.chamfer_poly([(-152, -14), (-67, -14), (-67, 26), (-152, 26)], 6), fwd + 5.5, fwd + 16)]
    gm = P.cyl(26, 24.5, 24)                                                                          # tilt gearmotor
    gm.transform(T(-80, 50, fwd + 17.75))
    web = P.box(22, 16, 10.5)
    web.transform(T(-80, 32, fwd + 10.75))
    el_take(_union(bk + [gm, web], Cn, "ti", 0.8), "Tracker_Bracket",
            "Bracket carrying the tracking head off the swing arm, with the gearmotor for its tilt axis.")
    op = [(0, fwd + 16), (38, fwd + 16), (41, fwd + 19), (41, fwd + 30), (45, fwd + 33), (45, fwd + 80), (43.4, fwd + 81),
          (43.4, fwd + 83), (45, fwd + 84), (45, fwd + 92), (36, fwd + 92), (34, fwd + 88), (0, fwd + 88)]
    el("Tracker_Optic_Housing", P.revolve(op, 48), "Sealed housing of the tracking optic.", "alu", Cn @ T(xo, 6, 0),
       bevel=0.5)
    el("Tracker_Lens", P.revolve([(0, fwd + 88.2), (33.6, fwd + 88.2), (33.6, fwd + 90.6), (26, fwd + 92.4), (0, fwd + 93)], 48),
       "Coated front element of the tracking optic.", "glass", Cn @ T(xo, 6, 0), bevel=0)
    el("Tracker_Indicator", P.cyl(5, 1.6, 12), "Status light of the tracking head.", "emissive",
       Cn @ T(xo + 40.5 * math.cos(math.radians(60)), 6 + 40.5 * math.sin(math.radians(60)), fwd + 92.2), bevel=0)
    rf = P.prism(P.rrect(70, 52, 5), fwd + 66, fwd + 73.6)
    P.merge(rf, P.box(16, 14, 20), T(0, -34, fwd + 64))
    el("Tracker_Radar_Frame", rf, "Frame fixing the radar panel above the optic.", "alu", Cn @ T(xo, 82, 0), bevel=0.6)
    el("Tracker_Radar_Panel", P.prism(P.rrect(74, 56, 6), fwd + 74, fwd + 86), "Flat tracking radar panel.", "cfrp",
       Cn @ T(xo, 82, 0), bevel=1.0)

    # ── swing arm with the gear sector ──────────────────────────────────────
    arm = [(72 * math.cos(math.radians(g)), 72 * math.sin(math.radians(g))) for g in range(200, 341, 10)]
    arm += [(85, rise - 70), (85, rise + 55), (-105, rise + 55), (-105, rise - 70)]
    sa = el("Swing_Arm", P.prism(arm, 0, 22), "Swing arm carrying the breech above the trunnion.", "ti", A0, bevel=1.2, seg=3)
    C.boolean_cut(sa, C.cutter(P.cyl(64.4, 60), A0 @ T(0, 0, 11)), lip=0.4)                           # trunnion bore
    reb = _arc(74.5, -157, -47) + _arc(61.5, -47, -157)
    C.boolean_cut(sa, C.cutter(P.prism(reb, -2, 10.2), A0), lip=0.3)                                  # sector seat
    D.pocket_grid(sa, A0 @ T(-8, rise + 22, 22), 2, 1, 56, 44, 64, 0, depth=9)
    D.pocket_grid(sa, A0 @ T(-8, rise - 27, 22), 2, 1, 56, 24, 64, 0, depth=9)
    seats = [A0 @ T(x, y, 22) for x in (-92, 72) for y in (rise - 55, rise - 8, rise + 39)]
    el_take(mech.fasteners("_sab", seats, "M10", target=sa), "Swing_Arm_Bolts", "Bolts fixing the breech to the swing arm.")
    sector = el_take(mech.sector_gear("_sec", 2.0, 88, 104.0, 10.0, 62.0, A0 @ T(0, 0, 5) @ R("Z", -102)),
                     "Elevation_Sector", "Gear sector on the swing arm, driven by the elevation pinion.", zone=ZP)
    seats = [A0 @ R("Z", g) @ T(67, 0, 0) @ R("X", 180) for g in (-146, -124, -102, -80, -58)]
    el_take(mech.fasteners("_secs", seats, "M4", "csk", target=sector), "Elevation_Sector_Screws",
            "Countersunk screws fixing the gear sector to the swing arm.", zone=ZP)
    pin = [(0, 0), (30, 0), (32, 2), (32, 22), (44, 22), (44, 26), (32, 26.5), (32, 48), (30, 50), (0, 50)]
    el("Trunnion_Pin", P.revolve(pin, 40), "Trunnion pin: the single axis the cannon elevates and stows about.", "steel", A0,
       bevel=0, zone=ZP)

    # ── traversing yoke ─────────────────────────────────────────────────────
    rh, sw = 85.0, 50.0
    a0 = math.degrees(math.atan2(-math.sqrt(rh * rh - sw * sw), sw))
    key = [(sw, -PR.YOKE_DROP - 2.0)] + _arc(rh, a0, 180 - a0, 28) + [(-sw, -PR.YOKE_DROP - 2.0)]
    Mc = A0 @ T(0, 0, 27)
    cheek = tr("Yoke_Cheek", P.prism(key, 0, 28), "Outboard cheek of the yoke, holding the trunnion bearing.", "alu", Mc,
               bevel=1.2, seg=3)
    C.boolean_cut(cheek, C.cutter(P.cyl(100.2, 60), Mc @ T(0, 0, 14)), lip=0.4)                       # bearing bore
    C.boolean_cut(cheek, C.cutter(P.cyl(151.4, 10), Mc @ T(0, 0, 24 + 5)), lip=0.4)                   # housing register
    D.pocket_grid(cheek, Mc @ T(0, -104, 28), 1, 1, 66, 24, 0, 0, depth=9)
    tr_take(mech.bearing("_tb", 100, 64, 24, Mc @ T(0, 0, 12)), "Trunnion_Bearing",
            "Sealed bearing carrying the trunnion pin in the yoke cheek.")
    Mh = Mc @ T(0, 0, 24)
    prof, rb, zl = D.bolted_cover_profile(75, 10, 0.0, 12.0, 4.0)
    ph = tr("Pivot_Housing", P.revolve(prof, 64), "Bolted housing closing the trunnion bearing.", "alu", Mh)
    tr_take(mech.fasteners("_phs", mech.ring((0, 0, zl), (0, 0, 1), rb, 10), "M6", target=ph, matrix=Mh),
            "Pivot_Housing_Screws", "Screws clamping the pivot housing to the yoke cheek.")
    tr("Pivot_Retainer", P.tube(98, 74, 4, 0.8), "Polished ring retaining the trunnion bearing.", "steel", Mh @ T(0, 0, 16),
       bevel=0)
    tr("Elevation_Encoder", D.encoder_bm(52), "Absolute encoder reading elevation at the trunnion.", ["alu", "fastener"],
       Mh @ T(0, 0, 14) @ R("Z", -120), bevel=0.4)

    xc0, xc1 = xb - hw - 60.0, xb - 80.0
    cut = math.degrees(math.asin(12.0 / 88.0))
    dee = [(xb + x, yt + y) for x, y in _arc(88, 180 - cut, 360 + cut, 40)]
    foot = [(xc0, yt - 50), (xc1, yt - 50), (xc1, yt + 12), (xb - 110, yt + 12), (xb - 110, yt + 50), (xc0, yt + 50)]
    base = tr_take(_union([P.prism(dee, zb - 24, zb), P.prism(P.chamfer_poly(foot, [8, 0, 0, 6, 0, 8]), zb - 24.01, zb + 0.01)],
                          None, "alu", 1.0),
                   "Yoke_Base", "Yoke base on the slewing ring, flat at the rear so the breech can swing down past it.")
    D.pocket_grid(base, T(xb + 18, yt - 18, zb), 1, 1, 30, 26, 0, 0, depth=8)      # inside the bolt circle, clear of the screws
    seats = [T(xb, yt, zb) @ R("Z", g) @ T(58.5, 0, 0) for g in (190, 216.7, 243.3, 270, 296.7, 323.3, 350)]
    tr_take(mech.fasteners("_ybs", seats, "M6", target=base), "Yoke_Base_Screws",
            "Screws fixing the yoke base to the inner race of the slewing ring.")

    # elevation drive: forward of and below the trunnion, the one quadrant the cannon never sweeps
    yd, zd = yt - 50.0, zt - 85.0
    cradle = tr("Elevation_Drive_Cradle", P.prism(P.chamfer_poly(P.rrect(64, 44), 5), 0, 15),
                "Cradle seating the elevation drive on the yoke base.", "alu", T(xb - 43, yd, zb))
    C.boolean_cut(cradle, C.cutter(P.cyl(62.8, 90), T(xb - 43, yd, zd) @ R("Y", 90)), lip=0.3)
    d = mech.rotary_actuator("_ed", 62, 78, T(xb - 3, yd, zd) @ R("Y", -90), bolts=0, connector_angle=0.0)
    a.take_rotary(d, "Elevation_Drive", "elevation drive", zone=ZT, group=TV)
    tr_take(mech.gear("_pin", 2.0, 11, 12, 12.0, T(xb - hw - 10, yd, zd) @ R("Y", 90)), "Elevation_Pinion",
            "Pinion of the elevation drive, meshing with the sector on the swing arm.")
    tr("Elevation_Drive_Shaft", P.cyl(11.8, 18, 16), "Output shaft carrying the elevation pinion.", "steel",
       T(xb - 90, yd, zd) @ R("Y", 90), bevel=0)

    # ── fixed: slewing ring, traverse motor, hardpoint, gussets ─────────────
    Msr = T(xb, yt, zb - 54)
    sr = mech.slewing_ring("_sr", PR.SLEW_OD, 100.0, 30.0, bolts=12, size="M6", matrix=Msr)
    hid = sr.pop("bolts_inner")                                   # the yoke base brings its own screws
    hid_me = hid.data
    bpy.data.objects.remove(hid)
    bpy.data.meshes.remove(hid_me)
    reg = a.take_slew(sr, "Traverse_Ring", "traverse", zone=ZF)
    reg["inner"]["zone"], reg["inner"]["mount_group"] = ZT, TV    # the inner race turns with the yoke
    tm = P.tube(96, 58, 22, 1.0)
    P.merge(tm, P.box(22, 16, 16), T(0, 0, -19))
    a.add("Traverse_Motor", tm, "Direct-drive torque motor inside the slewing ring, turning the yoke in traverse.", "alu",
          Msr @ T(0, 0, 13), bevel=0.5, zone=ZF)

    xf0, xf1 = -PR.PACK_HALF_W - 4.0, -PR.PACK_HALF_W - 20.0      # mounting flange against the backpack pad
    yfc = yt + FLANGE_Y_OFF                                       # flange centre: inside the backpack's side panel
    hp = [(xf0, -84), (xb - 70, -84), (xb - 92, -60), (xb - 92, 60), (xb - 70, 84), (xf0, 84)]
    flange = P.box(xf0 - xf1, FLANGE_LEN, zb - 44 - 1196)
    flange.transform(T((xf0 + xf1) / 2, yfc, (zb - 44 + 1196) / 2))
    hard = a.take(_union([P.prism(P.chamfer_poly([(x, yt + y) for x, y in hp], [0, 10, 10, 10, 10, 0]), zb - 84, zb - 54),
                          flange], None, "ti", 1.2, 3),
                  "Hardpoint", "Titanium hardpoint bracket bolted through the backpack to the thorax frame.", zone=ZF)
    C.boolean_cut(hard, C.cutter(P.cyl(56, 80), T(xb, yt, zb - 69)), lip=0.5)                         # cable pass-through
    seats = [frame((xf1, yfc + y, z), (-1, 0, 0), (0, 0, 1)) for y in HP_BOLT_DY for z in HP_BOLT_Z]
    a.take(mech.fasteners("_hpb", seats, "M10", target=hard), "Hardpoint_Bolts",
           "Bolts taking the mount loads through the backpack pad into the thorax frame.", zone=ZF)
    web = P.chamfer_poly([(xf1, 1200), (xf1, zb - 84), (-310, zb - 84), (-310, zb - 98)], [0, 0, 0, 6])
    bm = bmesh.new()
    for y in (yfc - 35, yfc + 35):
        P.merge(bm, P.prism(web, -5, 5), T(0, y, 0) @ R("X", 90))
    gus = a.add("Hardpoint_Gussets", bm, "Gusset webs bracing the hardpoint against the backpack flange.", "ti", None,
                bevel=0.8, zone=ZF)
    C.boolean_cut(gus, C.cutter(P.cyl(34, 200), T(xf1 - 40, yfc, zb - 122) @ R("X", 90)), lip=0.4)

    # ── travel lock on the backpack's top right rear corner ─────────────────
    yl = PR.PACK_BACK_Y + PR.TORSO_Y                               # backpack rear face (world)
    zk = PR.PACK_Z1                                                # backpack top
    xl = -PR.PACK_HALF_W - 1.0                                     # plane of the latch
    padb = P.prism(P.chamfer_poly(P.rrect(42, 40), 5), zk, zk + 6)
    padb.transform(T(-PR.PACK_HALF_W + 26, yl - 54, 0))
    armo = P.chamfer_poly([(yl - 62, zk), (yl - 8, zk), (yl + 2, zk + 8), (yl + 2, zk + 17), (yl - 18, zk + 17),
                           (yl - 30, zk + 6), (yl - 62, zk + 6)], 2)
    armb = P.prism(armo, -11, 11)
    armb.transform(T(xl, 0, 0) @ YZ)
    lb = a.take(_union([armb, padb], None, "ti", 0.7), "Travel_Lock_Base",
                "Base of the travel lock on the backpack, carrying the latch pivot.", zone=ZL)
    C.boolean_cut(lb, C.cutter(P.box(9.2, 40, 40), T(xl, yl - 2, zk + 14)), lip=0.3)                   # latch slot
    hook = P.chamfer_poly([(yl - 14, zk + 5), (yl + 4, zk + 5), (yl + 9, zk + 18), (yl + 13, zk + 20.5), (yl + 13, zk + 30),
                           (yl + 2.5, zk + 30), (yl + 2.5, zk + 23), (yl - 8, zk + 19)], 1.2)
    a.add("Travel_Lock_Latch", P.prism(hook, -4, 4), "Sprung latch that captures the breech when the barrel is vertical.",
          "ti", T(xl, 0, 0) @ YZ, bevel=0.5, seg=1, zone=ZL)
    a.add("Travel_Lock_Pin", P.cyl(5, 26, 12), "Pivot pin of the travel lock latch.", "steel",
          T(xl, yl - 4, zk + 11) @ R("Y", 90), bevel=0, zone=ZL)
    sp = [(2.8, -6)]
    for i in range(6):
        sp += [(5.2, -6 + i * 2), (5.2, -5 + i * 2), (4.2, -4.6 + i * 2), (4.2, -4.2 + i * 2)]
    sp += [(5.2, 6), (2.8, 6)]
    a.add("Travel_Lock_Spring", P.revolve(sp, 16), "Torsion spring holding the travel lock latch closed.", "steel",
          T(xl + 17.6, yl - 4, zk + 11) @ R("Y", 90), bevel=0, zone=ZL)

    # ── energy chain between the backpack and the feed box ──────────────────
    p0 = chain_ends(0.0)[0]
    bm = P.box(4, 30, 44)
    bm.transform(T(-PR.PACK_HALF_W - 2, p0.y, p0.z + 4))
    xs0, xs1 = p0.x - 13.0, -PR.PACK_HALF_W
    P.merge(bm, P.box(xs1 - xs0, 28, 5), T((xs0 + xs1) / 2, p0.y, p0.z - 2.5))
    a.add("Energy_Chain_Anchor", bm, "Bracket anchoring the fixed end of the energy chain to the backpack.", "ti", None,
          bevel=0.6, zone=ZF)
    el("Energy_Chain_Clamp", P.prism(P.rrect(30, 30, 4), 0, 4), "Clamp fixing the moving end of the energy chain to the feed box.",
       "ti", Cn @ T(hw + CHAIN_X_OFF, -45, 30) @ R("X", 90), bevel=0.5)
    _chain(a)
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    tp = tuple(poses.trunnion())
    poses.set_mount("deployed")
    RV.sheet(objs, out / f"15_mount_level_clay{tag}.jpg", "15 mount, level", res=(1000, 900))
    RV.closeup(objs, out / f"15_mount_level_final{tag}.jpg", "15 mount, level, outboard front", (-0.75, -0.6, 0.3), "final",
               isolate=True, dist=3.6)
    RV.closeup(objs, out / f"15_trunnion_clay{tag}.jpg", "15 trunnion and yoke, outboard rear", (-0.8, 0.55, 0.15), "clay",
               isolate=True, target=tp, dist=2.0)
    RV.closeup(objs, out / f"15_inboard_clay{tag}.jpg", "15 mount, inboard: drive, feed box, chain", (0.8, -0.45, 0.25),
               "clay", isolate=True, target=tp, dist=2.0)
    poses.set_mount("stowed")
    RV.closeup(objs, out / f"15_mount_stowed_clay{tag}.jpg", "15 mount, stowed, inboard rear", (0.65, 0.7, 0.2), "clay",
               isolate=True, dist=3.6, res=(1000, 1400))
    RV.closeup(objs, out / f"15_mount_stowed_final{tag}.jpg", "15 mount, stowed, outboard rear", (-0.7, 0.65, 0.25),
               "final", isolate=True, dist=3.6, res=(1000, 1400))
