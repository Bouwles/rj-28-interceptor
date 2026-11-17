"""Assembly 06: backpack.

The cooling plant of the robot: two radiator cores behind slatted grilles,
two axial blowers, the coolant reservoir, pump and manifold, in an armoured
shell on a frame bolted to the thorax back plane. It also carries the pad the
mount hardpoint bolts through (the hardpoint and travel lock are assembly 15).

Built in body coordinates and placed with the torso offset. Rear-face fittings
use a frame whose +Z points out of the rear face (+Y), +X is the robot's left
and +Y points down.
"""
import bmesh
import bpy
from mathutils import Matrix, Vector

from .. import frames as FR, params as PR
from ..lib import armour as A, core as C, detail as D, fittings as F, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm, raw
from . import mount as MT

XZ = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))      # outline drawn in (x, z), extruded along +Y
YZ = Matrix(((0, 0, -1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))     # outline drawn in (y, z), extruded along -X

BLOWER_Z, RAD_Z = 1388.0, 1262.0
REAR_Z0, REAR_Z1 = 50.0, 28.0          # the rear face stops this far above the bottom / below the top (edge chamfers)


def _centre(ob):
    lo, hi = C.bounds_mm([ob])
    return (lo + hi) / 2


def _biggest(objs, n):
    return sorted(objs, key=lambda o: -len(o.data.vertices))[:n]


def _drop(ob):
    me = ob.data
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)


def _ring(w, h, zc, y, r=16.0):
    return [(x, y, z + zc) for x, z in P.rrect(w, h, r)]


def _latches(e, ys):
    """Over-centre latches for a door whose latch edge is at local x = +e (door surface z = 0):
    keeper on the panel, lever on the door, wire bail between them."""
    bm = bmesh.new()
    for y in ys:
        P.merge(bm, P.box(8, 16, 5), T(e + 8.0, y, 2.5))
        P.merge(bm, P.prism(P.chamfer_poly(P.rrect(26, 12), [0, 3, 3, 0]), 0, 3), T(e - 13.5, y, 0))
        for o in (1, -1):
            P.merge(bm, P.box(22, 1.6, 1.6), T(e - 0.5, y + o * 5.4, 4.0))
        P.merge(bm, P.box(1.6, 12.4, 1.6), T(e + 9.7, y, 4.0))
    return bm


