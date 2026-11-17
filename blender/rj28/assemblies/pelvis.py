"""Assembly 05: pelvis.

A machined block with a keel between the thighs and a titanium top plate that
seats the waist slewing ring. Each hip is a three-axis stack kept entirely
above the hip pitch housing (which belongs to the leg): a pancake yaw actuator
clamped in a wing of the block, a roll link under it carrying a small roll
actuator behind the yaw stack, and a saddle that hangs the pitch housing from
the roll output.

Nothing fixed to the pelvis sits behind a hip between 90 and 170 mm from the
pitch axis below 50 mm above it: that zone belongs to the knee actuators,
which swing with the thigh.

World coordinates. Hip centres are at (+/-HX, 0, Z_HIP); the yaw frame is the
hip centre turned by the toe-out, the leg's hip frame adds the abduction.
"""
import math

import bmesh
import bpy
from mathutils import Vector

from .. import frames as FR, params as PR
from ..lib import armour as A, core as C, detail as D, harness as H, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm, raw
from . import abdomen as AB

TOP = AB.RING_Z - 8.0           # top of the block; the top plate sits on it and seats the waist ring
BOX_W, BOX_Y0, BOX_Y1 = 108.0, -88.0, 92.0
YAW_OD, YAW_L = 140.0, 28.0
LINK_Z = TOP - YAW_L - 3.0 - PR.Z_HIP      # top of the roll link plate, above the hip centre
ROLL_X, ROLL_Z = 38.0, 78.0     # hip roll axis in the yaw frame: parallel to Y, above the pitch housing
GUARD_R = 87.0                  # outer radius of the hip guards and of the top plate round each hip
ROLL_OD, ROLL_L, ROLL_Y = 48.0, 50.0, 137.0     # roll actuator, and the y of its rear face
PITCH_R = 87.0                  # hip pitch housing radius (leg)
PAD_R = PITCH_R + 7.5           # outer radius of the saddle pads


def _wc(bm, seats, d=14.0):
    for m in seats:
        c = H.connector_bm(d)
        for f in c.faces:
            f.material_index += 1
        P.merge(bm, c, m)
    return bm


