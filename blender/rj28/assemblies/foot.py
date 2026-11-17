"""Assemblies 13 / 14: foot, left / right.

Large and wide for stability under 185 kg: machined frame, universal ankle
joint, armoured upper and ankle guard, hinged toe section, heel block, and a
replaceable rubber sole with straight sipes.

Foot frame (rj28.frames.leg(s)[5]): origin at the ankle centre, level, yawed
by the toe-out; -Y is foot-forward, floor at z = -Z_ANKLE.
"""
import bmesh
from mathutils import Vector

from .. import frames as FR, params as PR
from ..lib import armour as A, core as C, detail as D, fittings as F, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm, raw

ZF = -PR.Z_ANKLE                 # floor
Y_HEEL = PR.FOOT_L / 3           # rear of the heel
Y_TOE = Y_HEEL - PR.FOOT_L       # tip of the toe
Y_HINGE = Y_TOE + 100.0          # toe hinge line


def outline():
    hw = PR.FOOT_W / 2
    return P.round_poly([(-hw * 0.78, Y_HEEL), (-hw * 0.97, -30), (-hw, -150), (-hw * 0.8, Y_TOE), (hw * 0.8, Y_TOE),
                         (hw, -150), (hw * 0.97, -30), (hw * 0.78, Y_HEEL)], [34, 80, 80, 44, 44, 80, 80, 34], 6)


def _clip(pts, y_min=None, y_max=None):
    """Keep the part of a convex-ish outline between two Y limits (adds the cut edge)."""
    out = []
    n = len(pts)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        inside_p = (y_min is None or p[1] >= y_min) and (y_max is None or p[1] <= y_max)
        inside_q = (y_min is None or q[1] >= y_min) and (y_max is None or q[1] <= y_max)
        if inside_p:
            out.append(p)
        if inside_p != inside_q:
            lim = y_min if (y_min is not None and (p[1] < y_min or q[1] < y_min)) else y_max
            t = (lim - p[1]) / (q[1] - p[1])
            out.append((p[0] + (q[0] - p[0]) * t, lim))
    return out


