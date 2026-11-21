"""Assemblies 11 / 12: leg, left / right.

Hip pitch actuator, thigh frame and armour, knee crank joint with its two
linear actuators, shin member and armour, ankle actuators. The ankle joint
itself and everything below it belong to the foot (13 / 14).

Frames (rj28.frames.leg): thigh and shin frames have +X along the joint axes,
+Y to the rear and -Z running down the limb. "Outer" is s * X.

Knee kinematics. The thigh ends in a fork: two long cheeks either side of an
open corridor. The shin's tang sits in the middle of the fork on the knee
shaft, and carries a crank pin KNEE_CRANK from the axis on each side. The two
actuators run down the corridor from the top of the thigh to those pins. With
the leg straight the pin sits half the knee's range (plus KNEE_PHASE, because
the actuator leans back) below "straight back". The lever arm then peaks at
the crank radius in mid-range and is the same at both ends of travel, about
57% of the crank radius, so the rod always passes the slim knee shaft.
measure.py prints the lever arm across the range from these pivots.

Rear guards. Seen from the side the knee actuators pivot on KNEE_P0 and lean
between 8.1 and 12.9 degrees off the thigh axis across the 110 degree range.
The hamstring guard is a channel parallel to the rear-most of those lines,
its inner wall 17 mm behind the actuator bodies at the closest angle. Seen
from the shin, the same actuators fold down across the back of the calf to 39
degrees below horizontal at full flexion, and the hamstring guard comes down
with them: the calf guard therefore starts low and its top edge is raked
parallel to the folded thigh (14 mm from the hamstring guard, 50 mm from the
actuators at 110 degrees). HAM_* and CALF_* below are those numbers.
"""
import math

import bmesh
from mathutils import Matrix, Vector

from .. import frames as FR, params as PR
from ..lib import armour as A, core as C, detail as D, fittings as F, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import ACTUATOR_FN, Asm, raw

ACT_X = 42.0                                         # knee actuators sit this far either side of the leg centre
_H = math.radians(PR.KNEE_RANGE / 2)
_A = math.radians(PR.KNEE_RANGE / 2 + PR.KNEE_PHASE)
KNEE_P0 = (ACT_X, 120.0, -62.0)                      # body-end pivot, thigh frame
KNEE_P1 = (ACT_X, PR.KNEE_CRANK * math.cos(_A), -PR.KNEE_CRANK * math.sin(_A))   # crank pin, shin frame
KNEE_STROKE = 2 * PR.KNEE_CRANK * math.sin(_H)
CHEEK_X = 74.0                                       # knee fork cheeks (14 thick) centred here
ANKLE_P0 = (40.0, 86.0, -150.0)                      # shin frame
ANKLE_P1 = (40.0, 104.0, -6.0)                       # foot frame

HAM_Z = (-100.0, -228.0)                             # hamstring guard: top and bottom edge, thigh frame
HAM_Y, HAM_LEAN = 149.8, 0.1421                      # outer face of its rear wall at the bottom edge; dy/dz of that wall
HAM_RET = 64.0                                       # depth of its side returns
CALF_Y, CALF_FRONT = 139.0, 98.0                     # calf guard: outer face of the rear wall, front edge of the returns
CALF_TOP, CALF_BOT, CALF_RAKE = -230.0, -356.0, 0.545    # top edge at the rear wall, bottom edge, rise of the top edge per mm forward
YZ = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))    # a prism drawn in (y, z) and extruded along x


def _dir(m, v):
    return (m.to_3x3() @ Vector(v)).normalized()


def _local(m, ob):
    lo, hi = C.bounds_mm([ob])
    return m.inverted() @ ((lo + hi) / 2)


def _bar(p0, p1, axis, r, t):
    """Solid flat link between two pivot points (world, mm): round ends, thickness t along the pivot axis."""
    p0, p1 = Vector(p0), Vector(p1)
    x = p1 - p0
    ln = x.length
    x.normalize()
    z = (Vector(axis) - x * x.dot(Vector(axis))).normalized()
    m = Matrix((x, z.cross(x), z)).transposed().to_4x4()
    m.translation = p0
    n = 10
    pts = [(r * math.cos(math.radians(90 + 180 * k / n)), r * math.sin(math.radians(90 + 180 * k / n))) for k in range(n + 1)]
    pts += [(ln + r * math.cos(math.radians(-90 + 180 * k / n)), r * math.sin(math.radians(-90 + 180 * k / n)))
            for k in range(n + 1)]
    bm = P.prism(pts, -t / 2, t / 2)
    bm.transform(m)
    return bm


def _weld(bodies, matrix, mat="alu", bevel=1.0):
    """One machined part from overlapping bodies (bmeshes in the limb frame), joined by real unions and then
    placed. Bodies that merely share a mesh do not survive two cuts in a row: the second boolean drops
    whichever of them the first one touched, which is how the hip hanger went missing."""
    ob = raw(bodies[0], None, mat, bevel, 2)
    for b in bodies[1:]:
        C.boolean_join(ob, C.cutter(b), lip=1.0)
    m = matrix.copy()
    m.translation = m.translation * C.MM
    ob.data.transform(m)
    ob.data.update()
    return ob