def build():
    a = Asm("05")
    hx = PR.HX
    wy = PR.TORSO_Y                              # the waist ring is centred here in y

    # ── block: keel, box, and a clamp ring for each hip yaw actuator ────────
    bm = P.loft([A.csec(852, 70, 124, 0, 0, 0.18), A.csec(900, 84, 168, 0, 0, 0.16), A.csec(975, 84, 168, 0, 0, 0.16)])
    yc, dp = (BOX_Y0 + BOX_Y1) / 2, BOX_Y1 - BOX_Y0
    P.merge(bm, P.loft([A.csec(975, BOX_W, dp, 0, yc, 0.14), A.csec(TOP, BOX_W, dp, 0, yc, 0.14)]))
    for s in (1, -1):
        P.merge(bm, P.tube(YAW_OD + 16, YAW_OD + 1, 9, 1.0), T(s * hx, 0, TOP - YAW_L + 4.5))
        for y in (-58, 58):                       # webs tying each clamp ring back to the box
            P.merge(bm, P.box(34, 12, 22), T(s * (BOX_W / 2 + 12), y, TOP - 11))
    blk = a.add("Pelvis_Block", bm,
                "Machined pelvis block: keel between the thighs, box under the waist, hip yaw clamp rings.", "alu", None,
                bevel=1.0)
    for o in (1, -1):
        D.pocket_grid(blk, T(o * 42.3, 0, 936) @ R("Y", o * 90), 1, 2, 50, 40, 0, 52, depth=6.0)
    D.pocket_grid(blk, T(0, 84.3, 936) @ R("X", -90), 1, 1, 46, 50, 0, 0, depth=6.0)

    arc = [math.radians(-75 + 150 * k / 20) for k in range(21)]
    plate = [(hx + GUARD_R * math.cos(t), GUARD_R * math.sin(t)) for t in arc]
    plate += [(112, 108), (-112, 108)]
    plate += [(-hx - GUARD_R * math.cos(t), GUARD_R * math.sin(t)) for t in reversed(arc)]
    plate += [(-112, wy - 108), (112, wy - 108)]
    top = a.add("Pelvis_Top_Plate", P.prism(plate, TOP, TOP + 8),
                "Top plate closing the block; the waist slewing ring bolts to its machined face.", "ti", None, bevel=0.8)
    seats = [T(x, y, TOP + 8) for x, y in ((0, 86), (44, 84))]
    for s in (1, -1):
        seats += [T(s * (hx + x), y, TOP + 8) for x, y in ((41, 41), (41, -41), (0, 58), (0, -58))]
    a.take(mech.fasteners("_tp", seats, "M6", target=top), "Pelvis_Top_Plate_Screws",
           "Screws fixing the top plate to the block and to the hip yaw actuators.")

    # ── groin plate in two pieces, standing off the front of the block ──────
    g = hx - 18
    out = P.chamfer_poly([(-40, 0), (40, 0), (48, 96), (g, 132), (g, TOP - 862), (-g, TOP - 862), (-g, 132), (-48, 96)],
                         [8, 8, 6, 10, 12, 12, 10, 6])
    gp = raw(P.plate(out, 12, crown=7, slices=8), T(0, -100, 862) @ R("X", 90), "armour", 1.2, 3)
    A.gap_cut(gp, Vector((0, -100, 960)), (0, 0, 1))
    lower, upper = sorted(sorted(A.islands(gp), key=lambda o: -len(o.data.vertices))[:2],
                          key=lambda o: C.bounds_mm([o])[0].z)
    a.take(upper, "Groin_Plate_Upper", "Upper groin armour plate across the front of the pelvis.")
    a.take(lower, "Groin_Plate_Lower", "Lower groin armour plate covering the keel between the thighs.")
    posts = bmesh.new()
    for x, z in ((-30, 1012), (30, 1012), (-24, 904), (24, 904)):
        P.merge(posts, P.cyl(12, 18, 12), T(x, -93, z) @ R("X", 90))
    a.add("Groin_Plate_Standoffs", posts, "Standoff posts fixing the groin plates to the block.", "alu", None, bevel=0.3,
          seg=1)
    pts = [Vector((x, -160, z)) for x, z in ((-30, 1012), (30, 1012), (-96, 1022), (96, 1022))]
    a.take(mech.fasteners("_gu", D.seats_on(upper, pts, (0, -1, 0)), "M6", target=upper), "Groin_Upper_Screws",
           "Screws fixing the upper groin plate to its standoffs.")
    pts = [Vector((x, -160, 904)) for x in (-24, 24)]
    a.take(mech.fasteners("_gl", D.seats_on(lower, pts, (0, -1, 0)), "M6", target=lower), "Groin_Lower_Screws",
           "Screws fixing the lower groin plate to its standoffs.")

    # ── rear connector panel: where the leg harnesses plug in ───────────────
    pan = P.prism(P.rrect(88, 42, 5, 3), 0.0, 4.0)
    _wc(pan, [T(x, 0, 4) for x in (-28, 0, 28)], 13.0)
    a.add("Pelvis_Connector_Panel", pan, "Bulkhead panel where the leg harnesses plug into the pelvis.",
          ["alu", "fastener", "rubber"], T(0, BOX_Y1, 1006) @ R("X", -90), bevel=0.4)

    # ── hips: yaw actuator, roll link, roll actuator, saddle ────────────────
    for s in (1, -1):
        n = "L" if s > 0 else "R"
        side = "left" if s > 0 else "right"
        Lg = FR.leg(s)[0]
        Yw = T(s * hx, 0, PR.Z_HIP) @ R("Z", s * PR.TOE_OUT)
        Hm = T(s * hx, 0, TOP) @ R("X", 180)
        xp = s * ROLL_X
        d = mech.rotary_actuator("_hy", YAW_OD, YAW_L, Hm, bolts=10, fins=False)
        conn = d.pop("connector")                 # the standard connector is too tall for a pancake motor
        me = conn.data
        bpy.data.objects.remove(conn)
        bpy.data.meshes.remove(me)
        a.take_rotary(d, f"Hip_Yaw_{n}", f"{side} hip yaw")
        ang = -120 if s > 0 else -60
        a.add(f"Hip_Yaw_Connector_{n}", H.connector_bm(9.0), f"Power and encoder connector of the {side} hip yaw actuator.",
              ["fastener", "rubber"], Hm @ R("Z", ang) @ T(YAW_OD / 2 - 3.5, 0, 6.7) @ R("Y", 90), bevel=0)

        # roll link: plate under the yaw output, tongue running back to a clamp round the roll actuator
        bm = P.cyl(116, 8, 48)
        bm.transform(T(0, 0, LINK_Z - 4))
        P.merge(bm, P.prism(P.chamfer_poly(P.rrect(68, 128), 8), LINK_Z - 8, LINK_Z), T(xp, 44, 0))
        clamp = P.revolve(P.ring_profile(ROLL_OD / 2 + 0.5, LINK_Z - ROLL_Z, -14, 14, 1.0), 48, angle=200.0)
        P.merge(bm, clamp, T(xp, ROLL_Y - 27, ROLL_Z) @ R("X", 90) @ R("Z", -10))
        lk = a.add(f"Hip_Roll_Link_{n}", bm,
                   f"Link turning with the {side} hip yaw output and carrying the hip roll actuator above the joint.",
                   "alu", Yw, bevel=0.8)
        D.pocket_grid(lk, Yw @ T(xp, 46, LINK_Z), 1, 1, 40, 50, 0, 0, depth=3.5)
        ca = 0 if s > 0 else 180
        d = mech.rotary_actuator("_hr", ROLL_OD, ROLL_L, Yw @ T(xp, ROLL_Y, ROLL_Z) @ R("X", 90), bolts=0,
                                 connector_angle=ca)
        a.take_rotary(d, f"Hip_Roll_{n}", f"{side} hip roll")

        # saddle: pads bolted over the top of the pitch housing, lug onto the roll output
        yf = ROLL_Y - ROLL_L - 3.0                # roll output face
        pads = P.revolve(P.ring_profile(PITCH_R + 0.7, PAD_R, -20, 20, 1.0), 64, angle=110.0)
        pads.transform(Lg @ T(s * 46, 0, 0) @ R("Y", 90) @ R("Z", 125))
        lug = P.lug(22, 6, 14, 16, 32)
        lug.transform(Yw @ frame((xp, yf - 8, ROLL_Z), (0, 1, 0), (0, 0, 1)))
        P.merge(pads, lug)
        sd = a.add(f"Hip_Saddle_{n}", pads,
                   f"Saddle hanging the {side} hip pitch housing from the hip roll output.", "ti", None, bevel=0.6)
        seats = []
        for x in (36, 56):
            for al in (-36, 36):
                sn, cs = math.sin(math.radians(al)), math.cos(math.radians(al))
                seats.append(Lg @ frame((s * x, PAD_R * sn, PAD_R * cs), (0, sn, cs), (1, 0, 0)))
        a.take(mech.fasteners("_sd", seats, "M4", target=sd), f"Hip_Saddle_Screws_{n}",
               f"Screws fixing the {side} saddle pads to the hip pitch housing.")

        # hip guard: curved armour band round the front and outer side of the yaw stage; the rear stays open
        Gm = T(s * hx, 0, TOP - 31) @ R("Z", 0 if s > 0 else 180)       # local X points outboard
        gd = a.add(f"Pelvis_Hip_Guard_{n}", P.revolve(P.ring_profile(GUARD_R - 6.5, GUARD_R, 0, 31, 1.4), 64, angle=170.0),
                   f"Curved armour band guarding the {side} hip yaw stage; it carries a tie-down ring.", "armour",
                   Gm @ R("Z", -150 if s > 0 else -20), bevel=1.0, seg=2)
        seats = [Gm @ R("Z", -s * ang_) @ T(GUARD_R, 0, 13) @ R("Y", 90) for ang_ in (130, 90, 40)]
        a.take(mech.fasteners("_hg", seats, "M6", target=gd), f"Pelvis_Hip_Guard_Screws_{n}",
               f"Screws fixing the {side} hip guard to the yaw clamp ring.")
        td = P.box(7, 16, 12)
        td.transform(T(3.5, 0, 8))                    # staple at the top, ring hanging flat below it
        P.merge(td, P.torus(30, 5.5, 32, 10), T(3.6, 0, -9) @ R("Y", 90))
        a.add(f"Tie_Down_Ring_{n}", td, f"Fold-flat tie-down ring on the {side} hip guard for transport lashing.", "ti",
              Gm @ R("Z", s * 4) @ T(GUARD_R, 0, 17), bevel=0.3, seg=1)
    return a


