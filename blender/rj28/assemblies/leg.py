"""Assemblies 11 / 12: leg, left / right.

Hip pitch actuator, thigh frame and armour, knee crank joint with its two
linear actuators, shin member and armour, ankle actuators. The ankle joint
itself and everything below it belong to the foot (13 / 14).

Frames (rj28.frames.leg): thigh and shin frames have +X along the joint axes,
+Y to the rear and -Z running down the limb. "Outer" is s * X.
"""
import bmesh
from mathutils import Vector

from .. import frames as FR, params as PR
from ..lib import armour as A, core as C, detail as D, fittings as F, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm, raw


def _dir(m, v):
    return (m.to_3x3() @ Vector(v)).normalized()


def _local(m, ob):
    lo, hi = C.bounds_mm([ob])
    return m.inverted() @ ((lo + hi) / 2)


def build(s):
    a = Asm("11" if s > 0 else "12")
    Lg, Th, Kn, Sh, An, Ft = FR.leg(s)
    xk = _dir(Th, (1, 0, 0))                     # pitch axis of hip, knee and ankle
    fwd_t, fwd_s = _dir(Th, (0, -1, 0)), _dir(Sh, (0, -1, 0))

    # ── hip pitch actuator: its housing is the top of the thigh ─────────────
    d = mech.rotary_actuator("_hip", 174, 150, Lg @ T(-s * 67, 0, 0) @ R("Y", s * 90), bolts=0)
    a.take_rotary(d, "Hip_Pitch", "hip pitch")

    # ── thigh frame: two hangers on the actuator, pocketed beam, knee fork ──
    bm = bmesh.new()
    P.merge(bm, P.lug(78, 30, 150, 14, 40), frame((s * 93, 0, 0), (1, 0, 0), (0, 0, 1)))
    P.merge(bm, P.lug(64, 36, 150, 12, 40), frame((-s * 74, 0, 0), (1, 0, 0), (0, 0, 1)))
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(190, 124), 14), -152, -112), T(s * 10, 14, 0))
    P.merge(bm, P.loft([A.csec(-150, 98, 84, 0, 30, 0.14), A.csec(-330, 88, 74, 0, 32, 0.14)]))
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(164, 84), 12), -346, -314), T(0, 24, 0))   # knee crosshead, clear of the tang
    for o in (1, -1):
        P.merge(bm, P.lug(60, 34, 74, 14, 40), frame((o * 68, 0, -PR.THIGH), (1, 0, 0), (0, 0, -1)))
        P.merge(bm, P.box(18, 16, 22), T(o * 40, -24, -PR.THIGH + 66))                      # knee guard link pivots
    tf = a.add("Thigh_Frame", bm, "Machined thigh member: hangs from the hip pitch output and carries the knee fork.",
               "alu", Th, bevel=1.0)
    D.pocket_grid(tf, Th @ T(0, 71.5, -240) @ R("X", -90), 1, 3, 50, 40, 0, 54, depth=9)
    for o in (1, -1):
        D.pocket_grid(tf, Th @ T(o * 47.5, 31, -240) @ R("Y", o * 90), 3, 1, 40, 40, 54, 0, depth=8)
    D.pocket_grid(tf, Th @ T(s * 100.2, 0, -110) @ R("Y", s * 90), 1, 1, 26, 96, 0, 0, depth=6)
    seats = mech.ring((s * 100, 0, 0), (s, 0, 0), 52, 12, x_hint=(0, 0, 1))
    a.take(mech.fasteners("_hb", seats, "M6", target=tf, matrix=Th), "Hip_Hanger_Bolts",
           "Screws clamping the thigh hanger to the hip pitch output flange.")

    # ── thigh armour: one shell, opened at the rear and inner side, split in two ──
    secs = [A.rsec(-80, 152, 192, -10 * s, -14, 36), A.rsec(-130, 206, 204, 4 * s, -18, 44),
            A.rsec(-200, 212, 206, 4 * s, -18, 46), A.rsec(-300, 190, 186, 0, -14, 42),
            A.rsec(-372, 166, 166, 0, -8, 36)]
    def open_thigh(ob, lip=0.6):
        """The armour (and its carrier) cover the front and outer side only."""
        C.boolean_cut(ob, C.cutter(P.box(500, 300, 700), Th @ T(0, 36 + 150, -220)), lip=lip)
        C.boolean_cut(ob, C.cutter(P.box(200, 260, 700), Th @ T(-s * 172, 70, -220)), lip=lip)
        C.boolean_cut(ob, C.cutter(P.cyl(198, 500, 64), Th @ R("Y", 90)), lip=lip)
        C.boolean_cut(ob, C.cutter(P.cyl(178, 500, 64), Kn @ R("Y", 90)), lip=lip)

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
    for z in (-168, -300):
        for x in (-30, 30):
            P.merge(posts, P.cyl(14, 82, 16), T(x, -53, z) @ R("X", 90))
    a.add("Thigh_Carrier_Standoffs", posts, "Standoff posts fixing the thigh armour carrier to the thigh frame.", "alu",
          Th, bevel=0.4, seg=1)
    pts = [Th @ Vector((x * 1.0 + 4 * s, -200, z)) for x, z in ((-52, -128), (52, -128), (-58, -196), (58, -196))]
    a.take(mech.fasteners("_tu", D.seats_on(upper, pts, fwd_t), "M6", target=upper), "Thigh_Upper_Screws",
           "Screws fixing the upper thigh panel to its carrier.")
    pts = [Th @ Vector((x, -200, z)) for x, z in ((-56, -262), (56, -262), (-46, -330), (46, -330))]
    a.take(mech.fasteners("_tl", D.seats_on(lower, pts, fwd_t), "M6", target=lower), "Thigh_Lower_Screws",
           "Screws fixing the lower thigh panel to its carrier.")
    seat = D.seats_on(upper, [Th @ Vector((s * 220, -22, -166))], _dir(Th, (s, 0, 0)), x_hint=_dir(Th, (0, 1, 0)))[0]
    h = F.hatch("_th", 88, 60, seat, target=upper, hinge_side="L", fasteners=2)
    a.take(h["door"], "Thigh_Hatch", "Service hatch over the hip pitch connector and thigh harness.")
    a.take(h["hinge"], "Thigh_Hatch_Hinge", "Hinge of the thigh service hatch.")
    a.take(h["fasteners"], "Thigh_Hatch_Quarter_Turns", "Quarter-turn fasteners latching the thigh service hatch.")

    # ── knee: hub through the fork, bearing housings, crank driven from behind ──
    a.add("Knee_Hub", P.cyl(100, 152, 48), "Knee shaft joining the thigh fork to the shin tang.", "ti",
          Kn @ R("Y", 90), bevel=1.0)
    Ko = Kn @ T(s * 76, 0, 0) @ R("Y", s * 90)
    prof, rb, zl = D.bolted_cover_profile(76, 18, 0.0, 13.0, 5.0)
    ho = a.add("Knee_Bearing_Housing_Outer", P.revolve(prof, 64), "Outer knee bearing housing and cover.", "alu", Ko,
               bevel=0.8)
    a.take(mech.fasteners("_ko", mech.ring((0, 0, zl), (0, 0, 1), rb, 10), "M6", target=ho, matrix=Ko),
           "Knee_Housing_Screws_Outer", "Screws clamping the outer knee bearing cover.")
    a.add("Knee_Bearing_Retainer", P.tube(104, 78, 5, 0.8), "Polished ring retaining the knee bearing in its housing.",
          "steel", Ko @ T(0, 0, 23 + 2.5), bevel=0)
    a.add("Knee_Encoder", D.encoder_bm(58), "Absolute encoder reading knee angle at the shaft end.",
          ["alu", "fastener"], Ko @ T(0, 0, 23) @ R("Z", 90 * s), bevel=0.4)
    Ki = Kn @ T(-s * 76, 0, 0) @ R("Y", -s * 90)
    hi = a.add("Knee_Bearing_Housing_Inner", P.revolve([(0, 0), (66, 0), (66, 9), (62, 13), (26, 13), (22, 16), (0, 16)], 64),
               "Inner knee bearing housing and cover.", "alu", Ki, bevel=0.8)
    a.take(mech.fasteners("_ki", mech.ring((0, 0, 13), (0, 0, 1), 52, 8), "M6", target=hi, matrix=Ki),
           "Knee_Housing_Screws_Inner", "Screws clamping the inner knee bearing cover.")
    a.add("Knee_Hard_Stop", D.hard_stop_bm(40, 20, 16), "Bumpered stop that limits knee extension.", ["ti", "rubber"],
          Kn @ frame((0, -18, 56), (0, -1, 0), (0, 0, -1)), bevel=0.5)
    for o, tag in ((s, "Outer"), (-s, "Inner")):
        p0 = Th @ Vector((o * 36, 104, -122))
        p1 = Sh @ Vector((o * 36, 86, -12))
        d = mech.linear_actuator("_ka", p0, p1, 46, 30, 90, pin_axis=xk, body_len=150,
                                 base_dir0=_dir(Th, (0, -1, 0.15)), base_dir1=_dir(Sh, (0, -1, -0.3)))
        a.take_actuator(d, f"Knee_{tag}", "knee")

    # knee guard on a four-bar linkage so it follows the joint
    guard = a.add("Knee_Guard", P.plate(P.chamfer_poly(P.rrect(128, 156), 28), 12, crown=9, slices=8),
                  "Armour plate over the knee, carried on links so it tracks the joint.", "armour",
                  Kn @ T(0, -98, 2) @ R("X", 86), bevel=1.2, seg=3)
    up, lo_ = bmesh.new(), bmesh.new()
    for o in (1, -1):
        P.merge(up, D.link_between(Kn @ Vector((o * 40, -24, 66)), Kn @ Vector((o * 40, -88, 46)), xk, 9, 3.5, 6))
        P.merge(lo_, D.link_between(Sh @ Vector((o * 40, -40, -76)), Kn @ Vector((o * 40, -88, -44)), xk, 9, 3.5, 6))
    a.add("Knee_Guard_Links_Upper", up, "Upper pair of links carrying the knee guard from the thigh.", "ti", None,
          bevel=0.5, seg=1)
    a.add("Knee_Guard_Links_Lower", lo_, "Lower pair of links carrying the knee guard from the shin.", "ti", None,
          bevel=0.5, seg=1)
    gb = bmesh.new()
    for o in (1, -1):
        for z in (46, -44):
            P.merge(gb, P.box(16, 14, 22), T(o * 40, -91, z))
    a.add("Knee_Guard_Brackets", gb, "Pivot brackets on the back of the knee guard.", "ti", Kn, bevel=0.6, seg=1)
    pts = [Kn @ Vector((x, -200, z)) for x, z in ((-40, 50), (40, 50), (-40, -42), (40, -42))]
    a.take(mech.fasteners("_kg", D.seats_on(guard, pts, fwd_t), "M4", target=guard), "Knee_Guard_Screws",
           "Screws fixing the knee guard to its pivot brackets.")

    # ── shin member: tang on the knee hub, crank block, beam, ankle fork ────
    bm = bmesh.new()
    P.merge(bm, P.lug(58, 34, 84, 118, 40), frame((0, 0, 0), (1, 0, 0), (0, 0, 1)))
    P.merge(bm, P.box(118, 46, 66), T(0, 36, -30) @ R("X", -17))                  # crank block: seat of the knee actuator forks
    P.merge(bm, P.box(40, 24, 14), T(0, -58, 34))                                  # stop tab that meets the knee hard stop
    for o in (1, -1):
        P.merge(bm, P.box(18, 14, 22), T(o * 40, -41, -76))                        # knee guard link pivots
    P.merge(bm, P.loft([A.csec(-60, 90, 82, 0, 6, 0.14), A.csec(-PR.SHIN + 70, 78, 70, 0, 8, 0.14)]))
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(160, 76), 10), -PR.SHIN + 44, -PR.SHIN + 78), T(0, 8, 0))
    for o in (1, -1):
        P.merge(bm, P.lug(42, 16, 62, 14, 32), frame((o * 72, 0, -PR.SHIN), (1, 0, 0), (0, 0, -1)))
        P.merge(bm, P.box(50, 34, 64), T(o * 40, 54, -150))
    sm = a.add("Shin_Member", bm, "Machined shin member: knee tang and crank at the top, ankle fork at the bottom.",
               "alu", Sh, bevel=1.0)
    for o in (1, -1):
        D.pocket_grid(sm, Sh @ T(o * 44.5, 7, -240) @ R("Y", o * 90), 3, 1, 44, 38, 58, 0, depth=8)
    C.boolean_cut(sm, C.cutter(P.box(30, 24, 150), Sh @ T(0, 50, -265)), lip=0.4)
    cov = a.add("Shin_Cable_Channel_Cover", P.prism(P.rrect(42, 162, 5), 0, 2.5),
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
        C.boolean_cut(ob, C.cutter(P.cyl(182, 500, 64), Sh @ R("Y", 90)), lip=lip)
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
    car = a.add("Shin_Armour_Carrier", A.hoops(secs, (-80, -190, -300), band=18.0),
                "Carbon ribs bonded inside the shin armour, carrying it off the shin member.", "cfrp", Sh, bevel=0.3,
                seg=1)
    open_shin(car, lip=None)
    posts = bmesh.new()
    for z in (-80, -190, -300):
        for x in (-28, 28):
            P.merge(posts, P.cyl(14, 46, 16), T(x, -56, z) @ R("X", 90))
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
        p0 = Sh @ Vector((o * 40, 86, -150))
        p1 = Ft @ Vector((o * 40, 104, -6))
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
               "clay", target=kc, dist=2.6)
    RV.closeup(knee, out / f"{a.aa}_knee_front_final{tag}.jpg", f"{a.aa} knee, front three-quarter", (s * 0.8, -0.75, 0.1),
               "final", target=kc, dist=2.6)
    RV.closeup(objs, out / f"{a.aa}_leg_rear_final{tag}.jpg", f"{a.aa} leg, rear three-quarter", (s * 0.7, 0.8, 0.15),
               "final", res=(1000, 1500), dist=3.0)
