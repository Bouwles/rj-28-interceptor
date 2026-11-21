"""Assembly 03: thorax.

A machined aluminium tub carries everything: the shoulder pitch actuators sit
in bores in its side walls, the armour stands off its front and flanks on
carriers, and the battery, compute and power distribution live inside it.

The chest armour is two layers. The pectoral panels are the inner layer, 13 mm
behind the chest front. Over them, 3 mm clear, lie the sternum keel, a clavicle
plate across the top of each pectoral and a rib plate under it. Every plate is
faceted: it falls away towards the shoulder, towards the collar and towards the
waist, and the creases line up from plate to plate.

Body coordinates (before the torso offset): the tub's back plane is
y = THORAX_BACK_Y between z = 1292 and 1468, the top deck is z = 1492 with the
neck bore at (0, 4), and the shoulder pitch output faces are at x = +/-(SX - 77).
"""
import math

import bmesh
from mathutils import Matrix, Vector

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
PEC_FRONT = PR.CHEST_FRONT_Y            # outer face of the outer armour layer
ACT_X = PR.SX - 77 - 65                 # base plane of the shoulder pitch actuator (output face at SX - 77)
FLOOR_Z = 1206.0
WELL = (84.0, 58.0)                     # waist pitch actuators pass up through the floor here (+/-x, y)
BEAM_Z = 1306.0                         # underside of the reaction beam their forks bolt to
CONDUIT = (-20.0, 72.0)                 # floor entry of the conduit from the pelvis

# chest armour, drawn in (x, z) for the left side
XO = PR.SX - 34.0                       # outer edge of the chest armour
Y_PEC = PEC_FRONT + 13.0                # face of the pectoral panels (inner layer)
Y_OUT = PEC_FRONT                       # face of the clavicle and rib plates (outer layer)
Y_STERN = PEC_FRONT - 1.0               # the sternum keel stands 1 mm proud of them
T_PLATE, T_STERN = 10.0, 12.0
CREASE_X, CREASE_TOP, CREASE_LOW = 160.0, 1482.0, 1272.0     # where the facets break
SLOPE_X, SLOPE_TOP, SLOPE_LOW = 0.25, 0.70, 0.45             # how fast they fall away (mm per mm)
PEC = [(30, 1274), (166, 1274), (XO, 1334), (XO, 1419), (94, 1442), (30, 1402)]
CLAV = [(96.3, 1427), (XO, 1404), (XO, 1470), (XO - 30, 1500), (110.3, 1500)]
CLAV_BACK = [(101, 1444), (XO - 5, 1424), (XO - 5, 1468), (XO - 16, 1477), (108, 1477)]
RIB = [(42, 1289), (42, 1265), (34.5, 1244), (152, 1244), (197, 1289)]
STERN = [(32, 1240), (40, 1264), (40, 1392), (94, 1426), (108, 1500)]      # right half, bottom to top
YZ = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))      # profile drawn in (y, z), extruded along X


def tub_at(z, grow=0.0):
    """Tub outline (csec) at height z, grown outward by `grow` mm."""
    for (z0, w0, f0, b0), (z1, w1, f1, b1) in zip(SEC, SEC[1:]):
        if z0 <= z <= z1:
            t = (z - z0) / (z1 - z0)
            w, f, b = w0 + (w1 - w0) * t, f0 + (f1 - f0) * t, b0 + (b1 - b0) * t
            return A.csec(z, w + 2 * grow, (b - f) + 2 * grow, 0, (b + f) / 2, CHAMFER)
    raise ValueError(z)


def front_y(x, z, grow=0.0):
    """y of the tub's outer front surface at (x, z)."""
    pts = tub_at(z, grow)
    ys = [y0 + (y1 - y0) * (x - x0) / (x1 - x0)
          for (x0, y0, _), (x1, y1, _) in zip(pts, pts[1:] + pts[:1]) if x0 != x1 and (x0 - x) * (x1 - x) <= 0]
    return min(ys)


