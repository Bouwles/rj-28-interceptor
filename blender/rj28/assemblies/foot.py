"""Assemblies 13 / 14: foot, left / right.

Large and wide for stability under 185 kg: machined chassis with a heel block
for the two ankle actuators, universal ankle joint with bolted bearing caps
and encoders, armoured upper and ankle guard, hinged toe section, and a sole
in three replaceable pads (heel, arch, toe): lugged rubber bonded to
aluminium carrier plates that screw up into the chassis.

Foot frame (rj28.frames.leg(s)[5]): origin at the ankle centre, level, yawed
by the toe-out; -Y is foot-forward, floor at z = -Z_ANKLE. The ankle cross
sits in a frame rolled by the leg's abduction: its pitch trunnions follow the
shin fork, its roll trunnions the foot.
"""
import bmesh
from mathutils import Matrix, Vector

from .. import frames as FR, params as PR
from ..lib import armour as A, core as C, detail as D, fittings as F, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm, raw

ZF = -PR.Z_ANKLE                 # floor
Y_HEEL = PR.FOOT_L / 3           # rear of the heel
Y_TOE = Y_HEEL - PR.FOOT_L       # tip of the toe
Y_HINGE = Y_TOE + 100.0          # split between the rear foot and the toe section
Y_PIN = Y_HINGE + 4.0            # toe hinge pin, in the middle of the gap between the two chassis
Y_ARCH = 20.0                    # split between the heel pad and the arch pad
RUB, CAR = 9.0, 6.0              # rubber pad and carrier plate thickness
Z_PAD, Z_CAR, Z_DECK = ZF + RUB, ZF + RUB + CAR, ZF + 40.0
CH_X = 34.0                      # screw channels through the rubber, either side of the centre line
YZ = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))    # a prism drawn in (y, z) and extruded along x


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


