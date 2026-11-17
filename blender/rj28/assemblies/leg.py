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
"""
import math

import bmesh
from mathutils import Vector

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


def _dir(m, v):
    return (m.to_3x3() @ Vector(v)).normalized()


def _local(m, ob):
    lo, hi = C.bounds_mm([ob])
    return m.inverted() @ ((lo + hi) / 2)


def build(s):
    a = Asm("11" if s > 0 else "12")
    Lg, Th, Kn, Sh, An, Ft = FR.leg(s)
    xk = _dir(Th, (1, 0, 0))                         # pitch axis of hip, knee and ankle
    fwd_t, fwd_s = _dir(Th, (0, -1, 0)), _dir(Sh, (0, -1, 0))
    zk = -PR.THIGH                                   # knee axis height in the thigh frame

    # ── hip pitch actuator: its housing is the top of the thigh ─────────────
    d = mech.rotary_actuator("_hip", 174, 150, Lg @ T(-s * 67, 0, 0) @ R("Y", s * 90), bolts=0)
    a.take_rotary(d, "Hip_Pitch", "hip pitch")

    # ── thigh frame: hangers on the actuator, beam, crosshead, knee fork ────
    bm = bmesh.new()
    P.merge(bm, P.lug(78, 30, 150, 14, 40), frame((s * 93, 0, 0), (1, 0, 0), (0, 0, 1)))        # on the output flange
    P.merge(bm, P.lug(64, 36, 150, 12, 40), frame((-s * 74, 0, 0), (1, 0, 0), (0, 0, 1)))       # idler side
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(190, 124), 14), -152, -112), T(s * 10, 14, 0))   # top crosshead
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(132, 46), 8), -126, -82), T(0, 96, 0))           # knee actuator anchor
    P.merge(bm, P.loft([A.csec(-150, 98, 84, 0, 30, 0.14), A.csec(-206, 92, 78, 0, 14, 0.14)]))  # beam
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(2 * CHEEK_X + 14, 84), 10), -204, -164), T(0, 8, 0))   # fork crosshead
    for o in (1, -1):
        P.merge(bm, P.lug(60, 31, -zk - 150, 14, 40), frame((o * CHEEK_X, 0, zk), (1, 0, 0), (0, 0, -1)))   # fork cheeks
        P.merge(bm, P.box(12, 18, 22), T(o * 61, -50, zk + 60))                                 # knee guard link pivots
    tf = a.add("Thigh_Frame", bm, "Machined thigh member: hangs from the hip pitch output and ends in the knee fork.",
               "alu", Th, bevel=1.0)
    D.pocket_grid(tf, Th @ T(0, 54.5, -178) @ R("X", -90), 1, 1, 56, 30, 0, 0, depth=8)
    D.pocket_grid(tf, Th @ T(s * 100.2, 0, -110) @ R("Y", s * 90), 1, 1, 26, 96, 0, 0, depth=6)
    for o in (1, -1):
        D.pocket_grid(tf, Th @ T(o * (CHEEK_X + 7.2), 0, -272) @ R("Y", o * 90), 2, 1, 58, 62, 72, 0, depth=5)
    seats = mech.ring((s * 100, 0, 0), (s, 0, 0), 52, 12, x_hint=(0, 0, 1))
    a.take(mech.fasteners("_hb", seats, "M6", target=tf, matrix=Th), "Hip_Hanger_Bolts",
           "Screws clamping the thigh hanger to the hip pitch output flange.")

    # ── thigh armour: one shell, opened at the rear and inner side, split in two ──
    secs = [A.rsec(-80, 152, 192, -10 * s, -14, 36), A.rsec(-130, 206, 204, 4 * s, -18, 44),
            A.rsec(-200, 212, 206, 4 * s, -18, 46), A.rsec(-300, 198, 190, 0, -14, 42),
            A.rsec(-372, 190, 172, 0, -8, 38)]

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
    F.panel_cut(upper, [Th @ Vector((x + 4 * s, -126, -170 + y)) for x, y in P.rrect(104, 50, 9, 4)], 1.5, 2.0,
                closed=True)
    car = a.add("Thigh_Armour_Carrier", A.hoops(secs, (-168, -300), band=18.0),
                "Carbon ribs bonded inside the thigh armour, carrying it off the frame.", "cfrp", Th, bevel=0.3, seg=1)
    open_thigh(car, lip=None)
    posts = bmesh.new()
    for x in (-30, 30):
        P.merge(posts, P.cyl(14, 88, 16), T(x, -60, -168) @ R("X", 90))
        P.merge(posts, P.cyl(14, 44, 16), T(x * 2.2, -82, -300) @ R("X", 90))
    a.add("Thigh_Carrier_Standoffs", posts, "Standoff posts fixing the thigh armour carrier to the thigh frame.", "alu",
          Th, bevel=0.4, seg=1)
    pts = [Th @ Vector((x * 1.0 + 4 * s, -200, z)) for x, z in ((-52, -128), (52, -128), (-58, -196), (58, -196))]
    a.take(mech.fasteners("_tu", D.seats_on(upper, pts, fwd_t), "M6", target=upper), "Thigh_Upper_Screws",
           "Screws fixing the upper thigh panel to its carrier.")
    pts = [Th @ Vector((x, -200, z)) for x, z in ((-56, -262), (56, -262), (-52, -330), (52, -330))]
    a.take(mech.fasteners("_tl", D.seats_on(lower, pts, fwd_t), "M6", target=lower), "Thigh_Lower_Screws",
           "Screws fixing the lower thigh panel to its carrier.")
    seat = D.seats_on(upper, [Th @ Vector((s * 220, -22, -166))], _dir(Th, (s, 0, 0)), x_hint=_dir(Th, (0, 1, 0)))[0]
    h = F.hatch("_th", 88, 60, seat, target=upper, hinge_side="L", fasteners=2)
    a.take(h["door"], "Thigh_Hatch", "Service hatch over the hip pitch connector and thigh harness.")
    a.take(h["hinge"], "Thigh_Hatch_Hinge", "Hinge of the thigh service hatch.")
    a.take(h["fasteners"], "Thigh_Hatch_Quarter_Turns", "Quarter-turn fasteners latching the thigh service hatch.")

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
        fork = d.pop("clevis_b")                     # the shin's own crank plates are the rod-end fork
        me = fork.data
        C.bpy.data.objects.remove(fork)
        C.bpy.data.meshes.remove(me)
        a.take_set(d, f"Knee_{tag}", "knee", ACTUATOR_FN)

    # knee guard on links from the fork and from the crank, so it tracks the joint
    guard = a.add("Knee_Guard", P.plate(P.chamfer_poly(P.rrect(150, 156), 28), 12, crown=10, slices=8),
                  "Armour plate over the knee, carried on links so it tracks the joint.", "armour",
                  Kn @ T(0, -100, 2) @ R("X", 86), bevel=1.2, seg=3)
    up, lo_ = bmesh.new(), bmesh.new()
    for o in (1, -1):
        P.merge(up, D.link_between(Kn @ Vector((o * 61, -52, 60)), Kn @ Vector((o * 61, -90, 46)), xk, 9, 3.5, 6))
        P.merge(lo_, D.link_between(Sh @ Vector((o * 61, -40, -76)), Kn @ Vector((o * 61, -90, -44)), xk, 9, 3.5, 6))
    a.add("Knee_Guard_Links_Upper", up, "Upper pair of links carrying the knee guard from the fork.", "ti", None,
          bevel=0.5, seg=1)
    a.add("Knee_Guard_Links_Lower", lo_, "Lower pair of links carrying the knee guard from the shin crank.", "ti", None,
          bevel=0.5, seg=1)
    gb = bmesh.new()
    for o in (1, -1):
        for z in (46, -44):
            P.merge(gb, P.box(16, 14, 22), T(o * 61, -93, z))
    a.add("Knee_Guard_Brackets", gb, "Pivot brackets on the back of the knee guard.", "ti", Kn, bevel=0.6, seg=1)
    pts = [Kn @ Vector((x, -200, z)) for x, z in ((-48, 50), (48, 50), (-48, -42), (48, -42))]
    a.take(mech.fasteners("_kg", D.seats_on(guard, pts, fwd_t), "M4", target=guard), "Knee_Guard_Screws",
           "Screws fixing the knee guard to its pivot brackets.")

    # ── shin member: tang and crank on the knee shaft, beam, ankle fork ─────
    py, pz = KNEE_P1[1], KNEE_P1[2]
    root = Vector((0, -(py - 6), -(pz + 112))).normalized()          # from the crank pin down into the beam
    bm = bmesh.new()
    P.merge(bm, P.lug(50, 20.3, 96, 44, 40), frame((0, 0, 0), (1, 0, 0), (0, 0, 1)))            # tang on the shaft
    P.merge(bm, P.lug(24, 8.4, 60, 44, 24), frame((0, py, pz), (1, 0, 0), tuple(-root)))        # centre crank lobe
    plate = P.chamfer_poly([(py + 22, pz + 2), (py + 12, pz + 20), (py - 12, pz + 22), (-36, -62), (-52, -76), (-40, -90),
                            (0, -128), (40, -128), (py + 20, pz - 24)], 5)
    for o in (1, -1):
        P.merge(bm, P.prism(plate, -4, 4), T(o * 61, 0, 0) @ R("Z", 90) @ R("X", 90))             # outer crank plates
        P.merge(bm, P.lug(42, 16, 62, 14, 32), frame((o * 72, 0, -PR.SHIN), (1, 0, 0), (0, 0, -1)))   # ankle fork
        P.merge(bm, P.box(50, 34, 64), T(o * ANKLE_P0[0], 54, ANKLE_P0[2]))                      # ankle actuator seats
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(136, 64), 8), -130, -94), T(0, 6, 0))            # shoulder under the crank
    P.merge(bm, P.loft([A.csec(-96, 92, 76, 0, 6, 0.14), A.csec(-PR.SHIN + 70, 78, 70, 0, 8, 0.14)]))   # beam
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(160, 76), 10), -PR.SHIN + 44, -PR.SHIN + 78), T(0, 8, 0))
    sm = a.add("Shin_Member", bm, "Machined shin member: knee tang and crank at the top, ankle fork at the bottom.",
               "alu", Sh, bevel=1.0)
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
    secs = [A.rsec(-40, 168, 164, 0, -8, 40), A.rsec(-112, 190, 196, 0, -2, 48), A.rsec(-236, 170, 160, 0, -12, 40),
            A.rsec(-336, 158, 142, 0, -12, 34), A.rsec(-366, 168, 152, 0, -10, 34)]

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
    F.panel_cut(front, [Sh @ Vector((x, -104, -206 - abs(x) * 0.12)) for x in range(-56, 57, 8)], 1.5, 2.0)
    a.take(front, "Shin_Armour_Front", "Front shin armour panel with cooling slots for the ankle actuators.")
    a.take(outer, "Shin_Armour_Outer", "Outer shin armour side panel.")
    a.take(inner, "Shin_Armour_Inner", "Inner shin armour side panel.")
    vb = bmesh.new()
    uv = vb.loops.layers.uv.new("UVMap")
    f = vb.faces.new([vb.verts.new((x, y, 0)) for x, y in P.rrect(86, 56, 4)])
    for lp in f.loops:
        lp[uv].uv = (lp.vert.co.x * C.MM, lp.vert.co.y * C.MM)
    a.add("Shin_Vent_Screen", vb, "Mesh screen behind the shin cooling slots.", "mesh", Sh @ T(0, -84, -150) @ R("X", 90),
          bevel=0)
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
    pts = [Sh @ Vector((x, -200, z)) for x, z in ((-44, -72), (44, -72), (-48, -232), (48, -232), (-40, -322), (40, -322))]
    a.take(mech.fasteners("_sf", D.seats_on(front, pts, fwd_s), "M6", target=front), "Shin_Front_Screws",
           "Screws fixing the front shin panel to its carrier.")
    for ob, o, tag in ((outer, s, "Outer"), (inner, -s, "Inner")):
        pts = [Sh @ Vector((o * 200, y, z)) for y, z in ((-34, -96), (-30, -200), (-34, -310))]
        a.take(mech.fasteners("_ss", D.seats_on(ob, pts, _dir(Sh, (o, 0, 0))), "M6", target=ob),
               f"Shin_{tag}_Screws", f"Screws fixing the {tag.lower()} shin side panel to its carrier.")

    # ── ankle actuators: two parallel roller screws down the back of the shin ──
    for o, tag in ((s, "Outer"), (-s, "Inner")):
        p0 = Sh @ Vector((o * ANKLE_P0[0], ANKLE_P0[1], ANKLE_P0[2]))
        p1 = Ft @ Vector((o * ANKLE_P1[0], ANKLE_P1[1], ANKLE_P1[2]))
        d = mech.linear_actuator("_aa", p0, p1, 34, 20, 60, pin_axis=xk, body_len=112,
                                 base_dir0=_dir(Sh, (0, -1, 0)), base_dir1=Vector((0, 0, -1)))
        a.take_actuator(d, f"Ankle_{tag}", "ankle")
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