def _facet(bm, creases, w=3.0):
    """Facet a plate lying in XY (outer face +Z). Each crease is ((px, py), (nx, ny), slope): on the
    side of the line through p that n points to, the plate falls away at `slope`. The break is
    rounded over +/- w, and every facet stays planar, so thickness along Z is kept."""
    for (px, py), (nx, ny), _ in creases:
        n = Vector((nx, ny, 0.0)).normalized()
        for off in (-w, -w / 3, w / 3, w):
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5,
                                   plane_co=Vector((px, py, 0.0)) + n * off, plane_no=n)
    for v in bm.verts:
        dz = 0.0
        for (px, py), (nx, ny), k in creases:
            u = ((v.co.x - px) * nx + (v.co.y - py) * ny) / math.hypot(nx, ny)
            dz += k * (0.0 if u <= -w else u if u >= w else (u + w) ** 2 / (4 * w))
        v.co.z -= dz
    return bm


def _inset(poly, d):
    """Convex counter-clockwise polygon moved inward by d."""
    out = []
    for i in range(len(poly)):
        p0, p1, p2 = Vector(poly[i - 1]), Vector(poly[i]), Vector(poly[(i + 1) % len(poly)])
        e0, e1 = (p1 - p0).normalized(), (p2 - p1).normalized()
        a, b = p1 + Vector((-e0.y, e0.x)) * d, p1 + Vector((-e1.y, e1.x)) * d
        t = ((b - a).x * e1.y - (b - a).y * e1.x) / (e0.x * e1.y - e0.y * e1.x)
        out.append(tuple(a + e0 * t))
    return out


def _mx(pts, s):
    return [(x * s, z) for x, z in pts]


def _posts(spec, s, d=12.0):
    """Standoff posts running back along Y from (x, z, y) to the tub's front surface."""
    bm = bmesh.new()
    for x, z, y0 in spec:
        y1 = front_y(x, z) + 3.0
        P.merge(bm, P.cyl(d, y1 - y0, 16), T(s * x, (y0 + y1) / 2, z) @ R("X", 90))
    return bm


def _with_connectors(bm, seats, d=14.0):
    """Merge circular connectors into a module body: slot 0 body, 1 shell, 2 boot."""
    for m in seats:
        c = H.connector_bm(d)
        for f in c.faces:
            f.material_index += 1
        P.merge(bm, c, m)
    return bm


