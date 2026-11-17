"""Assembly 03: thorax.

A machined aluminium tub carries everything: the shoulder pitch actuators sit
in bores in its side walls, the armour stands off its front and flanks on
carriers, and the battery, compute and power distribution live inside it.

Body coordinates (before the torso offset): the tub's back plane is
y = THORAX_BACK_Y between z = 1292 and 1468, the top deck is z = 1492 with the
neck bore at (0, 4), and the shoulder pitch output faces are at x = +/-(SX - 77).
"""
import bmesh
from mathutils import Vector

from .. import frames as FR, params as PR
from ..lib import armour as A, core as C, detail as D, fittings as F, harness as H, mech, prims as P
from ..lib.core import T, R
from ..parts import Asm, raw

# tub sections: (z, width, front y, back y)
BACK = PR.THORAX_BACK_Y
SEC = [(1206, 258, -104, 99), (1292, 344, -152, BACK), (1400, 352, -158, BACK), (1468, 348, -154, BACK),
       (1492, 300, -130, 112)]
WALL = 8.0
CHAMFER = 0.16
PEC_FRONT = PR.CHEST_FRONT_Y            # outer face of the pectoral armour at its crown
ACT_X = PR.SX - 77 - 65                 # base plane of the shoulder pitch actuator (output face at SX - 77)
FLOOR_Z = 1206.0
WELL = (84.0, 58.0)                     # waist pitch actuators pass up through the floor here (+/-x, y)
BEAM_Z = 1306.0                         # underside of the reaction beam their forks bolt to
CONDUIT = (-20.0, 72.0)                 # floor entry of the conduit from the pelvis


def tub_at(z, grow=0.0):
    """Tub outline (csec) at height z, grown outward by `grow` mm."""
    for (z0, w0, f0, b0), (z1, w1, f1, b1) in zip(SEC, SEC[1:]):
        if z0 <= z <= z1:
            t = (z - z0) / (z1 - z0)
            w, f, b = w0 + (w1 - w0) * t, f0 + (f1 - f0) * t, b0 + (b1 - b0) * t
            return A.csec(z, w + 2 * grow, (b - f) + 2 * grow, 0, (b + f) / 2, CHAMFER)
    raise ValueError(z)


def _box_part(w, d, h, r=8.0):
    return P.prism(P.rrect(w, d, r, 4), 0.0, h)


def _with_connectors(bm, seats, d=14.0):
    """Merge circular connectors into a module body: slot 0 body, 1 shell, 2 boot."""
    for m in seats:
        c = H.connector_bm(d)
        for f in c.faces:
            f.material_index += 1
        P.merge(bm, c, m)
    return bm