def build(s):
    a = Asm("13" if s > 0 else "14")
    Ft = FR.leg(s)[5]
    w = PR.FOOT_W
    full = outline()
    rear = _clip(full, y_min=Y_HINGE + 3.0)              # heel and mid-foot
    toe = _clip(full, y_max=Y_HINGE - 3.0)               # hinged toe

    # ── ankle: universal joint between the shin fork and the foot yoke ──────
    cross = P.box(58, 58, 42)
    P.merge(cross, P.cyl(30, 162, 32), R("Y", 90))                                 # pitch trunnions into the shin fork
    P.merge(cross, P.cyl(26, 118, 32), R("X", 90))                                 # roll trunnions into the foot yoke
    a.add("Ankle_Cross", cross, "Cross of the ankle universal joint: pitch in the shin fork, roll in the foot yoke.", "ti",
          Ft, bevel=0.8)
    caps = bmesh.new()
    for o in (1, -1):
        P.merge(caps, P.revolve([(0, 0), (22, 0), (22, 4), (19, 7), (0, 7)], 32), T(o * 80, 0, 0) @ R("Y", o * 90))
    a.add("Ankle_Pitch_Caps", caps, "Caps retaining the ankle pitch bearings in the shin fork.", "alu", Ft, bevel=0.4, seg=1)

    # ── frame: sole plate, ankle yoke, heel bridge for the two ankle actuators ──
    bm = P.prism([(x * 0.93, y * 0.96 + 1) for x, y in rear], ZF + 22, ZF + 40)
    for o in (1, -1):
        P.merge(bm, P.lug(27, 13.2, 46, 12, 32), frame((0, o * 46, 0), (0, 1, 0), (0, 0, 1)))    # roll yoke ears
    P.merge(bm, P.loft([A.csec(ZF + 38, 104, 120, 0, 0, 0.16), A.csec(-44, 84, 108, 0, 0, 0.16)]))   # yoke pedestal
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(132, 38), 8), ZF + 38, -38), T(0, 104, 0))            # heel bridge
    fr = a.add("Foot_Frame", bm, "Machined foot chassis: sole plate, ankle yoke and the bridge that takes the ankle actuators.",
               "alu", Ft, bevel=0.8)
    for o in (1, -1):
        D.pocket_grid(fr, Ft @ T(o * 62, -34, ZF + 40) , 1, 3, 30, 44, 0, 56, depth=7)
    a.add("Heel_Bumper", P.prism(P.rrect(118, 22, 8), ZF + 24, ZF + 54), "Rubber bumper protecting the heel bridge.",
          "rubber", Ft @ T(0, Y_HEEL - 6, 0), bevel=1.0)

    # ── sole: replaceable rubber with straight sipes ────────────────────────
    sole = a.add("Sole", P.prism(rear, ZF, ZF + 22), "Replaceable rubber sole with straight sipes.", "rubber", Ft, bevel=1.5)
    n = int((Y_HEEL - Y_HINGE - 30) // 22)
    A.slots(sole, Ft @ T(0, (Y_HEEL + Y_HINGE) / 2, ZF) @ R("X", 180), n, w + 40, 3.0, 22.0, depth=4.0, lip=0.2)
    tsole = a.add("Toe_Sole", P.prism(toe, ZF, ZF + 22), "Rubber sole of the hinged toe section.", "rubber", Ft, bevel=1.5)
    A.slots(tsole, Ft @ T(0, (Y_TOE + Y_HINGE) / 2 - 4, ZF) @ R("X", 180), 3, w + 40, 3.0, 22.0, depth=4.0, lip=0.2)

    # ── hinged toe ──────────────────────────────────────────────────────────
    a.add("Toe_Frame", P.prism([(x * 0.93, y * 0.95 - 4) for x, y in toe], ZF + 22, ZF + 38),
          "Toe chassis, hinged to the foot frame so the foot can roll off the ground.", "alu", Ft, bevel=0.8)
    a.add("Toe_Hinge", F.hinge_bm(8.0, w - 34, 7), "Hinge between the foot frame and the toe section.", ["alu", "steel"],
          Ft @ T(0, Y_HINGE, ZF + 46) @ R("Z", 90), bevel=0)
    ts = raw(A.solid([A.rsec(ZF + 38, w - 12, 92, 0, Y_TOE + 52, 26), A.rsec(ZF + 62, w - 30, 76, 0, Y_TOE + 58, 24),
                      A.rsec(ZF + 76, w - 52, 56, 0, Y_TOE + 64, 20)]), Ft, "armour", 1.2, 3)
    a.take(ts, "Toe_Armour", "Armoured cap over the toe section.")
    F.panel_cut(ts, [Ft @ Vector((x, Y_TOE + 50, ZF + 100)) for x in range(-60, 61, 10)], 1.5, 2.0)

    # ── armoured upper and ankle guard ──────────────────────────────────────
    secs = [A.rsec(ZF + 40, w - 8, 214, 0, -18, 34), A.rsec(-30, w - 18, 194, 0, -12, 34), A.rsec(-12, w - 28, 172, 0, -6, 32)]

    def open_upper(ob, lip=0.6):
        C.boolean_cut(ob, C.cutter(P.box(400, 300, 300), Ft @ T(0, 62 + 150, 0)), lip=lip)       # open at the rear
        C.boolean_cut(ob, C.cutter(P.cyl(92, 400, 48), Ft @ R("Y", 90)), lip=lip)                # clear the pitch trunnions

    lower = raw(A.shell(secs, 9.0), Ft, "armour", 1.2, 3)
    open_upper(lower)
    a.take(lower, "Foot_Armour", "Armoured upper over the instep and the sides of the foot.")
    F.panel_cut(lower, [Ft @ Vector((x, -140, -50 + abs(x) * 0.05)) for x in range(-70, 71, 10)], 1.5, 2.0)
    g_secs = [A.rsec(-20, w - 36, 158, 0, -8, 32), A.rsec(10, w - 46, 142, 0, -6, 30), A.rsec(42, w - 58, 124, 0, -5, 28)]
    guard = raw(A.shell(g_secs, 9.0), Ft, "armour", 1.2, 3)
    C.boolean_cut(guard, C.cutter(P.box(400, 300, 300), Ft @ T(0, -4 + 150, 0)), lip=0.6)        # front shield only
    C.boolean_cut(guard, C.cutter(P.cyl(96, 400, 48), Ft @ R("Y", 90)), lip=0.6)
    a.take(guard, "Ankle_Guard", "Armour shield over the front of the ankle joint, fixed to the foot.")
    gb = bmesh.new()
    for o in (1, -1):
        P.merge(gb, P.box(10, 44, 40), T(o * 50, -44, -24))
    a.add("Ankle_Guard_Brackets", gb, "Brackets standing the ankle guard off the foot frame.", "alu", Ft, bevel=0.6, seg=1)
    car = a.add("Foot_Armour_Carrier", A.hoops(secs, (-48,), band=16.0, inset=9.6),
                "Carbon rib bonded inside the foot armour, carrying it off the frame.", "cfrp", Ft, bevel=0.3, seg=1)
    open_upper(car, lip=None)
    fwd = (Ft.to_3x3() @ Vector((0, -1, 0))).normalized()
    pts = [Ft @ Vector((x, -200, z)) for x, z in ((-54, -62), (54, -62), (-46, -38), (46, -38))]
    a.take(mech.fasteners("_fa", D.seats_on(lower, pts, fwd), "M6", target=lower), "Foot_Armour_Screws",
           "Screws fixing the foot armour to its carrier.")
    for o, tag in ((s, "Outer"), (-s, "Inner")):
        side = (Ft.to_3x3() @ Vector((o, 0, 0))).normalized()
        pts = [Ft @ Vector((o * 160, y, -40)) for y in (-76, -16, 40)]
        a.take(mech.fasteners("_fs", D.seats_on(lower, pts, side), "M6", target=lower), f"Foot_Side_Screws_{tag}",
               f"Screws along the {tag.lower()} edge of the foot armour.")
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    s = 1 if a.aa == "13" else -1
    for name, d, mode in (("front", (s * 0.7, -1.0, 0.45), "clay"), ("rear", (s * 0.6, 1.0, 0.5), "clay"),
                          ("under", (s * 0.4, -0.6, -1.0), "clay"), ("front_final", (s * 0.7, -1.0, 0.4), "final")):
        RV.closeup(objs, out / f"{a.aa}_foot_{name}{tag}.jpg", f"{a.aa} foot, {name}", d, mode, isolate=True, dist=4.4,
                   res=(1300, 1000))