def build():
    a = Asm("06")
    W = FR.torso()
    y0, y1 = PR.THORAX_BACK_Y + 2.0, PR.PACK_BACK_Y              # body coords: front plane, rear face
    yc, d = (y0 + y1) / 2, y1 - y0
    hw = PR.PACK_HALF_W
    w = hw * 2
    z0, z1 = PR.PACK_Z0, PR.PACK_Z1
    zc, H = (z0 + z1) / 2, z1 - z0
    up, back = Vector((0, 0, 1)), Vector((0, 1, 0))
    rz0, rz1 = z0 + REAR_Z0, z1 - REAR_Z1                        # flat rear face

    def rear(x, z):
        """Frame on the rear face at (x, z): +Z out of the face, +X left, +Y down."""
        return W @ T(x, y1, z) @ R("X", -90)

    # ── frame: backplate on the thorax, posts, stiles, radiator rails, reservoir bracket ──
    plate = [(x, z + zc) for x, z in P.chamfer_poly(P.rrect(w - 30, H - 26), 14)]
    bm = P.prism(plate, y0, y0 + 8)
    bm.transform(XZ)
    pieces = [bm]

    def piece(sx_, sy_, sz_, x, y, z):
        b = P.box(sx_, sy_, sz_)
        b.transform(T(x, y, z))
        pieces.append(b)

    for sx in (1, -1):
        for z in (z0 + 40, z1 - 44):
            piece(14, d - 22, 14, sx * (hw - 26), yc - 2, z)                            # corner posts
        piece(14.02, 14, H - 70, sx * (hw - 26), y1 - 62, zc - 2)                       # rear stiles
        for z in (RAD_Z - 36, RAD_Z + 36):
            piece(112, 8, 10, sx * 87, y1 - 62, z)                                      # radiator rails
        piece(6, y1 - 66 - (y0 + 6), 18, sx * 19, (y1 - 66 + y0 + 6) / 2, 1315)         # reservoir bracket arms
    piece(44, 60, 4, 0, y1 - 40, 1322)
    fr = raw(pieces[0], W, "alu", 0.8)
    for b in pieces[1:]:
        C.boolean_join(fr, C.cutter(b, W), lip=0.5)
    a.take(fr, "Backpack_Frame",
           "Backpack frame: backplate bolted to the thorax, posts, radiator rails and reservoir bracket.")
    D.pocket_grid(fr, W @ T(0, y0 + 8, zc) @ R("X", -90), 3, 3, 64, 62, 92, 92, depth=4.5)
    C.boolean_cut(fr, C.cutter(P.cyl(17.5, 20), W @ T(0, y1 - 50, 1322)), lip=0.3)                 # reservoir outlet passes the bracket
    seats = [W @ frame((sx * (hw - 44), y0 + 8, z), (0, 1, 0), (1, 0, 0)) for sx in (1, -1) for z in (z0 + 70, z1 - 74)]
    a.take(mech.fasteners("_tb", seats, "M10", washer=True), "Backpack_Mounting_Bolts",
           "Bolts fixing the backpack frame to the thorax back plane.")

    # ── armour shell: one tub open towards the thorax, split into five panels ──
    secs = [_ring(w, H, zc, y0 + 12), _ring(w, H, zc, y1 - 20), _ring(w - 6, rz1 - rz0, (rz0 + rz1) / 2, y1)]
    tub = P.loft(secs, cap=True)
    bmesh.ops.delete(tub, geom=[f for f in tub.faces if all(abs(v.co.y - (y0 + 12)) < 1e-6 for v in f.verts)],
                     context="FACES_ONLY")
    sh = raw(P.thicken(tub, 10.0), W, "armour", 1.2, 3)
    A.gap_cut(sh, W @ Vector((0, y1 - 28, zc)), back)
    lid, ring = sorted(_biggest(A.islands(sh), 2), key=lambda o: -_centre(o).y)
    A.gap_cut(ring, W @ Vector((0, yc, z1 - 40)), up)
    A.gap_cut(ring, W @ Vector((0, yc, z0 + 40)), up)
    pcs = _biggest(A.islands(ring), 4)
    top = max(pcs, key=lambda o: _centre(o).z)
    bot = min(pcs, key=lambda o: _centre(o).z)
    side_r, side_l = sorted([o for o in pcs if o not in (top, bot)], key=lambda o: _centre(o).x)

    # openings in the rear panel
    for sx in (1, -1):
        A.opening(lid, P.circle(113.0, 48), rear(sx * 80, BLOWER_Z), depth=20, above=10)
    A.opening(lid, P.rrect(18, 72, 8), rear(0, BLOWER_Z), depth=20, above=10)
    vents = {}
    for sx, tag in ((1, "Left"), (-1, "Right")):
        v = F.vent("_rv", 100, 92, rear(sx * 80, RAD_Z), "slats", count=9, depth=22.0, target=lid)
        _drop(v.pop("back"))                                       # the radiator core is what shows behind the louvres
        vents[tag] = v
    F.panel_cut(lid, [W @ Vector((x, y1 + 4, 1322.5)) for x in range(-136, 137, 8)], 1.5, 2.0)
    a.take(lid, "Backpack_Rear_Panel", "Rear armour panel carrying the blower outlets, radiator grilles and sight glass.")
    a.take(top, "Backpack_Top_Panel", "Top armour panel of the backpack.")
    a.take(bot, "Backpack_Bottom_Panel", "Bottom armour panel of the backpack.")
    a.take(side_l, "Backpack_Side_Panel_Left", "Left armour side panel, with the battery service door.")
    a.take(side_r, "Backpack_Side_Panel_Right", "Right armour side panel, reinforced where the mount hardpoint bolts on.")
    ribs = bmesh.new()
    for y in (y0 + 44, y1 - 56):
        P.merge(ribs, D.rib_ring_bm([_ring(w, H, zc, y - 9), _ring(w, H, zc, y + 9)], 3.0, 10.6))
    a.add("Backpack_Shell_Carrier", ribs, "Carbon ribs bonded inside the backpack shell, carrying it off the frame.", "cfrp",
          W, bevel=0.3, seg=1)

    # panel screws
    pts = [W @ Vector((x, y1 + 40, z)) for x, z in ((142, 1318), (-142, 1318), (142, 1212), (-142, 1212), (30, 1440),
                                                     (-30, 1440), (0, 1214))]
    a.take(mech.fasteners("_rs", D.seats_on(lid, pts, back, x_hint=(1, 0, 0)), "M6", target=lid), "Rear_Panel_Screws",
           "Screws fixing the rear panel to the backpack frame.")
    pts = [W @ Vector((sx * 108, yc - 8 + sy * 30, z1 + 40)) for sx in (1, -1) for sy in (1, -1)]
    a.take(mech.fasteners("_ts", D.seats_on(top, pts, up, x_hint=(1, 0, 0)), "M6", target=top), "Top_Panel_Screws",
           "Screws fixing the top panel to the backpack frame.")
    pts = [W @ Vector((sx * 100, yc - 8 + sy * 24, z0 - 40)) for sx in (1, -1) for sy in (1, -1)]
    a.take(mech.fasteners("_bs", D.seats_on(bot, pts, -up, x_hint=(1, 0, 0)), "M6", target=bot), "Bottom_Panel_Screws",
           "Screws fixing the bottom panel to the backpack frame.")
    for ob, sx, zs, tag in ((side_l, 1, 1410, "Left"), (side_r, -1, 1372, "Right")):
        pts = [W @ Vector((sx * (hw + 40), y, zs)) for y in (170, 200, 230)]
        a.take(mech.fasteners("_ss", D.seats_on(ob, pts, Vector((sx, 0, 0))), "M6", target=ob), f"Side_Panel_Screws_{tag}",
               f"Screws fixing the {tag.lower()} side panel to the backpack frame.")

    # ── radiators behind slatted grilles ────────────────────────────────────
    for sx, tag in ((1, "Left"), (-1, "Right")):
        v = vents[tag]
        a.take(v["bezel"], f"Radiator_Grille_Bezel_{tag}", f"Bezel framing the {tag.lower()} radiator outlet.")
        a.take(v["slats"], f"Radiator_Louvres_{tag}", f"Fixed louvres over the {tag.lower()} radiator outlet.")
        core = D.finned_block_bm(98, 86, 34, fins=18, fin_h=26)
        for yy in (30, -30):                                       # inlet (low) and outlet (high) stubs, inboard side
            P.merge(core, P.cyl(15, 14, 16), T(-sx * 49, yy, 4) @ R("Y", 90))
        a.add(f"Radiator_Core_{tag}", core, f"Liquid-to-air radiator core, {tag.lower()} side of the cooling loop.", "alu",
              rear(sx * 80, RAD_Z) @ T(0, 0, -58), bevel=0.3, seg=1)

    # ── axial blowers ───────────────────────────────────────────────────────
    for sx, tag in ((1, "Left"), (-1, "Right")):
        Mb = rear(sx * 80, BLOWER_Z)
        bm = P.revolve([(50, -34), (56, -34), (56, 0), (61, 0), (61, 2), (59, 3.6), (52, 3.6), (50, 1.6)], 64)
        P.merge(bm, P.revolve([(0, -33), (17, -33), (19, -31), (19, -19), (17, -17), (0, -17)], 32))     # motor pod
        for k in range(3):
            P.merge(bm, P.box(34, 5, 9), R("Z", 120 * k + 30) @ T(34.5, 0, -27))                          # pod struts
        a.add(f"Blower_Shroud_{tag}", bm, f"Shroud and motor pod of the {tag.lower()} cooling blower.", "alu", Mb, bevel=0.4,
              seg=1)
        rot = P.revolve([(0, -15.5), (16, -15.5), (17, -14.5), (17, -4), (13, -2.5), (0, -2.5)], 32)
        for k in range(9):
            P.merge(rot, P.box(32, 21, 2.0), R("Z", 40 * k) @ T(33.5, 0, -9) @ R("X", 34 * sx))
        a.add(f"Blower_Rotor_{tag}", rot, f"Nine-blade rotor of the {tag.lower()} cooling blower.", "cfrp", Mb, bevel=0)
        gd = P.cyl(18, 2.4, 24)
        gd.transform(T(0, 0, 4.4))
        for dia in (48, 88):
            P.merge(gd, P.torus(dia, 2.6, 48, 8), T(0, 0, 4.4))
        for k in range(6):
            P.merge(gd, P.cyl(2.6, 52, 8), R("Z", 60 * k) @ T(33, 0, 4.4) @ R("Y", 90))
        a.add(f"Blower_Guard_{tag}", gd, f"Wire finger guard over the {tag.lower()} blower outlet.", "fastener", Mb, bevel=0)

    # ── coolant reservoir with sight glass and filler ───────────────────────
    res = P.prism(P.rrect(40, 56, 8), 1326, 1466)
    P.merge(res, P.cyl(24, 18, 24), T(0, -16, 1473))                                                  # filler neck
    P.merge(res, P.cyl(15, 14, 16), T(0, -10, 1320))                                                  # outlet stub
    for sx in (1, -1):
        P.merge(res, P.cyl(13, 10, 16), T(sx * 22, -4, 1338) @ R("Y", 90))                            # return stubs
    a.add("Coolant_Reservoir", res, "Coolant header tank for the single liquid loop.", "alu", W @ T(0, y1 - 40, 0), bevel=0.8)
    C.boolean_cut(top, C.cutter(P.cyl(28, 60), W @ T(0, y1 - 56, z1)), lip=0.5)
    cap = P.revolve([(0, 0), (17, 0), (17, 1.2), (15.8, 1.6), (15.8, 2.4), (17, 2.8), (17, 6.5), (15, 8), (0, 8)], 32)
    a.add("Coolant_Filler_Cap", cap, "Filler cap of the coolant reservoir, on top of the backpack.", "alu",
          W @ T(0, y1 - 56, z1 + 1.5), bevel=0.3, seg=1)
    Mw = rear(0, BLOWER_Z)
    a.add("Coolant_Sight_Glass", P.prism(P.rrect(17.4, 71.4, 7.7), -5.0, -2.0), "Sight glass showing the coolant level.",
          "glass", Mw, bevel=0)
    a.add("Coolant_Sight_Bezel", P.ring_solid(P.rrect(30, 84, 13), P.rrect(18, 72, 8), 0.0, 1.8),
          "Bezel retaining the coolant sight glass.", "alu", Mw, bevel=0.4, seg=1)
    plug = P.cyl(18, 5, 6)
    P.merge(plug, P.cyl(24, 1.6, 24), T(0, 0, -1.7))
    a.add("Coolant_Drain_Plug", plug, "Drain plug at the low point of the cooling loop.", "fastener",
          D.seats_on(bot, [W @ Vector((60, yc - 6, z0 - 40))], -up, x_hint=(1, 0, 0))[0] @ T(0, 0, 2.5), bevel=0.3, seg=1)

    # ── battery service door on the left side, over-centre latches ──────────
    ysd = (y0 + 12 + y1 - 29) / 2 - 4.0                            # the side panel runs from y0+12 to y1-29
    seat = D.seats_on(side_l, [W @ Vector((hw + 40, ysd, 1300))], Vector((1, 0, 0)), x_hint=(0, 1, 0))[0]
    A.recess(side_l, P.rrect(63, 113, 6.5), seat, depth=3.6)
    a.add("Battery_Service_Door", P.prism(P.rrect(60, 110, 5), -3.2, 0.0),
          "Service door over the battery disconnect and charge port.", "armour", seat, bevel=0.6)
    a.take(F.hinge("_bh", 3.0, 84, 5, 0.0, seat @ T(-30.8, 0, 1.6)), "Battery_Door_Hinge",
           "Hinge along the front edge of the battery service door.")
    a.add("Battery_Door_Latches", _latches(30.0, (-30, 30)), "Over-centre latches holding the battery service door shut.",
          "fastener", seat, bevel=0.3, seg=1)

    # ── pump, manifold, pipes, blower controller ────────────────────────────
    pump = P.revolve([(0, 1232), (20, 1232), (23, 1235), (23, 1268), (21.6, 1269), (21.6, 1271), (23, 1272), (23, 1288),
                      (18, 1292), (0, 1292)], 40)
    for sx in (1, -1):
        P.merge(pump, P.cyl(16, 14, 16), T(sx * 27, 0, 1248) @ R("Y", 90))
    a.add("Coolant_Pump", pump, "Circulation pump of the liquid cooling loop.", "alu", W @ T(0, y0 + 50, 0), bevel=0.4, seg=1)
    man = P.prism(P.chamfer_poly(P.rrect(74, 34), 5), 1184, 1214)
    for x in (-24, -8, 8, 24):
        P.merge(man, P.cyl(13, 12, 16), T(x, 0, 1219))
    a.add("Coolant_Manifold", man, "Manifold splitting coolant between the radiators and the thorax loop.", "alu",
          W @ T(0, y0 + 30, 0), bevel=0.6)
    pipes = bmesh.new()
    runs = []
    zl, zh = RAD_Z - 30, RAD_Z + 30                              # radiator stubs: inlet low, outlet high
    for sx in (1, -1):
        runs.append([(sx * 24, y0 + 30, 1224), (sx * 26, y0 + 40, 1230), (sx * 26, y1 - 64, zl), (sx * 25, y1 - 54, zl)])
        runs.append([(sx * 8, y0 + 30, 1224), (sx * 13, y0 + 40, 1236), (sx * 30, y0 + 50, 1246), (sx * 33, y0 + 50, 1248)])
        runs.append([(sx * 25, y1 - 54, zh), (sx * 28, y1 - 50, zh + 16), (sx * 28, y1 - 45, 1330), (sx * 26, y1 - 44, 1338)])
    runs.append([(0, y0 + 50, 1292), (0, y0 + 56, 1304), (0, y1 - 54, 1311), (0, y1 - 50, 1313)])
    for run in runs:
        P.merge(pipes, P.sweep(P.catmull(run, step=4.0), 5.5, 12))
    a.add("Coolant_Pipes", pipes, "Rigid coolant pipes linking the manifold, pump, radiators and reservoir.", "alu", W,
          bevel=0)
    fc = D.finned_block_bm(92, 58, 20, fins=10)
    P.merge(fc, P.box(20, 12, 10), T(0, -35, 6))
    a.add("Blower_Controller", fc, "Motor controller for the two blowers and the pump, on its own heat sink.", "alu",
          W @ T(70, y0 + 8, 1428) @ R("X", -90), bevel=0.3, seg=1)

    # ── pad for the mount hardpoint ─────────────────────────────────────────
    ypad = PR.TRUNNION_Y + MT.FLANGE_Y_OFF - PR.TORSO_Y            # body y of the mount flange centre
    pad = [(y + ypad, z + 1274) for y, z in P.chamfer_poly(P.rrect(MT.FLANGE_LEN + 4, 160), 8)]
    pad_ob = a.add("Hardpoint_Pad", P.prism(pad, 0, 4),
                   "Titanium doubler spreading the mount hardpoint loads into the backpack frame.", "ti",
                   W @ T(-hw, 0, 0) @ YZ, bevel=0.6)
    for ob in (pad_ob, side_r):                                    # clearance holes for the hardpoint bolts
        holes = bmesh.new()
        for dy in MT.HP_BOLT_DY:
            for z in MT.HP_BOLT_Z:
                P.merge(holes, P.cyl(10.6, 60, 16), T(-hw, ypad + dy, z) @ R("Y", 90))
        C.boolean_cut(ob, C.cutter(holes, W), lip=0.3)
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    RV.closeup(objs, out / f"06_backpack_rear_clay{tag}.jpg", "06 backpack, rear three-quarter", (0.55, 0.8, 0.25), "clay",
               isolate=True, dist=3.8)
    RV.closeup(objs, out / f"06_backpack_rear_final{tag}.jpg", "06 backpack, rear, right side", (-0.6, 0.78, 0.2), "final",
               isolate=True, dist=3.8)
    inner = [o for o in objs if "Panel" not in o.name and "Screws" not in o.name and "Carrier" not in o.name]
    RV.closeup(inner, out / f"06_backpack_internals_clay{tag}.jpg", "06 backpack with the shell removed", (0.6, 0.75, 0.3),
               "clay", isolate=True, dist=3.8)