def build():
    a = Asm("03")
    W = FR.torso()
    sx = PR.SX

    def cut(target, bm, m, lip=0.5):
        return C.boolean_cut(target, C.cutter(bm, W @ m), lip=lip)

    # ── tub: open-ended shell, top deck, floor, reaction beam for the waist actuators ──
    bm = A.shell([A.csec(z, w, b - f, 0, (b + f) / 2, CHAMFER) for z, w, f, b in SEC], WALL)
    P.merge(bm, P.prism([(p[0], p[1]) for p in tub_at(1492)], 1484, 1492))
    P.merge(bm, P.prism([(p[0], p[1]) for p in tub_at(FLOOR_Z)], FLOOR_Z, FLOOR_Z + 10))
    P.merge(bm, P.box(332, 34, 24), T(0, WELL[1], BEAM_Z + 12))
    fr = a.add("Thorax_Frame", bm,
               "Machined aluminium tub carrying the shoulder actuators, armour, battery and compute.", "alu", W,
               bevel=1.0)
    cut(fr, P.cyl(96, 40, 48), T(0, 4, 1488))                             # neck pass-through
    cut(fr, P.prism(P.rrect(184, 116, 12), -24, 24), T(0, 136, 1344) @ R("X", -90))   # plumbing to the backpack
    for s in (1, -1):
        cut(fr, P.cyl(179, 110, 64), T(s * (sx - 110), 0, PR.Z_SHOULDER) @ R("Y", 90))   # shoulder bore
        cut(fr, P.prism(P.rrect(112, 164, 10), -40, 40), T(s * 92, -158, 1380) @ R("X", 90))   # front access
        cut(fr, P.prism(P.rrect(46, 124, 8), -30, 30), T(s * 172, -22, 1304) @ R("Y", 90))     # flank intake
        cut(fr, P.cyl(62, 40, 32), T(s * WELL[0], WELL[1], FLOOR_Z + 5))  # wells for the waist pitch actuators
    cut(fr, P.cyl(40, 40, 24), T(CONDUIT[0], CONDUIT[1], FLOOR_Z + 5))    # conduit entry
    for s in (1, -1):                                                     # machined pockets on the back wall
        seat = D.seats_on(fr, [W @ Vector((s * 50, 260, 1440))], (0, 1, 0))
        if seat:
            D.pocket_grid(fr, seat[0], 1, 1, 34, 56, 0, 0, depth=4.0)

    bosses = bmesh.new()
    for x in (-104, 104):
        for z in (1300, 1432):
            P.merge(bosses, P.cyl(30, 6, 24), T(x, BACK - 1, z) @ R("X", 90))
    a.add("Backpack_Mount_Bosses", bosses, "Four threaded bosses on the back plane that the backpack bolts to.", "ti",
          W, bevel=0.5, seg=1)

    # ── shoulder pitch actuators and the yokes that cap them ────────────────
    for s in (1, -1):
        n = "L" if s > 0 else "R"
        d = mech.rotary_actuator("_sp", 176, 62, W @ T(s * ACT_X, 0, PR.Z_SHOULDER) @ R("Y", s * 90))
        a.take_rotary(d, f"Shoulder_Pitch_{n}", "shoulder pitch")
        arch = [(-88, 1492), (-88, 1506), (-58, 1530), (40, 1530), (62, 1512), (88, 1512), (88, 1492)]
        yk = raw(P.prism(arch, -19, 19), W @ T(s * 131, -2, 0) @ R("Z", 90) @ R("X", 90), "alu", 1.0)
        cut(yk, P.cyl(180, 120, 64), T(s * 131, 0, PR.Z_SHOULDER) @ R("Y", 90))
        a.take(yk, f"Shoulder_Yoke_{n}", "Arch bolted to the top deck, capping the shoulder pitch actuator in its bore.")
        pts = [W @ Vector((s * (131 + dx), y, 1600)) for y in (-80, 76) for dx in (-9, 9)]
        a.take(mech.fasteners("_yk", D.seats_on(yk, pts, (0, 0, 1), x_hint=(1, 0, 0)), "M6", target=yk),
               f"Shoulder_Yoke_Screws_{n}", "Screws fixing the shoulder yoke to the top deck.")
        a.add(f"Lifting_Eye_{n}", F.lifting_eye_bm(26), "Lifting eye on the shoulder yoke for hoisting the robot.", "ti",
              W @ T(s * 131, 74, 1512) @ R("Z", 90), bevel=0)

    # ── armour: sternum keel, two pectorals, two flanks, collar ─────────────
    px = sx - 30
    for s in (1, -1):
        n = "L" if s > 0 else "R"
        side = "left" if s > 0 else "right"
        out = P.chamfer_poly([(x * s, y) for x, y in ((52, 0), (px - 66, 0), (px, 66), (px, 206), (px - 38, 240),
                                                       (52, 240))], 9)
        Pm = W @ T(0, PEC_FRONT + 12 + 9, 1262) @ R("X", 90)
        cx = sum(p[0] for p in out) / len(out)
        cy = sum(p[1] for p in out) / len(out)
        ring = [[(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in out] for k in (0.90, 0.74)]
        tray = P.prism(out, 0.0, 12.0)                               # face plate plus a return lip round its edge
        P.merge(tray, P.ring_solid(out, [(cx + (x - cx) * 0.94, cy + (y - cy) * 0.95) for x, y in out], -9.0, 1.0))
        P.bend(tray, 0, 9.0, 10)
        pec = raw(tray, Pm, "armour", 1.2, 3)
        F.panel_cut(pec, [W @ Vector((s * (150 + 76 * k / 11), -205, 1494 - 90 * k / 11)) for k in range(12)], 1.5, 2.0)
        hw, hh, nf = (94, 68, 3) if s > 0 else (72, 56, 2)
        seat = D.seats_on(pec, [W @ Vector((s * 100, -230, 1352))], (0, -1, 0), x_hint=(1, 0, 0))[0]
        h = F.hatch("_ph", hw, hh, seat, target=pec, hinge_side="L" if s > 0 else "R", fasteners=nf)
        a.take(pec, f"Pectoral_Panel_{n}", "Pectoral armour panel covering the chest and the front of the shoulder joint.")
        what = "battery service disconnect" if s > 0 else "compute modules"
        a.take(h["door"], f"Chest_Hatch_{n}", f"Service hatch giving access to the {what}.")
        a.take(h["hinge"], f"Chest_Hatch_Hinge_{n}", f"Hinge of the {side} chest service hatch.")
        a.take(h["fasteners"], f"Chest_Hatch_Quarter_Turns_{n}",
               f"Quarter-turn fasteners latching the {side} chest service hatch.")
        a.add(f"Pectoral_Carrier_{n}", P.ring_solid(ring[0], ring[1], 0.0, 3.0),
              "Carbon carrier frame bonded behind the pectoral panel.", "cfrp", W @ T(0, -164, 1262) @ R("X", 90),
              bevel=0.3, seg=1)
        posts = bmesh.new()
        for x, z in ((62, 1284), (112, 1284), (62, 1470), (112, 1470)):
            P.merge(posts, P.cyl(12, 24, 12), T(s * x, -157, z) @ R("X", 90))
        a.add(f"Pectoral_Standoffs_{n}", posts, "Standoff posts fixing the pectoral carrier to the tub.", "alu", W,
              bevel=0.3, seg=1)
        pts = [W @ Vector((s * x, -230, z)) for x, z in ((62, 1278), (150, 1278), (216, 1340), (216, 1456), (184, 1488),
                                                         (62, 1488))]
        a.take(mech.fasteners("_pc", D.seats_on(pec, pts, (0, -1, 0)), "M6", target=pec), f"Pectoral_Screws_{n}",
               "Screws fixing the pectoral panel to its carrier.")

        fm = W @ T(s * 173.5, -22, 1300) @ R("Y", s * 90) @ R("Z", 90)
        fl = a.add(f"Flank_Panel_{n}", P.plate(P.chamfer_poly(P.rrect(190, 76), 12), 10),
                   "Flank armour panel carrying the side cooling intake.", "armour", fm, bevel=1.2, seg=3)
        v = F.vent("_fv", 112, 36, fm @ T(0, 0, 10), "mesh", depth=9.0, target=fl)
        a.take(v["bezel"], f"Flank_Intake_Bezel_{n}", "Bezel framing the flank cooling intake.")
        a.take(v["mesh"], f"Flank_Intake_Screen_{n}", "Mesh screen over the flank cooling intake.")
        a.take(v["back"], f"Flank_Intake_Duct_{n}", "Duct floor behind the flank intake, leading into the tub.")
        seats = [fm @ T(x, y, 10) for x in (-82, 82) for y in (-26, 26)]
        a.take(mech.fasteners("_fs", seats, "M6", target=fl), f"Flank_Screws_{n}",
               "Screws fixing the flank panel to the tub.")

    stern = P.chamfer_poly([(-38, 0), (38, 0), (44, 40), (44, 264), (-44, 264), (-44, 40)], [10, 10, 4, 8, 8, 4])
    st = a.add("Sternum_Panel", P.plate(stern, 20, crown=4, slices=6),
               "Sternum armour keel standing proud between the pectoral panels.", "armour",
               W @ T(0, PEC_FRONT - 1 + 20 + 4, 1238) @ R("X", 90), bevel=1.2, seg=3)
    pts = [W @ Vector((x, -240, z)) for x, z in ((-30, 1262), (30, 1262), (-32, 1486), (32, 1486))]
    a.take(mech.fasteners("_st", D.seats_on(st, pts, (0, -1, 0)), "M6", target=st), "Sternum_Screws",
           "Screws fixing the sternum panel to the tub.")
    seat = D.seats_on(st, [W @ Vector((0, -240, 1306))], (0, -1, 0), x_hint=(1, 0, 0))[0]
    A.recess(st, P.rrect(66, 42, 3), seat, depth=2.2)
    a.add("Data_Plate", P.prism(P.rrect(64, 40, 2.5, 3), -2.1, -0.5),
          "Blank metal data plate; designation, serial, mass and voltage are engraved on it.", "ti", seat, bevel=0.2,
          seg=1)
    a.take(mech.fasteners("_dp", [seat @ T(x, y, -0.5) for x in (-27, 27) for y in (-15, 15)], "M4", "csk"),
           "Data_Plate_Screws", "Countersunk screws holding the data plate.")

    collar = [(-108, 70), (-108, -62), (-70, -100), (70, -100), (108, -62), (108, 70), (86, 70), (86, -52),
              (60, -78), (-60, -78), (-86, -52), (-86, 70)]
    crest = [(-102, 70), (-102, -59), (-67, -94), (67, -94), (102, -59), (102, 70), (90, 70), (90, -54),
             (62, -82), (-62, -82), (-90, -54), (-90, 70)]
    co = a.add("Collar_Guard", P.loft([P.at_z(collar, 1492), P.at_z(collar, 1520), P.at_z(crest, 1540)]),
               "Raised guard protecting the front and sides of the neck mechanism.", "armour", W @ T(0, -12, 0),
               bevel=1.2, seg=3)
    seats = [W @ T(x, y - 12, 1540) for x, y in ((-96, 40), (96, 40), (-79, -71), (79, -71), (0, -88))]
    a.take(mech.fasteners("_co", seats, "M6", target=co), "Collar_Guard_Screws",
           "Screws fixing the collar guard to the top deck.")

    # ── inside the tub: battery, compute, power distribution, coolant manifold ──
    # the pack is stepped: a narrower foot follows the tapered floor of the tub
    by0, by1 = -138.0, 30.0
    by = (by0 + by1) / 2
    bb = P.prism(P.rrect(224, by1 - by0, 10, 4), 1292.0, 1408.0)
    bb.transform(T(0, by, 0))
    foot = P.prism(P.rrect(212, 138, 10, 4), 1250.0, 1296.0)
    P.merge(bb, foot, T(0, -43, 0))
    bat = a.add("Battery_Enclosure", bb,
                "Sealed enclosure of the 96 V lithium-ion pack with its internal cold plates.", "alu", W, bevel=1.0)
    D.pocket_grid(bat, W @ T(-36, by0, 1350) @ R("X", 90), 2, 2, 62, 44, 72, 52, depth=3.0)
    cover = P.prism(P.rrect(224, by1 - by0, 10, 4), 0.0, 6.0)
    for k in range(6):
        P.merge(cover, P.box(188, 8, 4), T(0, -65 + 26 * k, 7.5))
    a.add("Battery_Cover", cover, "Ribbed lid of the battery enclosure.", "alu", W @ T(0, by, 1408), bevel=0.5)
    a.take(mech.fasteners("_bc", [W @ T(x, by + y, 1414) for x in (-102, 0, 102) for y in (-76, 76)], "M4", "shcs",
                          washer=True), "Battery_Cover_Screws", "Screws sealing the battery lid.")
    bus = bmesh.new()
    for y in (by + 12, by - 12):
        P.merge(bus, P.box(76, 14, 5), T(62, y, 1420.5))
        for x in (30, 94):
            P.merge(bus, P.prism(P.rrect(24, 20, 4, 3), 0, 6.0), T(x, y, 1417.6), mat_index=1)
    a.add("Battery_Busbars", bus, "Insulated busbars carrying pack current to the power distribution unit.",
          ["alu", "rubber"], W, bevel=0.4, seg=1)
    dis = P.revolve([(0, 0), (24, 0), (24, 10), (20, 14), (0, 14)], 32)
    P.merge(dis, P.box(52, 12, 12), T(0, 0, 18), mat_index=1)
    a.add("Service_Disconnect", dis, "Manual service disconnect that isolates the battery for maintenance.",
          ["alu", "rubber"], W @ T(86, by0, 1352) @ R("X", 90), bevel=0.5)
    ports = bmesh.new()
    for x in (-58, 58):
        P.merge(ports, P.revolve([(7, 0), (13, 0), (13, 6), (10, 8), (10, 22), (11.5, 23), (11.5, 27), (7, 27)], 24),
                T(x, by1, 1386) @ R("X", -90))
    a.add("Battery_Coolant_Ports", ports, "Supply and return coolant ports of the battery cold plates.", "alu", W,
          bevel=0)
    for k, z in enumerate((1427, 1457)):
        body = P.prism(P.rrect(120, 104, 6, 3), 0.0, 20.0)
        _with_connectors(body, [T(x, -52, 10) @ R("X", 90) for x in (-36, -10)], 12.0)
        a.add(f"Compute_Module_{'AB'[k]}", body,
              f"Liquid-cooled compute module {'AB'[k]}; the pair run in redundancy.", ["alu", "fastener", "rubber"],
              W @ T(-56, -60, z), bevel=0.6)
        cp = P.prism(P.rrect(120, 104, 6, 3), 0.0, 7.0)
        for x in (-30, 30):
            P.merge(cp, P.cyl(6.4, 16, 12), T(x, 58, 3.5) @ R("X", -90))
        a.add(f"Compute_Cold_Plate_{'AB'[k]}", cp, f"Cold plate drawing heat out of compute module {'AB'[k]}.", "alu",
              W @ T(-56, -60, z - 8.5), bevel=0.4)
    pdu = P.prism(P.rrect(84, 96, 6, 3), 0.0, 52.0)
    for x in (-27, 0, 27):
        P.merge(pdu, P.box(3, 80, 5), T(x, 0, 54))
    _with_connectors(pdu, [T(x, -48, z) @ R("X", 90) for x, z in ((-22, 37), (22, 37), (0, 15))], 16.0)
    a.add("Power_Distribution_Unit", pdu, "Contactors, fuses and converters feeding every actuator bus.",
          ["alu", "fastener", "rubber"], W @ T(68, -58, 1424), bevel=0.6)
    man = P.box(170, 24, 26)
    for x in (-66, -22, 22, 66):
        P.merge(man, P.cyl(14, 22, 12), T(x, 0, -22))
    a.add("Coolant_Manifold", man, "Manifold splitting the coolant loop to battery, compute and shoulder actuators.",
          "alu", W @ T(0, 106, 1452), bevel=0.6)
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    RV.closeup(objs, out / f"03_thorax_front_final{tag}.jpg", "03 thorax, front three-quarter", (-0.55, -0.8, 0.25),
               "final", res=(1300, 1100), isolate=True, dist=3.0)
    armour = ("Pectoral", "Sternum", "Chest_Hatch", "Flank", "Collar", "Data_Plate")
    inner = [o for o in objs if not any(k in o.name for k in armour)]
    RV.closeup(inner, out / f"03_thorax_internals_clay{tag}.jpg", "03 thorax, armour removed", (0.5, -0.82, 0.3),
               "clay", res=(1300, 1100), isolate=True, dist=3.0)