def _tread(pad, Ft, y0, y1):
    """Cut one rubber pad (spanning y0..y1): two screw channels right through to the carrier, then lugs 6 deep.
    Three passes, each cutter a set of separate bars, each pass a different depth so no two cuts share a face."""
    yc, ln = (y0 + y1) / 2, y1 - y0
    n = int((ln - 20) // 20)
    cut = bmesh.new()
    for o in (1, -1):
        P.merge(cut, P.prism(P.rrect(14, ln - 24, 6.9, 4), -5, RUB + 5), T(o * CH_X, yc, ZF))
    C.boolean_cut(pad, C.cutter(cut, Ft), lip=0.3)
    cut = bmesh.new()
    for k in range(n):                               # across the centre band, ending in the channels
        P.merge(cut, P.box(2 * CH_X - 6, 6, 20), T(0, yc + (k - (n - 1) / 2) * 20, ZF - 4.5))
    for o in (1, -1):                                # along each side band
        P.merge(cut, P.box(6, ln + 40, 20), T(o * 70, yc, ZF - 4.5))
    C.boolean_cut(pad, C.cutter(cut, Ft), lip=0.3)
    cut = bmesh.new()
    for k in range(n + 1):                           # raked across the side bands, half a pitch out of step
        for o in (1, -1):
            P.merge(cut, P.box(110, 6, 20), T(o * (CH_X + 3), yc + (k - n / 2) * 20, ZF - 3.5) @ R("Z", o * 18) @ T(o * 52, 0, 0))
    C.boolean_cut(pad, C.cutter(cut, Ft), lip=0.3)
    m = int((ln - 24) // 40) + 1                     # carrier screws down each channel at 40 mm pitch
    return [(o * CH_X, yc + (k - (m - 1) / 2) * 40) for k in range(m) for o in (1, -1)]


def _cap_shell(secs, t):
    """Shell skinned over sections and closed across the last one: a cap with an open, thick lower rim."""
    bm = P.loft(secs, cap=False)
    n = len(secs[0])
    bm.faces.new(list(bm.verts)[-n:])
    return P.thicken(bm, t)


def build(s):
    a = Asm("13" if s > 0 else "14")
    Ft = FR.leg(s)[5]
    Cx = Ft @ R("Y", -s * PR.LEG_ABDUCT)             # ankle cross: X along the shin fork's bores, Y along the foot
    w = PR.FOOT_W
    fwd, up = (Ft.to_3x3() @ Vector((0, -1, 0))).normalized(), Vector((0, 0, 1))
    full = outline()
    rear = _clip(full, y_min=Y_HINGE + 3.0)              # heel and mid-foot
    toe = _clip(full, y_max=Y_HINGE - 3.0)               # hinged toe

    # ── ankle: universal joint between the shin fork and the foot yoke ──────
    cross = P.prism(P.chamfer_poly(P.rrect(58, 58), 9), -21, 21)
    P.merge(cross, P.cyl(30, 156, 32), R("Y", 90))                                 # pitch trunnions into the shin fork
    P.merge(cross, P.cyl(40, 68, 32), R("Y", 90))                                  # their thrust shoulders
    P.merge(cross, P.cyl(26, 104, 32), R("X", 90))                                 # roll trunnions into the foot yoke
    P.merge(cross, P.cyl(36, 68, 32), R("X", 90))
    a.add("Ankle_Cross", cross, "Cross of the ankle universal joint: pitch in the shin fork, roll in the foot yoke.", "ti",
          Cx, bevel=0.8)
    prof, rbc, zl = D.bolted_cover_profile(34, 4, 0, 11, 3)
    caps, seats = bmesh.new(), []
    for o in (1, -1):
        m = T(o * 79, 0, 0) @ R("Y", o * 90)
        P.merge(caps, P.revolve(prof, 48), m)
        seats += [Cx @ m @ k for k in mech.ring((0, 0, zl), (0, 0, 1), rbc, 6)]
    a.add("Ankle_Pitch_Caps", caps, "Bolted caps retaining the ankle pitch bearings in the shin fork.", "alu", Cx, bevel=0.4,
          seg=1)
    a.take(mech.fasteners("_pc", seats, "M4"), "Ankle_Pitch_Cap_Screws", "Screws clamping the ankle pitch bearing caps.")
    a.add("Ankle_Pitch_Encoder", D.encoder_bm(36), "Absolute encoder reading ankle pitch on the outer bearing cap.",
          ["alu", "fastener"], Cx @ T(s * 86, 0, 0) @ R("Y", s * 90) @ R("Z", 90), bevel=0.4)     # gland to the rear

    # ── chassis: sole plate, ankle yoke, heel block for the two ankle actuators ──
    # joined by real unions: bodies that only overlap in one mesh get lost by the second cut made after them
    bodies = [P.prism([(x * 0.93, y * 0.96 + 1) for x, y in rear], Z_CAR, Z_DECK),                              # sole plate
              P.loft([A.csec(ZF + 38, 104, 120, 0, 0, 0.16), A.csec(-44, 84, 108, 0, 0, 0.16)]),                # yoke pedestal
              P.loft([A.csec(Z_CAR + 0.5, 124, 50, 0, 84, 0.12), A.csec(ZF + 34, 138, 57, 0, 91, 0.12),
                      A.csec(ZF + 57, 136, 49, 0, 99, 0.1)])]                                                # heel block
    for o in (1, -1):
        ear = P.lug(27, 13.2, 48, 12, 32)                                                                # roll yoke ears
        ear.transform(frame((0, o * 46, 0), (0, 1, 0), (0, 0, 1)))
        bodies.append(ear)
    fr = raw(bodies[0], None, "alu", 0.8, 2)
    for b in bodies[1:]:
        C.boolean_join(fr, C.cutter(b), lip=1.0)
    m = Ft.copy()
    m.translation = m.translation * C.MM
    fr.data.transform(m)
    fr.data.update()
    a.take(fr, "Foot_Frame", "Machined foot chassis: sole plate, ankle yoke and the heel block that takes the ankle actuators.")
    for o in (1, -1):
        D.pocket_grid(fr, Ft @ T(o * 66, -60, Z_DECK), 1, 2, 24, 40, 0, 52, depth=7)
        D.pocket_grid(fr, Ft @ T(o * 68.8, 99, ZF + 47.5) @ R("Y", o * 90), 1, 1, 9, 26, 0, 0, depth=5)
    D.pocket_grid(fr, Ft @ T(0, 104, ZF + 57), 1, 1, 30, 18, 0, 0, depth=8)                      # between the two fork pads
    D.pocket_grid(fr, Ft @ T(0, 122.2, ZF + 46.5) @ R("X", -90), 1, 1, 72, 10, 0, 0, depth=4)    # relief across the rear face
    prof, rbc, zl = D.bolted_cover_profile(24, 4, 0, 9, 3)
    caps, seats = bmesh.new(), []
    for o in (1, -1):
        m = T(0, o * 52, 0) @ R("X", -o * 90)
        P.merge(caps, P.revolve(prof, 40), m)
        seats += [Ft @ m @ k for k in mech.ring((0, 0, zl), (0, 0, 1), rbc, 4, phase=45)]
    a.add("Ankle_Roll_Caps", caps, "Bolted caps retaining the ankle roll bearings in the foot yoke.", "alu", Ft, bevel=0.4,
          seg=1)
    a.take(mech.fasteners("_rc", seats, "M4"), "Ankle_Roll_Cap_Screws", "Screws clamping the ankle roll bearing caps.")
    a.add("Ankle_Roll_Encoder", D.encoder_bm(26), "Absolute encoder reading ankle roll on the rear bearing cap.",
          ["alu", "fastener"], Ft @ T(0, 59, 0) @ R("X", -90) @ R("Z", 90 + 90 * s), bevel=0.4)   # gland to the inner side
    a.add("Heel_Bumper", P.prism(P.rrect(84, 14, 3), -0.5, 5.0), "Rubber strike pad bonded under the overhang of the heel block.",
          "rubber", Ft @ T(0, 114.25, ZF + 24.5) @ R("X", -118.9), bevel=1.0)

    # ── sole: carrier plates screwed up into the chassis, lugged rubber pads bonded to them ──
    car = a.add("Sole_Carrier", P.prism(rear, Z_PAD, Z_CAR), "Carrier plate of the heel and arch pads, screwed up into the foot chassis.",
                "alu", Ft, bevel=0.5)
    heel = a.add("Heel_Pad", P.prism(_clip(full, y_min=Y_ARCH + 3.0), ZF, Z_PAD),
                 "Replaceable lugged rubber pad under the heel, bonded to the sole carrier.", "rubber", Ft, bevel=1.0)
    arch = a.add("Arch_Pad", P.prism(_clip(full, y_min=Y_HINGE + 3.0, y_max=Y_ARCH - 3.0), ZF, Z_PAD),
                 "Replaceable lugged rubber pad under the arch and ball of the foot, bonded to the sole carrier.", "rubber", Ft,
                 bevel=1.0)
    pts = _tread(heel, Ft, Y_ARCH + 3.0, Y_HEEL) + _tread(arch, Ft, Y_HINGE + 3.0, Y_ARCH - 3.0)
    seats = [frame((x, y, Z_PAD), (0, 0, -1), (1, 0, 0)) for x, y in pts]
    a.take(mech.fasteners("_sc", seats, "M6", "csk", target=car, matrix=Ft), "Sole_Carrier_Screws",
           "Countersunk screws in the pad channels fixing the sole carrier to the foot chassis.")

    # ── hinged toe ──────────────────────────────────────────────────────────
    a.add("Toe_Frame", P.prism([(x * 0.93, y * 0.95 - 4) for x, y in toe], Z_CAR, Z_DECK),
          "Toe chassis, hinged to the foot frame so the foot can roll off the ground.", "alu", Ft, bevel=0.8)
    tcar = a.add("Toe_Carrier", P.prism(toe, Z_PAD, Z_CAR), "Carrier plate of the toe pad, screwed up into the toe chassis.",
                 "alu", Ft, bevel=0.5)
    tpad = a.add("Toe_Pad", P.prism(toe, ZF, Z_PAD), "Replaceable lugged rubber pad under the toe section, bonded to the toe carrier.",
                 "rubber", Ft, bevel=1.0)
    seats = [frame((x, y, Z_PAD), (0, 0, -1), (1, 0, 0)) for x, y in _tread(tpad, Ft, Y_TOE, Y_HINGE - 3.0)]
    a.take(mech.fasteners("_tc", seats, "M6", "csk", target=tcar, matrix=Ft), "Toe_Carrier_Screws",
           "Countersunk screws in the pad channels fixing the toe carrier to the toe chassis.")
    a.add("Toe_Hinge", F.hinge_bm(8.0, w - 34, 7, leaf=12.0), "Hinge between the foot frame and the toe section, its leaves let into both decks.",
          ["alu", "steel"], Ft @ T(0, Y_PIN, Z_DECK + 8.0) @ R("Z", 90), bevel=0)
    tsec = [(Z_DECK, w - 12, 79, 0, Y_TOE + 46.5, 26), (ZF + 58, w - 24, 70, 0, Y_TOE + 49, 24), (ZF + 74, w - 48, 50, 0, Y_TOE + 55, 18)]
    ts = raw(_cap_shell([A.rsec(*t) for t in tsec], 8.0), Ft, "armour", 1.2, 3)
    a.take(ts, "Toe_Armour", "Armoured cap over the toe section: an 8 mm shell standing on the toe deck.")
    posts = bmesh.new()
    tpts = [(x, y) for x in (-44, 44) for y in (Y_TOE + 68, Y_TOE + 42)]
    for x, y in tpts:
        P.merge(posts, P.cyl(14, 26.4, 16), T(x, y, ZF + 53))
    a.add("Toe_Armour_Posts", posts, "Posts standing on the toe deck that the toe armour screws down onto.", "alu", Ft, bevel=0.4,
          seg=1)
    a.take(mech.fasteners("_ta", D.seats_on(ts, [Ft @ Vector((x, y, 60)) for x, y in tpts], up), "M6", target=ts),
           "Toe_Armour_Screws", "Screws fixing the toe armour to its posts.")
    F.panel_cut(ts, [Ft @ Vector((x, Y_TOE + 53, ZF + 100)) for x in range(-48, 49, 8)], 1.5, 2.0)
    osec = [(ZF + 17, w, 91, 0, Y_TOE + 46.5, 32), (Z_DECK, w, 91, 0, Y_TOE + 46.5, 32), (ZF + 58, w - 12, 82, 0, Y_TOE + 49, 30)]
    sp = raw(A.shell([A.rsec(*t) for t in osec], 6.0), Ft, "armour", 1.2, 3)
    C.boolean_intersect(sp, C.cutter(P.box(140, 64, 200), Ft @ T(0, Y_TOE + 24 - 32, ZF + 40)), lip=0.6)
    a.take(sp, "Toe_Strike_Plate", "Second armour layer wrapped round the front of the toe, down over the edge of the toe chassis.")
    pts = [Ft @ Vector((x, Y_TOE - 80, ZF + 28)) for x in (-48, -16, 16, 48)]
    a.take(mech.fasteners("_tk", D.seats_on(sp, pts, fwd), "M4", target=sp), "Toe_Strike_Plate_Screws",
           "Screws fixing the toe strike plate to the front of the toe chassis.")

    # ── armoured upper and ankle guard ──────────────────────────────────────
    secs = [A.rsec(Z_DECK, w - 8, 192, 0, -7, 34), A.rsec(-30, w - 18, 182, 0, -8, 34), A.rsec(-12, w - 28, 172, 0, -6, 32)]

    def open_upper(ob, lip=0.6):
        C.boolean_cut(ob, C.cutter(P.box(400, 300, 300), Ft @ T(0, 62 + 150, 0)), lip=lip)       # open at the rear
        C.boolean_cut(ob, C.cutter(P.cyl(92, 400, 48), Cx @ R("Y", 90)), lip=lip)                # clear the pitch bearing caps

    lower = raw(A.shell(secs, 9.0), Ft, "armour", 1.2, 3)
    open_upper(lower)
    a.take(lower, "Foot_Armour", "Armoured upper over the instep and the sides of the foot.")
    F.panel_cut(lower, [Ft @ Vector((x, -120, -34 + abs(x) * 0.05)) for x in range(-60, 61, 10)], 1.5, 2.0)
    # the guard is a front shield narrow enough to swing between the cheeks of the shin fork
    g_secs = [A.rsec(-34, 112, 100, 0, -34, 26), A.rsec(4, 108, 100, 0, -24.8, 26), A.rsec(40, 102, 100, 0, -16, 24)]
    guard = raw(A.shell(g_secs, 9.0), Ft, "armour", 1.2, 3)
    C.boolean_cut(guard, C.cutter(P.box(400, 300, 300), Ft @ T(0, -48 + 150, 0)), lip=0.6)       # front shield only
    a.take(guard, "Ankle_Guard", "Armour shield over the front of the ankle joint, fixed to the foot.")
    gb = bmesh.new()
    for o in (1, -1):
        br = P.prism([(-75.2, Z_DECK), (-61, Z_DECK), (-61, 0), (-66.9, 0), (-75.2, -34)], 34, 46)
        P.merge(gb, br, T(-80 if o < 0 else 0, 0, 0) @ YZ)
    a.add("Ankle_Guard_Brackets", gb, "Brackets standing on the foot deck that carry the ankle guard.", "alu", Ft, bevel=0.6,
          seg=1)
    pts = [Ft @ Vector((x, -200, -9)) for x in (-40, 40)]
    a.take(mech.fasteners("_ag", D.seats_on(guard, pts, fwd), "M6", target=guard), "Ankle_Guard_Screws",
           "Screws fixing the ankle guard to its brackets.")
    car = a.add("Foot_Armour_Carrier", A.hoops(secs, (-48,), band=16.0, inset=9.6),
                "Carbon rib bonded inside the foot armour, carrying it off the frame.", "cfrp", Ft, bevel=0.3, seg=1)
    open_upper(car, lip=None)
    pts = [Ft @ Vector((x, -200, z)) for x, z in ((-54, -46), (54, -46), (-44, -22), (44, -22))]
    a.take(mech.fasteners("_fa", D.seats_on(lower, pts, fwd), "M6", target=lower), "Foot_Armour_Screws",
           "Screws fixing the foot armour to its carrier.")
    for o, tag in ((s, "Outer"), (-s, "Inner")):
        side = (Ft.to_3x3() @ Vector((o, 0, 0))).normalized()
        pts = [Ft @ Vector((o * 160, y, -40)) for y in (-76, 44)]
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