def _at(bm, m):
    bm.transform(m)
    return bm


def _overlay(secs, t):
    """Sections of a second armour layer lying on a shell built from `secs` (tuples for A.rsec)."""
    return [A.rsec(z, w + 2 * t, d + 2 * t, dx, dy, r + t) for z, w, d, dx, dy, r in secs]


def build(s):
    a = Asm("11" if s > 0 else "12")
    Lg, Th, Kn, Sh, An, Ft = FR.leg(s)
    xk = _dir(Th, (1, 0, 0))                         # pitch axis of hip, knee and ankle
    fwd_t, fwd_s = _dir(Th, (0, -1, 0)), _dir(Sh, (0, -1, 0))
    zk = -PR.THIGH                                   # knee axis height in the thigh frame

    # ── hip pitch actuator: its housing is the top of the thigh ─────────────
    # connector at the rear, 25 degrees above horizontal: the only arc of the housing that neither the
    # pelvis saddle nor the knee actuators' upper eyes ever cross
    d = mech.rotary_actuator("_hip", 174, 150, Lg @ T(-s * 67, 0, 0) @ R("Y", s * 90), bolts=0,
                             connector_angle=90 + 25 * s)
    a.take_rotary(d, "Hip_Pitch", "hip pitch")

    # ── thigh frame: hangers on the actuator, beam, crosshead, knee fork ────
    bodies = [P.loft([A.csec(-150, 98, 84, 0, 30, 0.14), A.csec(-206, 92, 78, 0, 14, 0.14)]),                    # beam
              _at(P.prism(P.chamfer_poly(P.rrect(182, 124), 14), -152, -112), T(s * 5, 14, 0)),               # top crosshead
              _at(P.lug(78, 30, 150, 10, 40), frame((s * 91, 0, 0), (1, 0, 0), (0, 0, 1))),                   # on the output flange, inside the armour
              _at(P.lug(64, 36, 150, 12, 40), frame((-s * 74, 0, 0), (1, 0, 0), (0, 0, 1))),                  # idler side
              _at(P.prism(P.chamfer_poly(P.rrect(132, 46), 8), -126, -82), T(0, 96, 0)),                      # knee actuator anchor
              _at(P.prism(P.chamfer_poly(P.rrect(2 * CHEEK_X + 14, 84), 10), -204, -164), T(0, 8, 0))]        # fork crosshead
    for o in (1, -1):
        bodies.append(_at(P.lug(60, 31, -zk - 150, 14, 40), frame((o * CHEEK_X, 0, zk), (1, 0, 0), (0, 0, -1))))   # fork cheeks
        bodies.append(_at(P.box(12, 18, 22), T(o * 61, -50, zk + 60)))                                 # knee guard link pivots
    tf = a.take(_weld(bodies, Th), "Thigh_Frame", "Machined thigh member: hangs from the hip pitch output and ends in the knee fork.")
    D.pocket_grid(tf, Th @ T(0, 54.5, -178) @ R("X", -90), 1, 1, 56, 30, 0, 0, depth=8)
    D.pocket_grid(tf, Th @ T(s * 96.2, 0, -90) @ R("Y", s * 90), 1, 1, 22, 96, 0, 0, depth=6)
    for o in (1, -1):
        D.pocket_grid(tf, Th @ T(o * (CHEEK_X + 7.2), 0, -272) @ R("Y", o * 90), 2, 1, 58, 62, 72, 0, depth=5)
    seats = mech.ring((s * 96, 0, 0), (s, 0, 0), 52, 12, x_hint=(0, 0, 1))
    a.take(mech.fasteners("_hb", seats, "M6", target=tf, matrix=Th), "Hip_Hanger_Bolts",
           "Screws clamping the thigh hanger to the hip pitch output flange.")

    # hip ends: a ribbed cap over the output-side hanger bore, a plain stub axle for the idler hanger
    Mo = Lg @ T(s * 96, 0, 0) @ R("Y", s * 90)
    cap = P.revolve([(0, 0), (41, 0), (41, 2.5), (39.5, 4), (28, 4), (24, 9), (10, 9), (10, 13), (0, 13)], 48)
    for k in range(6):
        rib = P.prism([(8, 6), (38, 2), (38, 6.5), (25, 12.5), (8, 12.5)], -2.5, 2.5)
        P.merge(cap, rib, R("Z", 60 * k) @ R("X", 90))
    a.add("Hip_Hub_Cap", cap, "Ribbed cap closing the hanger bore over the hip pitch output flange.", "alu", Mo, bevel=0.5,
          seg=1)
    a.take(mech.fasteners("_hc", mech.ring((0, 0, 4), (0, 0, 1), 34.5, 6, phase=30), "M4", matrix=Mo),
           "Hip_Hub_Cap_Screws", "Screws holding the hip hub cap to the thigh hanger.")
    Mi = Lg @ T(-s * 67, 0, 0) @ R("Y", -s * 90)
    tr = a.add("Hip_Idler_Trunnion",
               P.revolve([(0, 0), (35.5, 0), (35.5, 13), (47, 13), (47, 17), (45, 19), (15, 19), (13, 21.5), (0, 21.5)], 64),
               "Stub axle on the back of the hip pitch housing that carries the idler hanger.", "ti", Mi, bevel=0.5)
    a.take(mech.fasteners("_hi", mech.ring((0, 0, 19), (0, 0, 1), 26, 8), "M6", target=tr, matrix=Mi),
           "Hip_Idler_Trunnion_Screws", "Screws fixing the idler trunnion to the hip pitch housing.")

    # ── thigh armour: one shell, opened at the rear and inner side, split in two ──
    tsec = [(-80, 178, 192, 18 * s, -14, 36), (-130, 206, 204, 4 * s, -18, 44), (-200, 212, 206, 4 * s, -18, 46),
            (-300, 198, 190, 0, -14, 42), (-372, 190, 172, 0, -8, 38)]
    secs = [A.rsec(*t) for t in tsec]

    def open_thigh(ob, lip=0.6):
        """The armour (and its carrier) cover the front and outer side only."""
        C.boolean_cut(ob, C.cutter(P.box(500, 300, 700), Th @ T(0, 36 + 150, -220)), lip=lip)
        C.boolean_cut(ob, C.cutter(P.box(200, 260, 700), Th @ T(-s * 172, 70, -220)), lip=lip)
        C.boolean_cut(ob, C.cutter(P.cyl(198, 500, 64), Th @ R("Y", 90)), lip=lip)
        C.boolean_cut(ob, C.cutter(P.cyl(182, 500, 64), Kn @ R("Y", 90)), lip=lip)

    sh = raw(A.shell(secs, 10.0), Th, "armour", 1.2, 3)
    open_thigh(sh)
    A.gap_cut(sh, Th @ Vector((0, 0, -226)), _dir(Th, (0.0, 0.42, 1.0)))
    pieces = sorted(A.islands(sh), key=lambda o: -len(o.data.vertices))[:2]
    lower, upper = sorted(pieces, key=lambda o: _local(Th, o).z)
    a.take(upper, "Thigh_Armour_Upper", "Upper thigh armour panel covering the front and outer side of the thigh.")
    a.take(lower, "Thigh_Armour_Lower", "Lower thigh armour panel, lapping over the knee joint.")
    car = a.add("Thigh_Armour_Carrier", A.hoops(secs, (-168, -300), band=18.0),
                "Carbon ribs bonded inside the thigh armour, carrying it off the frame.", "cfrp", Th, bevel=0.3, seg=1)
    open_thigh(car, lip=None)
    posts = bmesh.new()
    for x in (-30, 30):
        P.merge(posts, P.cyl(14, 77, 16), T(x, -68.5, -168) @ R("X", 90))
        P.merge(posts, P.cyl(14, 44, 16), T(x * 2.2, -82, -300) @ R("X", 90))
    a.add("Thigh_Carrier_Standoffs", posts, "Standoff posts fixing the thigh armour carrier to the thigh frame.", "alu",
          Th, bevel=0.4, seg=1)
    pts = [Th @ Vector((x + 4 * s, -200, -128)) for x in (-52, 52)]
    a.take(mech.fasteners("_tu", D.seats_on(upper, pts, fwd_t), "M6", target=upper), "Thigh_Upper_Screws",
           "Screws fixing the upper thigh panel to its carrier.")
    pts = [Th @ Vector((x, -200, -336)) for x in (-52, 52)]
    a.take(mech.fasteners("_tl", D.seats_on(lower, pts, fwd_t), "M6", target=lower), "Thigh_Lower_Screws",
           "Screws fixing the lower thigh panel to its carrier.")
    seat = D.seats_on(upper, [Th @ Vector((s * 220, -22, -166))], _dir(Th, (s, 0, 0)), x_hint=_dir(Th, (0, 1, 0)))[0]
    h = F.hatch("_th", 88, 60, seat, target=upper, hinge_side="L", fasteners=2)
    a.take(h["door"], "Thigh_Hatch", "Service hatch over the hip pitch connector and thigh harness.")
    a.take(h["hinge"], "Thigh_Hatch_Hinge", "Hinge of the thigh service hatch.")
    a.take(h["fasteners"], "Thigh_Hatch_Quarter_Turns", "Quarter-turn fasteners latching the thigh service hatch.")

    # strike plate: a second 8 mm layer on the front of the thigh, lapping 18 mm over the gap between the panels
    cx = 2 * s
    sp = raw(A.shell(_overlay(tsec[1:], 8.0), 8.0), Th, "armour", 1.2, 3)
    C.boolean_intersect(sp, C.cutter(P.prism([(cx - 70, -318), (cx + 70, -318), (cx + 84, -296), (cx + 84, -180),
                                              (cx + 64, -158), (cx - 64, -158), (cx - 84, -180), (cx - 84, -296)], 40, 300),
                                     Th @ R("X", 90)), lip=0.6)
    a.take(sp, "Thigh_Strike_Plate", "Second armour layer on the front of the thigh, lapping over the gap between the panels.")
    pts = [Th @ Vector((cx + x, -200, z)) for x, z in ((-46, -168), (46, -168), (-46, -302), (46, -302))]
    a.take(mech.fasteners("_ts", D.seats_on(sp, pts, fwd_t), "M6", target=sp), "Thigh_Strike_Plate_Screws",
           "Screws fixing the thigh strike plate through the panels to their carrier.")

    # ── hamstring guard: a channel behind the knee actuator bodies, on two brackets from the fork cheeks ──
    lean = math.degrees(math.atan(HAM_LEAN))
    zc = (HAM_Z[0] + HAM_Z[1]) / 2

    def ham_y(z):
        return HAM_Y + (z - HAM_Z[1]) * HAM_LEAN

    G = Th @ T(0, ham_y(zc), zc) @ R("X", -lean)     # on the rear wall: local +Y out of it, local Z up it
    Gr = G @ R("X", -90)                             # the same wall as a fitting plane: local Z out of it, local Y down it
    hh = (HAM_Z[0] - HAM_Z[1]) / 2 / math.cos(math.radians(lean))
    hsecs = [A.rsec(hh, 196, 160, 0, -80, 34), A.rsec(hh - 40, 200, 160, 0, -80, 36), A.rsec(-hh, 200, 160, 0, -80, 36)]
    hg = raw(A.shell(hsecs, 10.0), G, "armour", 1.2, 3)
    C.boolean_cut(hg, C.cutter(P.box(400, 300, 400), G @ T(0, -HAM_RET - 150, 0)), lip=0.6)
    cut = bmesh.new()
    for o in (1, -1):                                # top corners cut back, seen from behind
        P.merge(cut, P.box(60, 300, 60), T(o * 104, 0, hh + 4) @ R("Y", 45))
    C.boolean_cut(hg, C.cutter(cut, G), lip=0.6)
    a.take(hg, "Hamstring_Guard", "Rear thigh armour over the knee actuator bodies, standing off the knee fork on brackets.")
    # left and right differ here: the left guard carries the service hatch, the right one is slotted for cooling
    if s > 0:
        h = F.hatch("_hh", 96, 52, Gr @ T(0, 52 - hh, 0), target=hg, hinge_side="L", fasteners=2)
        a.take(h["door"], "Hamstring_Hatch", "Service hatch in the left hamstring guard over the knee actuator motors.")
        a.take(h["hinge"], "Hamstring_Hatch_Hinge", "Hinge of the hamstring service hatch.")
        a.take(h["fasteners"], "Hamstring_Hatch_Quarter_Turns", "Quarter-turn fasteners latching the hamstring service hatch.")
    else:
        A.slots(hg, Gr @ T(0, 50 - hh, 0), 4, 84, 7, 16, depth=24)
    F.panel_cut(hg, [G @ Vector((x, 6, 12 - hh + abs(x) * 0.16)) for x in range(-64, 65, 8)], 1.5, 2.0)
    zb0, zb1 = -200.0, -156.0                        # bracket band on the cheeks: above the encoder cable, below the loom clip
    zbm, y_end = (zb0 + zb1) / 2, ham_y(zb0) - 40
    bars = bmesh.new()
    for o in (1, -1):
        bar = P.prism(P.chamfer_poly([(26, zb0), (y_end, zb0), (y_end, zb1), (26, zb1)], 6), 81, 90)
        P.merge(bars, bar, T(-171 if o < 0 else 0, 0, 0) @ YZ)
    hb = raw(bars, Th, "alu", 0.8, 2)
    C.boolean_cut(hb, C.cutter(P.prism(P.rrect(20, 16, 6, 4), -130, 130), Th @ YZ @ T(77, zbm, 0)), lip=0.4)
    a.take(hb, "Hamstring_Guard_Brackets", "Brackets lapped onto the fork cheeks that carry the hamstring guard clear of the actuators.")
    seats = [Th @ frame((o * 90, 47, z), (o, 0, 0), (0, 0, 1)) for o in (1, -1) for z in (zbm - 11, zbm + 11)]
    a.take(mech.fasteners("_hk", seats, "M6"), "Hamstring_Bracket_Screws",
           "Screws fixing the hamstring guard brackets to the fork cheeks.")
    seats = []
    for o in (1, -1):
        pts = [Th @ Vector((o * 160, ham_y(z) - 52, z)) for z in (zbm - 11, zbm + 11)]
        seats += D.seats_on(hg, pts, _dir(Th, (o, 0, 0)))
    a.take(mech.fasteners("_hs", seats, "M6", target=hg), "Hamstring_Guard_Screws",
           "Screws fixing the hamstring guard to its brackets.")

    # ── knee: slim shaft through the fork, bearing housings outside the cheeks ──
    xe = CHEEK_X + 7.0                               # outer face of a cheek
    shaft = [(0, -xe - 14), (30, -xe - 14), (30, -xe + 14.5), (20, -xe + 17.5), (20, xe - 17.5), (30, xe - 14.5),
             (30, xe + 14), (0, xe + 14)]
    a.add("Knee_Shaft", P.revolve(shaft, 48), "Knee shaft: runs in the fork's bearings and carries the shin tang.", "ti",
          Kn @ R("Y", 90), bevel=0.6)
    Ko = Kn @ T(s * xe, 0, 0) @ R("Y", s * 90)
    prof = [(31, 0), (76, 0), (76, 15), (73, 18), (63, 18), (58, 23), (0, 23), (0, 15), (31, 15)]   # blind bore for the shaft end
    rb, zl = 68.0, 18.0
    ho = a.add("Knee_Bearing_Housing_Outer", P.revolve(prof, 64), "Outer knee bearing housing and cover.", "alu", Ko,
               bevel=0.8)
    a.take(mech.fasteners("_ko", mech.ring((0, 0, zl), (0, 0, 1), rb, 10), "M6", target=ho, matrix=Ko),
           "Knee_Housing_Screws_Outer", "Screws clamping the outer knee bearing cover.")
    a.add("Knee_Bearing_Retainer", P.tube(104, 78, 5, 0.8), "Polished ring retaining the knee bearing in its housing.",
          "steel", Ko @ T(0, 0, 23 + 2.5), bevel=0)
    a.add("Knee_Encoder", D.encoder_bm(58), "Absolute encoder reading knee angle at the shaft end.",
          ["alu", "fastener"], Ko @ T(0, 0, 23) @ R("Z", 90), bevel=0.4)        # gland to the rear on both legs
    Ki = Kn @ T(-s * xe, 0, 0) @ R("Y", -s * 90)
    hi = a.add("Knee_Bearing_Housing_Inner",
               P.revolve([(31, 0), (66, 0), (66, 14), (62, 18), (26, 18), (22, 21), (0, 21), (0, 15), (31, 15)], 64),
               "Inner knee bearing housing and cover.", "alu", Ki, bevel=0.8)
    a.take(mech.fasteners("_ki", mech.ring((0, 0, 18), (0, 0, 1), 46, 8), "M6", target=hi, matrix=Ki),
           "Knee_Housing_Screws_Inner", "Screws clamping the inner knee bearing cover.")
    a.add("Knee_Hard_Stop", D.hard_stop_bm(30, 18, 14), "Bumpered stop on the fork that limits knee over-extension.",
          ["ti", "rubber"], Kn @ frame((s * (CHEEK_X - 7), -46, -40), (-s, 0, 0), (0, 0, -1)), bevel=0.5)

    # two actuators down the fork's corridor, onto the crank pins
    for o, tag in ((s, "Outer"), (-s, "Inner")):
        p0 = Th @ Vector((o * KNEE_P0[0], KNEE_P0[1], KNEE_P0[2]))
        p1 = Sh @ Vector((o * KNEE_P1[0], KNEE_P1[1], KNEE_P1[2]))
        d = mech.linear_actuator("_ka", p0, p1, 46, 30, KNEE_STROKE, pin_axis=xk, body_len=200,
                                 base_dir0=_dir(Th, (0, -0.45, -0.89)))
        for key in ("clevis_b", "pin_b"):            # the shin's own crank plates are the rod-end fork, and the
            spare = d.pop(key)                       # catalogue pin's head and clip would foul the fork cheek
            me = spare.data
            C.bpy.data.objects.remove(spare)
            C.bpy.data.meshes.remove(me)
        a.take_set(d, f"Knee_{tag}", "knee", ACTUATOR_FN)
        a.add(f"Knee_{tag}_Crank_Pin", P.revolve([(0, 0), (7.75, 0), (8.25, 0.5), (8.25, 46.9), (7.75, 47.4), (0, 47.4)], 24),
              f"Crank pin of the {tag.lower()} knee actuator, pressed flush into the crank plate to pass inside the fork cheek.",
              "steel", Sh @ T(o * 18, KNEE_P1[1], KNEE_P1[2]) @ R("Y", o * 90), bevel=0)

    # knee guard on links from the fork and from the crank, so it tracks the joint. Each link is one bar lying
    # against the inboard face of its pivots (fork boss, crank plate, guard bracket) and pinned through them.
    guard = a.add("Knee_Guard", P.plate(P.chamfer_poly(P.rrect(150, 156), 28), 12, crown=10, slices=8),
                  "Armour plate over the knee, carried on links so it tracks the joint.", "armour",
                  Kn @ T(0, -100, 2) @ R("X", 86), bevel=1.2, seg=3)
    up, lo_, seats = bmesh.new(), bmesh.new(), []
    for o in (1, -1):
        P.merge(up, _bar(Kn @ Vector((o * 52, -52, 60)), Kn @ Vector((o * 52, -90, 46)), xk, 9, 6))
        P.merge(lo_, _bar(Sh @ Vector((o * 53, -40, -76)), Kn @ Vector((o * 53, -90, -44)), xk, 9, 8))
        for m, p in ((Kn, (-52, 60)), (Kn, (-90, 46)), (Sh, (-40, -76)), (Kn, (-90, -44))):
            seats.append(frame(m @ Vector((o * 49, p[0], p[1])), -o * xk, (0, 0, 1)))
    a.add("Knee_Guard_Links_Upper", up, "Upper pair of links carrying the knee guard from the fork.", "ti", None,
          bevel=0.5, seg=1)
    a.add("Knee_Guard_Links_Lower", lo_, "Lower pair of links carrying the knee guard from the shin crank.", "ti", None,
          bevel=0.5, seg=1)
    a.take(mech.fasteners("_kl", seats, "M6"), "Knee_Guard_Link_Pins",
           "Shoulder screws on which the knee guard links pivot.")
    gb = bmesh.new()
    for o in (1, -1):
        P.merge(gb, P.box(12, 14, 22), T(o * 61, -93, 46))
        P.merge(gb, P.box(12, 14, 22), T(o * 63, -93, -44))
    a.add("Knee_Guard_Brackets", gb, "Pivot brackets on the back of the knee guard.", "ti", Kn, bevel=0.6, seg=1)
    pts = [Kn @ Vector((x, -200, z)) for x, z in ((-48, 50), (48, 50), (-48, -42), (48, -42))]
    a.take(mech.fasteners("_kg", D.seats_on(guard, pts, fwd_t), "M4", target=guard), "Knee_Guard_Screws",
           "Screws fixing the knee guard to its pivot brackets.")

    # ── shin member: tang and crank on the knee shaft, beam, ankle fork ─────
    py, pz = KNEE_P1[1], KNEE_P1[2]
    root = Vector((0, -(py - 6), -(pz + 112))).normalized()          # from the crank pin down into the beam
    plate = P.chamfer_poly([(py + 22, pz + 2), (py + 12, pz + 20), (py - 12, pz + 22), (-36, -62), (-52, -76), (-40, -90),
                            (0, -128), (40, -128), (py + 20, pz - 24)], 5)
    bodies = [P.loft([A.csec(-96, 92, 76, 0, 6, 0.14), A.csec(-PR.SHIN + 56, 78, 70, 0, 8, 0.14)]),              # beam
              _at(P.prism(P.chamfer_poly(P.rrect(136, 64), 8), -130, -94), T(0, 6, 0)),                       # shoulder under the crank
              _at(P.lug(50, 20.3, 100, 44, 40), frame((0, 0, 0), (1, 0, 0), (0, 0, 1))),                      # tang on the shaft
              _at(P.lug(24, 8.4, 60, 44, 24), frame((0, py, pz), (1, 0, 0), tuple(-root))),                   # centre crank lobe
              _at(P.prism(P.chamfer_poly(P.rrect(160, 76), 10), -PR.SHIN + 44, -PR.SHIN + 64), T(0, 8, 0))]   # crosshead over the ankle fork
    for o in (1, -1):
        bodies.append(_at(P.prism(plate, -4, 4), T(o * 61, 0, 0) @ R("Z", 90) @ R("X", 90)))            # outer crank plates
        bodies.append(_at(P.lug(42, 16, 62, 14, 32), frame((o * 72, 0, -PR.SHIN), (1, 0, 0), (0, 0, -1))))   # ankle fork
        bodies.append(_at(P.box(50, 34, 64), T(o * ANKLE_P0[0], 54, ANKLE_P0[2])))                      # ankle actuator seats
    sm = a.take(_weld(bodies, Sh), "Shin_Member", "Machined shin member: knee tang and crank at the top, ankle fork at the bottom.")
    for o in (1, -1):
        D.pocket_grid(sm, Sh @ T(o * 45.5, 7, -250) @ R("Y", o * 90), 3, 1, 44, 38, 58, 0, depth=8)
    C.boolean_cut(sm, C.cutter(P.box(30, 24, 150), Sh @ T(0, 50, -265)), lip=0.4)
    a.add("Shin_Cable_Channel_Cover", P.prism(P.rrect(42, 162, 5), 0, 2.5),
          "Cover plate over the cable channel down the back of the shin.", "alu",
          Sh @ T(0, 42.6, -265) @ R("X", -90), bevel=0.4)
    seats = [Sh @ T(o * 15, 45.1, -265 + z) @ R("X", -90) for o in (1, -1) for z in (-70, 0, 70)]
    a.take(mech.fasteners("_cc", seats, "M4", "csk"), "Shin_Channel_Cover_Screws",
           "Countersunk screws holding the shin cable channel cover.")

    # ── shin armour: one shell sliced into a front panel and two side panels ──
    ssec = [(-40, 168, 164, 0, -8, 40), (-112, 190, 196, 0, -2, 48), (-236, 170, 160, 0, -12, 40),
            (-340, 158, 142, 0, -12, 34)]         # stops above the ankle fork and its crosshead
    secs = [A.rsec(*t) for t in ssec]

    def open_shin(ob, lip=0.6):
        C.boolean_cut(ob, C.cutter(P.box(500, 300, 700), Sh @ T(0, 40 + 150, -200)), lip=lip)
        C.boolean_cut(ob, C.cutter(P.cyl(186, 500, 64), Sh @ R("Y", 90)), lip=lip)
        C.boolean_cut(ob, C.cutter(P.cyl(92, 300, 48), Sh @ T(0, -60, -PR.SHIN + 30) @ R("X", 90)), lip=lip)

    sh = raw(A.shell(secs, 10.0), Sh, "armour", 1.2, 3)
    open_shin(sh)
    for o in (1, -1):
        A.gap_cut(sh, Sh @ Vector((o * 62, 0, -200)), _dir(Sh, (1, 0, 0)))
    pieces = sorted(A.islands(sh), key=lambda o: -len(o.data.vertices))[:3]
    pieces.sort(key=lambda o: _local(Sh, o).x * s)
    inner, front, outer = pieces
    A.slots(front, Sh @ T(0, -97, -150) @ R("X", 90), 3, 72, 7, 17, depth=24)
    a.take(front, "Shin_Armour_Front", "Front shin armour panel with cooling slots for the ankle actuators.")
    a.take(outer, "Shin_Armour_Outer", "Outer shin armour side panel.")
    a.take(inner, "Shin_Armour_Inner", "Inner shin armour side panel.")
    vb = bmesh.new()
    uv = vb.loops.layers.uv.new("UVMap")
    f = vb.faces.new([vb.verts.new((x, y, 0)) for x, y in P.rrect(86, 56, 4)])
    for lp in f.loops:
        lp[uv].uv = (lp.vert.co.x * C.MM, lp.vert.co.y * C.MM)
    wall = math.degrees(math.atan(8 / 124))          # the front wall leans back this much between its two sections
    a.add("Shin_Vent_Screen", vb, "Mesh screen bonded to the inside of the front panel behind the cooling slots.", "mesh",
          Sh @ T(0, -87.3, -150) @ R("X", 90 + wall), bevel=0)
    car = a.add("Shin_Armour_Carrier", A.hoops(secs, (-190, -300), band=18.0),
                "Carbon ribs bonded inside the shin armour, carrying it off the shin member.", "cfrp", Sh, bevel=0.3,
                seg=1)
    open_shin(car, lip=None)
    posts = bmesh.new()
    for z in (-190, -300):
        for x in (-28, 28):
            P.merge(posts, P.cyl(14, 54, 16), T(x, -59, z) @ R("X", 90))
    a.add("Shin_Carrier_Standoffs", posts, "Standoff posts fixing the shin armour carrier to the shin member.", "alu", Sh,
          bevel=0.4, seg=1)
    pts = [Sh @ Vector((x, -200, z)) for x, z in ((-44, -72), (44, -72), (-40, -326), (40, -326))]
    a.take(mech.fasteners("_sf", D.seats_on(front, pts, fwd_s), "M6", target=front), "Shin_Front_Screws",
           "Screws fixing the front shin panel to its carrier.")
    for ob, o, tag in ((outer, s, "Outer"), (inner, -s, "Inner")):
        pts = [Sh @ Vector((o * 200, y, z)) for y, z in ((-34, -96), (-30, -200), (-34, -310))]
        a.take(mech.fasteners("_ss", D.seats_on(ob, pts, _dir(Sh, (o, 0, 0))), "M6", target=ob),
               f"Shin_{tag}_Screws", f"Screws fixing the {tag.lower()} shin side panel to its carrier.")

    # strike plate: a second 8 mm layer down the front of the shin, lapping 14 mm over both side panel gaps
    sp = raw(A.shell(_overlay(ssec[1:], 8.0), 8.0), Sh, "armour", 1.2, 3)
    C.boolean_intersect(sp, C.cutter(P.prism([(-62, -306), (62, -306), (76, -290), (76, -206), (40, -192), (-40, -192),
                                              (-76, -206), (-76, -290)], 40, 300), Sh @ R("X", 90)), lip=0.6)
    a.take(sp, "Shin_Strike_Plate", "Second armour layer down the front of the shin, lapping over the side panel gaps.")
    pts = [Sh @ Vector((x, -200, z)) for x, z in ((-44, -208), (44, -208), (-44, -292), (44, -292))]
    a.take(mech.fasteners("_sk", D.seats_on(sp, pts, fwd_s), "M6", target=sp), "Shin_Strike_Plate_Screws",
           "Screws fixing the shin strike plate through the front panel to its carrier.")

    # ── ankle actuators: two parallel roller screws down the back of the shin ──
    for o, tag in ((s, "Outer"), (-s, "Inner")):
        p0 = Sh @ Vector((o * ANKLE_P0[0], ANKLE_P0[1], ANKLE_P0[2]))
        p1 = Ft @ Vector((o * ANKLE_P1[0], ANKLE_P1[1], ANKLE_P1[2]))
        d = mech.linear_actuator("_aa", p0, p1, 34, 20, 60, pin_axis=xk, body_len=112,
                                 base_dir0=_dir(Sh, (0, -1, 0)), base_dir1=Vector((0, 0, -1)))
        a.take_actuator(d, f"Ankle_{tag}", "ankle")

    # ── calf guard: a channel behind the ankle actuators, on two pylons that stand between them ──
    csecs = [A.rsec(-196, 156, 120, 0, CALF_Y - 60, 30), A.rsec(-292, 156, 120, 0, CALF_Y - 60, 30),
             A.rsec(CALF_BOT, 146, 116, 0, CALF_Y - 60, 28)]
    cg = raw(A.shell(csecs, 10.0), Sh, "armour", 1.2, 3)
    C.boolean_cut(cg, C.cutter(P.box(400, 300, 500), Sh @ T(0, CALF_FRONT - 150, -280)), lip=0.6)
    rake = math.degrees(math.atan(CALF_RAKE))        # top edge parallel to the folded thigh at full flexion
    C.boolean_cut(cg, C.cutter(P.box(400, 400, 200), Sh @ T(0, CALF_Y, CALF_TOP) @ R("X", -rake) @ T(0, 0, 100)), lip=0.6)
    a.take(cg, "Calf_Guard", "Rear shin armour over the ankle actuators, raked at the top to clear the folded thigh.")
    F.panel_cut(cg, [Sh @ Vector((x, CALF_Y + 6, -336 + abs(x) * 0.2)) for x in range(-48, 49, 8)], 1.5, 2.0)

    def beam(z):
        """Shin beam section (width, depth, centre y) at shin-frame height z."""
        t = (z + 96) / (-PR.SHIN + 56 + 96)
        return 92 + (78 - 92) * t, 76 + (70 - 76) * t, 6 + 2 * t

    pyl, seats, gpts = bmesh.new(), [], []
    for z in (-250, -316):
        w, dp, dy = beam(z)
        yr, fx = dy + dp / 2 - 0.3, 0.36 * w         # rear face of the beam and half its flat width
        n = Vector((0.14 * dp, 0.14 * w)).normalized()               # out of the beam's rear chamfer
        q = Vector((fx + 0.85 * 0.14 * w, yr - 0.85 * 0.14 * dp))
        yf = CALF_Y - 10 - max(0.0, -292 - z) * 2 / 64 + 0.4         # inner face of the guard's rear wall
        half = [(0, yr + 4.5), (23, yr + 4.5), (23, yr), (fx, yr), tuple(q), tuple(q + n * 6), (fx + n.x * 6, yr + n.y * 6),
                (fx + n.x * 6, yr + 10), (5, yr + 10), (5, yf - 7), (26, yf - 7), (26, yf)]
        P.merge(pyl, P.prism(P.mirror_x(half), z - 12, z + 12))
        mid = (Vector((fx, yr)) + q) / 2 + n * 6
        for o in (1, -1):
            seats.append(Sh @ frame((o * mid.x, mid.y, z), (o * n.x, n.y, 0), (0, 0, 1)))
            gpts.append(Sh @ Vector((o * 15, 220, z)))
    a.add("Calf_Guard_Pylons", pyl, "Pylons between the ankle actuators: they straddle the cable channel and carry the calf guard.",
          "alu", Sh, bevel=0.6)
    a.take(mech.fasteners("_cp", seats, "M4"), "Calf_Pylon_Screws", "Screws fixing the calf guard pylons to the shin beam.")
    a.take(mech.fasteners("_cs", D.seats_on(cg, gpts, _dir(Sh, (0, 1, 0))), "M6", target=cg), "Calf_Guard_Screws",
           "Screws fixing the calf guard to its pylons.")
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    s = 1 if a.aa == "11" else -1
    knee = [o for o in objs if "Knee" in o.name or "Shin_Member" in o.name or "Thigh_Frame" in o.name]
    kc = FR.leg(s)[2].translation
    RV.closeup(knee, out / f"{a.aa}_knee_rear_clay{tag}.jpg", f"{a.aa} knee, rear three-quarter", (s * 0.75, 0.8, 0.12),
               "clay", target=kc, dist=1.5, isolate=True)
    RV.closeup(knee, out / f"{a.aa}_knee_inner_clay{tag}.jpg", f"{a.aa} knee mechanism, inner side", (-s * 1.0, 0.25, 0.05),
               "clay", target=kc, dist=1.5, isolate=True)
    RV.closeup(objs, out / f"{a.aa}_leg_rear_final{tag}.jpg", f"{a.aa} leg, rear three-quarter", (s * 0.7, 0.8, 0.15),
               "final", res=(1000, 1500), dist=1.9, isolate=True)
    for name, d in (("rear", (s * 0.55, 0.8, 0.2)), ("rear_inner", (-s * 0.6, 0.8, 0.15)), ("front", (s * 0.5, -0.85, 0.15))):
        RV.closeup(objs, out / f"{a.aa}_leg_{name}_clay{tag}.jpg", f"{a.aa} leg, {name}", d, "clay", res=(1000, 1500),
                   dist=2.6, isolate=True)
    hip = [o for o in objs if "Hip" in o.name or "Thigh_Frame" in o.name]
    RV.closeup(hip, out / f"{a.aa}_hip_outer_clay{tag}.jpg", f"{a.aa} hip, outer side", (s * 1.0, 0.35, 0.1), "clay",
               target=FR.leg(s)[0].translation, dist=1.2, isolate=True)