def knee_zone_check(a):
    """Lowest pelvis point inside the knee actuators' corridor behind each hip:
    |x| <= 75 mm of the leg centre, y > 0, 90 to 170 mm from the pitch axis.
    The actuators swing up to about 45 mm above the axis; the result must stay above that."""
    worst = None
    for s in (1, -1):
        inv = FR.leg(s)[0].inverted()
        for ob in a.parts:
            if ob.type != "MESH":
                continue
            me = C.evaluated_mesh(ob)
            pts = [v.co / C.MM for v in me.vertices] + [p.center / C.MM for p in me.polygons]
            bpy.data.meshes.remove(me)
            for p in pts:
                q = inv @ p
                r = math.hypot(q.y, q.z)
                if abs(q.x) <= 75 and q.y > 0 and 90 <= r <= 170 and (worst is None or q.z < worst[0]):
                    worst = (round(q.z, 1), ob.name, "L" if s > 0 else "R")
    print("KNEE_ZONE lowest pelvis point in the corridor:", worst)
    return worst


def review(a, out, tag=""):
    from .. import review as RV
    knee_zone_check(a)
    objs = [o for o in a.parts if o.type == "MESH"]
    RV.closeup(objs, out / f"05_pelvis_rear_clay{tag}.jpg", "05 pelvis, rear three-quarter", (0.55, 0.8, 0.3), "clay",
               res=(1300, 1000), isolate=False, dist=3.0)
    RV.closeup(objs, out / f"05_pelvis_front_final{tag}.jpg", "05 pelvis, front three-quarter", (-0.5, -0.82, 0.25),
               "final", res=(1300, 1000), isolate=False, dist=3.0)