def _eared(w, d, h, ears, r=6.0):
    """Module body with mounting ears at (x, y): each takes a stud of the stack."""
    bm = P.prism(P.rrect(w, d, r, 3), 0.0, h)
    for x, y in ears:
        P.merge(bm, P.prism(P.rrect(14, 16, 3, 2), 0.0, min(h, 6.0)), T(x, y, 0))
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
    for s in (1, -1):                                                     # machined land round each front access port
        C.boolean_join(fr, C.cutter(P.prism(P.rrect(76, 176, 14, 4), -8, 9), W @ T(s * 86, -153, 1382) @ R("X", 90)),
                       lip=0.6)
    cut(fr, P.cyl(96, 40, 48), T(0, 4, 1488))                             # neck pass-through
    cut(fr, P.prism(P.rrect(184, 116, 12), -24, 24), T(0, 136, 1344) @ R("X", -90), lip=1.0)   # plumbing to the backpack
    for s in (1, -1):
        cut(fr, P.cyl(179, 110, 64), T(s * (sx - 110), 0, PR.Z_SHOULDER) @ R("Y", 90))   # shoulder bore
        cut(fr, P.prism(P.rrect(60, 160, 10), -40, 40), T(s * 86, -158, 1382) @ R("X", 90), lip=1.0)   # front access
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

    # ── armour: pectorals under a sternum keel, clavicle plates and rib plates ──
    def plate_m(yf, t):
        """Plates are drawn in (x, z); their outer face lands on y = yf."""
        return W @ T(0, yf + t, 0) @ R("X", 90)

    def seats(ob, pts, s=1):
        return D.seats_on(ob, [W @ Vector((s * x, -260, z)) for x, z in pts], (0, -1, 0))

    c_top = ((0, CREASE_TOP), (0, 1), SLOPE_TOP)                # towards the collar
    c_low = ((0, CREASE_LOW), (0, -1), SLOPE_LOW)               # towards the waist
    back_low = lambda z: Y_OUT + T_PLATE + SLOPE_LOW * (CREASE_LOW - z)      # back face of the rib plate's lower facet

    for s in (1, -1):
        n = "L" if s > 0 else "R"
        side = "left" if s > 0 else "right"
        c_out = ((s * CREASE_X, 0), (s, 0), SLOPE_X)            # towards the shoulder

        # pectoral: inner layer, with the service hatch
        pec = raw(_facet(P.prism(P.chamfer_poly(_mx(PEC, s), 6), 0.0, T_PLATE), [c_out]), plate_m(Y_PEC, T_PLATE),
                  "armour", 1.2, 3)
        hw, hh, hx = (84, 64, 94) if s > 0 else (72, 56, 96)
        seat = D.seats_on(pec, [W @ Vector((s * hx, -260, 1346))], (0, -1, 0), x_hint=(1, 0, 0))[0]
        h = F.hatch("_ph", hw, hh, seat, target=pec, hinge_side="R" if s > 0 else "L", fasteners=3 if s > 0 else 2)
        a.take(pec, f"Pectoral_Panel_{n}", "Pectoral armour panel covering the chest and the front of the shoulder joint.")
        what = "battery service disconnect" if s > 0 else "compute modules"
        a.take(h["door"], f"Chest_Hatch_{n}", f"Service hatch giving access to the {what}.")
        a.take(h["hinge"], f"Chest_Hatch_Hinge_{n}", f"Hinge of the {side} chest service hatch.")
        a.take(h["fasteners"], f"Chest_Hatch_Quarter_Turns_{n}",
               f"Quarter-turn fasteners latching the {side} chest service hatch.")
        car = P.ring_solid(P.chamfer_poly(_mx(_inset(PEC, 4), s), 4), P.chamfer_poly(_mx(_inset(PEC, 30), s), 4),
                           -3.0, 0.0)
        P.merge(car, P.box(15, 114, 2.6), T(s * 147.5, 1353, -1.5))            # stile taking the outer standoff
        a.add(f"Pectoral_Carrier_{n}", _facet(car, [c_out]), "Carbon carrier frame bonded behind the pectoral panel.",
              "cfrp", plate_m(Y_PEC, T_PLATE), bevel=0.3, seg=1)
        y0 = Y_PEC + T_PLATE + 3.0
        a.add(f"Pectoral_Standoffs_{n}", _posts([(42, 1296, y0), (42, 1392, y0), (112, 1287, y0), (150, 1380, y0)], s),
              "Standoff posts fixing the pectoral carrier to the tub.", "alu", W, bevel=0.3, seg=1)
        pts = ((54, 1298), (150, 1298), (212, 1345), (212, 1394), (120, 1412), (50, 1392))
        a.take(mech.fasteners("_pc", seats(pec, pts, s), "M6", target=pec), f"Pectoral_Screws_{n}",
               "Screws fixing the pectoral panel to its carrier.")

        # clavicle plate: outer layer across the top of the pectoral
        cl = a.add(f"Clavicle_Plate_{n}", _facet(P.prism(P.chamfer_poly(_mx(CLAV, s), 5), 0.0, T_PLATE), [c_out, c_top]),
                   f"Strike plate over the {side} collar bone, lapping 15 mm over the pectoral panel.", "armour",
                   plate_m(Y_OUT, T_PLATE), bevel=1.2, seg=3)
        a.add(f"Clavicle_Carrier_{n}", _facet(P.prism(P.chamfer_poly(_mx(CLAV_BACK, s), 4), -3.0, 0.0), [c_out]),
              "Carbon backing plate bonded behind the clavicle plate.", "cfrp", plate_m(Y_OUT, T_PLATE), bevel=0.3,
              seg=1)
        y0 = Y_OUT + T_PLATE + 3.0
        a.add(f"Clavicle_Standoffs_{n}", _posts([(112, 1464, y0), (150, 1462, y0)], s),
              "Standoff posts fixing the clavicle carrier to the tub.", "alu", W, bevel=0.3, seg=1)
        a.take(mech.fasteners("_cv", seats(cl, ((122, 1462), (186, 1468), (208, 1440)), s), "M6", target=cl),
               f"Clavicle_Screws_{n}", "Screws fixing the clavicle plate to its carrier.")

        # rib plate: outer layer under the pectoral, folding back towards the waist
        rb = a.add(f"Rib_Plate_{n}", _facet(P.prism(P.chamfer_poly(_mx(RIB, s), [5, 3, 5, 5, 6]), 0.0, T_PLATE),
                                            [c_out, c_low]),
                   f"Rib plate lapping the lower edge of the {side} pectoral and shielding the waist bellows.", "armour",
                   plate_m(Y_OUT, T_PLATE), bevel=1.2, seg=3)
        rail = [(back_low(1252), 1252), (back_low(1268), 1268), (back_low(1268) + 10, 1268), (back_low(1252) + 10, 1252)]
        bm = P.prism(rail, min(s * 52, s * 158), max(s * 52, s * 158))
        bm.transform(YZ)
        P.merge(bm, _posts([(66, 1262, back_low(1262) + 9), (98, 1262, back_low(1262) + 9)], s, 10.0))
        a.add(f"Rib_Plate_Rail_{n}", bm, "Rail behind the rib plate, on two posts from the tub.", "alu", W, bevel=0.4,
              seg=1)
        a.take(mech.fasteners("_rb", seats(rb, ((66, 1259), (112, 1259), (150, 1259)), s), "M6", target=rb),
               f"Rib_Plate_Screws_{n}", "Screws fixing the rib plate to its rail.")

        fm = W @ T(s * 173.5, -22, 1300) @ R("Y", s * 90) @ R("Z", 90)
        fl = a.add(f"Flank_Panel_{n}", P.plate(P.chamfer_poly(P.rrect(190, 76), 12), 10),
                   "Flank armour panel carrying the side cooling intake.", "armour", fm, bevel=1.2, seg=3)
        v = F.vent("_fv", 112, 36, fm @ T(0, 0, 10), "mesh", depth=9.0, target=fl)
        a.take(v["bezel"], f"Flank_Intake_Bezel_{n}", "Bezel framing the flank cooling intake.")
        a.take(v["mesh"], f"Flank_Intake_Screen_{n}", "Mesh screen over the flank cooling intake.")
        a.take(v["back"], f"Flank_Intake_Duct_{n}", "Duct floor behind the flank intake, leading into the tub.")
        fs = [fm @ T(x, y, 10) for x in (-82, 82) for y in (-26, 26)]
        a.take(mech.fasteners("_fs", fs, "M6", target=fl), f"Flank_Screws_{n}",
               "Screws fixing the flank panel to the tub.")

    # sternum: a keel between the pectorals that widens into a head plate under the collar
    stern = P.chamfer_poly(P.mirror_x(STERN), [6, 3, 8, 5, 10, 10, 5, 8, 3, 6])
    st = a.add("Sternum_Panel", _facet(P.prism(stern, 0.0, T_STERN), [c_top, c_low]),
               "Sternum armour keel standing proud between the pectoral panels.", "armour", plate_m(Y_STERN, T_STERN),
               bevel=1.2, seg=3)
    yb = Y_STERN + T_STERN
    spine = P.prism([(yb, 1275), (yb, 1478), (-150, 1478), (-150, 1300), (-160, 1250), (yb + 10.2, 1250)], -16, 16)
    spine.transform(YZ)
    P.merge(spine, P.box(196, 12, 14), T(0, yb + 6, 1469))
    a.add("Sternum_Carrier", spine, "Machined spine and crossbar carrying the sternum panel off the front of the tub.",
          "alu", W, bevel=0.6)
    pts = ((0, 1258), (0, 1352), (0, 1418), (-90, 1469), (90, 1469))
    a.take(mech.fasteners("_st", seats(st, pts), "M6", target=st), "Sternum_Screws",
           "Screws fixing the sternum panel to its carrier.")
    seat = D.seats_on(st, [W @ Vector((0, -260, 1306))], (0, -1, 0), x_hint=(1, 0, 0))[0]
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
    cs = [W @ T(x, y - 12, 1540) for x, y in ((-96, 40), (96, 40), (-79, -71), (79, -71), (0, -88))]
    a.take(mech.fasteners("_co", cs, "M6", target=co), "Collar_Guard_Screws",
           "Screws fixing the collar guard to the top deck.")

    # ── inside the tub: battery, compute, power distribution, coolant manifold ──
    # The pack is sized by the energy it has to hold and shaped by what it has to miss. Side profile
    # (y, z), one extrusion 230 mm wide: a foot down to the tapered floor, the main block, a saddle that
    # steps over the waist reaction beam, and a rear tower up to the deck behind the compute stack.
    # Low wings fill the tub below the shoulder actuators. About 8.4 litres; the first version was 5.7.
    # Everything added to it since is cut into the casting or bolted on: the envelope has not moved.
    by0, by1, lid_y1 = -138.0, 100.0, 56.0
    by = (by0 + lid_y1) / 2
    lid_z = 1410.0
    prof = [(by0, 1288), (-112, 1288), (-112, 1246), (26, 1246), (26, 1288), (30, 1288), (30, BEAM_Z + 30),
            (by1, BEAM_Z + 30), (by1, 1478), (lid_y1, 1478), (lid_y1, lid_z), (by0, lid_z)]
    bb = P.prism(prof, -115.0, 115.0)
    bb.transform(YZ)
    bat = a.add("Battery_Enclosure", bb,
                "Sealed enclosure of the 96 V lithium-ion pack with its internal cold plates.", "alu", W, bevel=1.0)
    for s in (1, -1):                                                     # wings stop short of the tub's corner chamfers
        C.boolean_join(bat, C.cutter(P.box(43, 134, 47), W @ T(s * 126.5, -37, 1312.5)), lip=0.5)
    D.pocket_grid(bat, W @ T(-36, by0, 1350) @ R("X", 90), 2, 2, 62, 44, 72, 52, depth=3.0)
    # shallow panels machined into the other big faces leave stiffening ribs standing between them; they are
    # kept to 1.5 mm so the enclosure still measures 8.3 litres
    D.pocket_grid(bat, W @ T(0, by1, 1376) @ R("X", -90), 1, 1, 60, 46, 0, 0, depth=1.5)
    D.pocket_grid(bat, W @ T(0, -112, 1267) @ R("X", 90), 3, 1, 58, 24, 70, 0, depth=1.5)
    for s in (1, -1):
        D.pocket_grid(bat, W @ T(s * 115, -41, 1374) @ R("Y", s * 90), 1, 2, 44, 72, 0, 88, depth=1.5)
        D.pocket_grid(bat, W @ T(s * 115, 78, 1420) @ R("Y", s * 90), 1, 1, 84, 26, 0, 0, depth=1.5)
        D.pocket_grid(bat, W @ T(s * 148, -37, 1312.5) @ R("Y", s * 90), 1, 1, 26, 104, 0, 0, depth=1.5)

    feet, fs = bmesh.new(), []
    for x, y in ((62, -78), (-62, -78), (72, 6), (-72, 6)):               # pedestals under the foot of the pack
        P.merge(feet, P.prism(P.chamfer_poly(P.rrect(52, 24), 4), 0.0, 6.0), T(x, y, FLOOR_Z + 10))
        P.merge(feet, P.prism(P.rrect(22, 22, 4, 3), 6.0, 1246 - FLOOR_Z - 10), T(x, y, FLOOR_Z + 10))
        fs += [W @ T(x + dx, y, FLOOR_Z + 16) for dx in (-19, 19)]
    a.add("Battery_Mount_Feet", feet, "Pedestals carrying the foot of the battery enclosure on the tub floor.", "alu", W,
          bevel=0.5)
    a.take(mech.fasteners("_bf", fs, "M6", washer=True), "Battery_Mount_Bolts",
           "Bolts fixing the battery pedestals to the tub floor.")
    pads = bmesh.new()
    for x in (-38, 38):
        P.merge(pads, P.prism(P.rrect(44, 30, 4, 3), 0.0, 6.0), T(x, WELL[1], BEAM_Z + 24))
    a.add("Battery_Saddle_Isolators", pads, "Rubber isolators between the pack's saddle and the waist reaction beam.",
          "rubber", W, bevel=0.5, seg=1)

    lid_d = lid_y1 - by0
    cover = P.prism(P.rrect(230, lid_d, 6, 3), 0.0, 5.0)
    for k in range(7):
        P.merge(cover, P.box(190, 8, 3), T(0, -78 + 26 * k, 6.0))
    a.add("Battery_Cover", cover, "Ribbed lid of the battery enclosure, bolted down on its flange.", "alu",
          W @ T(0, by, lid_z), bevel=0.5)
    a.add("Battery_Lid_Seal", P.ring_solid(P.rrect(231.6, lid_d + 1.6, 6.8, 3), P.rrect(220, lid_d - 10, 3, 3), -0.6, 0.6),
          "Gasket sealing the battery lid to the enclosure flange.", "rubber", W @ T(0, by, lid_z), bevel=0)
    ls = [(x, y) for x in (-106, -53, 0, 53, 106) for y in (-91, 91)] + [(x, y) for x in (-106, 106) for y in (-30, 30)]
    ls.remove((53, -91))                                                  # the HV connector sits here
    a.take(mech.fasteners("_bc", [W @ T(x, by + y, lid_z + 5) for x, y in ls], "M4", "shcs", washer=True),
           "Battery_Cover_Screws", "Screws clamping the battery lid and its gasket to the flange.")

    # pack output: HV connector on the lid in front of the power distribution unit, busbars back under it
    px, py, pz = 68.0, -58.0, lid_z + 14.0                                # PDU centre and base
    hv = P.prism(P.chamfer_poly(P.rrect(52, 20), 3), 0.0, 3.0)
    P.merge(hv, P.prism(P.rrect(36, 20, 3, 3), 3.0, 9.5))
    for x in (-9, 9):
        P.merge(hv, P.revolve([(0, 9.5), (5.5, 9.5), (5.5, 11.5), (4.5, 12.5), (0, 12.5)], 20), T(x, 0, 0), mat_index=1)
    a.add("Battery_HV_Connector", hv, "High-voltage outlet of the pack: both poles leave the lid here.",
          ["alu", "rubber"], W @ T(px, by0 + 12, lid_z + 5), bevel=0.4, seg=1)
    a.take(mech.fasteners("_hv", [W @ T(px + x, by0 + 12, lid_z + 8) for x in (-21, 21)], "M4"),
           "Battery_HV_Connector_Screws", "Screws fixing the HV connector to the battery lid.")
    bus = bmesh.new()
    for x in (px - 9, px + 9):
        P.merge(bus, P.prism(P.rrect(12, 44, 3, 3), 3.0, 6.0), T(x, -94, lid_z + 5))
        P.merge(bus, P.prism(P.rrect(13.6, 20, 3, 3), 2.4, 6.6), T(x, -97, lid_z + 5), mat_index=1)
        P.merge(bus, P.prism(P.rrect(16, 16, 3, 3), 0.0, pz - lid_z - 5), T(x, -80, lid_z + 5), mat_index=1)
        P.merge(bus, mech.screw_bm("M4", "shcs", washer=True), T(x, -111, lid_z + 11), mat_index=2)
    a.add("Battery_Busbars", bus, "Insulated busbars carrying pack current from the HV connector to the power distribution unit.",
          ["alu", "rubber", "fastener"], W, bevel=0.4, seg=1)
    dis = P.revolve([(0, 0), (24, 0), (24, 10), (20, 14), (0, 14)], 32)
    P.merge(dis, P.box(52, 12, 12), T(0, 0, 18), mat_index=1)
    a.add("Service_Disconnect", dis, "Manual service disconnect that isolates the battery for maintenance.",
          ["alu", "rubber"], W @ T(86, by0, 1352) @ R("X", 90), bevel=0.5)
    vent = P.revolve([(0, 0), (11, 0), (11, 2.5), (9, 3.5), (9, 5), (10, 5.5), (10, 7), (9, 7.5), (9, 8.5), (7, 10),
                      (0, 10)], 24)
    a.add("Battery_Breather_Valve", vent, "Breather valve equalising pressure in the sealed pack and venting it in a fault.",
          "alu", W @ T(86, by0, 1392) @ R("X", 90), bevel=0)
    ports = bmesh.new()
    for x in (-58, 58):
        P.merge(ports, P.revolve([(7, 0), (13, 0), (13, 6), (10, 8), (10, 22), (11.5, 23), (11.5, 27), (7, 27)], 24),
                T(x, by1, 1386) @ R("X", -90))
    a.add("Battery_Coolant_Ports", ports, "Supply and return coolant ports of the battery cold plates.", "alu", W,
          bevel=0)

    # compute: two modules and their cold plates clamped into one stack on four studs from the battery lid
    cx, cy = -56.0, -60.0
    ears = [(-54, -58), (34, -58), (-46, 58), (46, 58)]
    for k, z in enumerate((lid_z + 17, lid_z + 47)):
        body = _eared(120, 104, 20.0, ears)
        P.merge(body, P.prism(P.rrect(106, 90, 4, 3), 20.0, 21.2))                         # screwed lid
        for x, y in ((-46, -38), (46, -38), (-46, 38), (46, 38)):
            P.merge(body, mech.screw_bm("M4", "csk"), T(x, y, 21.2), mat_index=1)
        _with_connectors(body, [T(x, -52, 10) @ R("X", 90) for x in (-36, -10)], 12.0)
        a.add(f"Compute_Module_{'AB'[k]}", body,
              f"Liquid-cooled compute module {'AB'[k]}; the pair run in redundancy.", ["alu", "fastener", "rubber"],
              W @ T(cx, cy, z), bevel=0.6)
        cp = _eared(120, 104, 7.0, ears)
        for x in (-30, 30):
            P.merge(cp, P.cyl(6.4, 16, 12), T(x, 58, 3.5) @ R("X", -90))
        a.add(f"Compute_Cold_Plate_{'AB'[k]}", cp, f"Cold plate drawing heat out of compute module {'AB'[k]}.", "alu",
              W @ T(cx, cy, z - 7.0), bevel=0.4)
    studs = bmesh.new()
    for x, y in ears:
        P.merge(studs, P.cyl(11, 5, 16), T(cx + x, cy + y, lid_z + 7.5))                   # foot spacer on the lid
        P.merge(studs, P.cyl(9, 17, 16), T(cx + x, cy + y, lid_z + 31.5))                  # sleeve between the modules
        P.merge(studs, P.cyl(5, 53, 12), T(cx + x, cy + y, lid_z + 31.5), mat_index=1)     # the stud itself
        P.merge(studs, P.cyl(11, 1, 16), T(cx + x, cy + y, lid_z + 53.5), mat_index=1)
        P.merge(studs, P.cyl(9.2, 4, 6), T(cx + x, cy + y, lid_z + 56), mat_index=1)       # nut
    a.add("Compute_Stack_Studs", studs, "Four studs with spacers clamping the compute stack to the battery lid.",
          ["alu", "fastener"], W, bevel=0.3, seg=1)

    pe = [(x, y) for x in (-30, 30) for y in (-55, 55)]
    pdu = P.prism(P.rrect(84, 96, 6, 3), 0.0, 52.0)
    for x, y in pe:
        P.merge(pdu, P.prism(P.rrect(16, 18, 3, 2), 0.0, 4.0), T(x, y, 0))
    for x in (-27, 0, 27):
        P.merge(pdu, P.box(3, 80, 5), T(x, 0, 54))
    _with_connectors(pdu, [T(x, -48, z) @ R("X", 90) for x, z in ((-22, 37), (22, 37), (0, 15))], 16.0)
    a.add("Power_Distribution_Unit", pdu, "Contactors, fuses and converters feeding every actuator bus.",
          ["alu", "fastener", "rubber"], W @ T(px, py, pz), bevel=0.6)
    so = bmesh.new()
    for x, y in pe:
        P.merge(so, P.cyl(10, pz - lid_z - 5, 6), T(px + x, py + y, (pz + lid_z + 5) / 2))
    a.add("Power_Distribution_Standoffs", so, "Hex standoffs carrying the power distribution unit on the battery lid.",
          "alu", W, bevel=0.3, seg=1)
    a.take(mech.fasteners("_pd", [W @ T(px + x, py + y, pz + 4) for x, y in pe], "M4", washer=True),
           "Power_Distribution_Screws", "Screws fixing the power distribution unit to its standoffs.")

    man = P.prism(P.chamfer_poly(P.rrect(170, 24), 5), -13.0, 13.0)
    barb = [(0, 0), (7, 0), (7, 10), (8.2, 11), (8.2, 13), (7, 15), (8.2, 16), (8.2, 18), (6.2, 22), (0, 22)]
    for x in (-66, -22, 22, 66):
        P.merge(man, P.revolve(barb, 16), T(x, 0, -13) @ R("X", 180))
    for o in (1, -1):
        P.merge(man, P.cyl(17, 5, 6), T(o * 87.5, 0, 0) @ R("Y", 90))                      # end plugs
    a.add("Coolant_Manifold", man, "Manifold splitting the coolant loop to battery, compute and shoulder actuators.",
          "alu", W @ T(0, 117, 1452), bevel=0.6)
    brk = bmesh.new()
    for x in (-60, 60):                                                   # angle brackets: over the top, down the back wall
        P.merge(brk, P.box(26, 26, 3), T(x, 119.5, 1466.5))
        P.merge(brk, P.box(26, 3.5, 21), T(x, 130.75, 1457.5))
    a.add("Coolant_Manifold_Brackets", brk, "Angle brackets hanging the coolant manifold on the tub's back wall.", "alu",
          W, bevel=0.4, seg=1)
    a.take(mech.fasteners("_cm", [W @ T(x, 116, 1468) for x in (-60, 60)], "M4", washer=True),
           "Coolant_Manifold_Screws", "Screws fixing the manifold brackets to the manifold.")
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    RV.closeup(objs, out / f"03_thorax_front_final{tag}.jpg", "03 thorax, front three-quarter", (-0.55, -0.8, 0.25),
               "final", res=(1300, 1100), isolate=True, dist=3.0)
    RV.closeup(objs, out / f"03_thorax_front_clay{tag}.jpg", "03 thorax, front, from below the left shoulder",
               (0.42, -0.9, -0.12), "clay", res=(1300, 1100), isolate=True, dist=3.0)
    armour = ("Pectoral_Panel", "Pectoral_Screws", "Sternum_Panel", "Sternum_Screws", "Chest_Hatch", "Flank", "Collar",
              "Data_Plate", "Clavicle_Plate", "Clavicle_Screws", "Rib_Plate_L", "Rib_Plate_R", "Rib_Plate_Screws")
    inner = [o for o in objs if not any(k in o.name for k in armour)]
    RV.closeup(inner, out / f"03_thorax_internals_clay{tag}.jpg", "03 thorax, armour removed", (0.5, -0.82, 0.3),
               "clay", res=(1300, 1100), isolate=True, dist=3.0)
    bare = [o for o in inner if "Thorax_Frame" not in o.name and "Shoulder" not in o.name and "Lifting" not in o.name
            and "Backpack" not in o.name and not any(k in o.name for k in ("Carrier", "Standoffs", "Rail"))]
    RV.closeup(bare, out / f"03_thorax_pack_clay{tag}.jpg", "03 thorax, battery and compute out of the tub",
               (0.6, 0.7, 0.4), "clay", res=(1300, 1100), isolate=True, dist=3.0)
    RV.closeup(bare, out / f"03_thorax_pack_front_clay{tag}.jpg", "03 thorax, battery and compute from the front",
               (-0.5, -0.7, 0.5), "clay", res=(1300, 1100), isolate=True, dist=3.0)
