"""Assembly 04: abdomen and spine. The one narrow part of the figure, and all mechanism.

From the pelvis up: waist slewing ring (yaw), turntable, spine column, pitch
pivot at the column head, two short roller-screw actuators that run up into
the thorax floor, the yaw drive standing on the turntable, a conduit and two
coolant hoses crossing the joint, four overlapping lames hung off the spine,
and a rubber bellows sealing the gap up to the chest armour.

Body coordinates (before the torso offset). The yaw axis is x = y = 0.
"""
import math

import bmesh
from mathutils import Vector

from .. import frames as FR, params as PR
from ..lib import armour as A, core as C, detail as D, harness as H, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm, raw
from . import thorax as TH

RING_Z = 1054.0                 # underside of the waist slewing ring (the 1,060 landmark lies inside it)
RING_OD, RING_ID, RING_H = 200.0, 132.0, 24.0
DECK_Z = RING_Z + RING_H        # turntable underside
DECK_T = 12.0
SPINE_Y = 26.0                  # spine column stands behind the yaw axis
PIVOT_Z = 1174.0                # waist pitch axis (parallel to X, through the spine head)
HEAD_Z = 1136.0                 # top of the spine column, underside of the fork head
RING_H = 11.0
RING_ZS = (1107.5, 1118.5, 1129.5, HEAD_Z + 7.0)   # stacked clamp rings, one per lame
ACT_TOP_Z = 1272.0              # upper pivots of the pitch actuators, inside the thorax
ACT_BOT = (78.0, 64.0, 1124.0)  # lower pivots, on the turntable pads (+/-x)
MOTOR = (20.0, 113.2)           # yaw drive: 115 mm from the yaw axis, where its pinion meets the ring gear
CONDUIT_FOOT = (-40.0, 116.0)   # where the conduit and hoses leave the pelvis top plate
HOSE_FEET = ((-78.0, 112.0), (-100.0, 104.0))
LAMES = [(1094 + 34 * i, 232 + 24 * i, 168 + 24 * i) for i in range(4)]     # (centre z, width, depth)
LAME_H, LAME_Y, LAME_REAR = 38.0, -22.0, 8.0


def _bar(p0, p1, w=16.0, t=8.0):
    p0, p1 = Vector(p0), Vector(p1)
    bm = P.box(w, t, (p1 - p0).length)
    bm.transform(frame((p0 + p1) / 2, p1 - p0, (0, 0, 1)))
    return bm


def build():
    a = Asm("04")
    W = FR.torso()

    # ── waist yaw: slewing ring, turntable, drive ───────────────────────────
    d = mech.slewing_ring("_ws", RING_OD, RING_ID, RING_H, bolts=16, matrix=W @ T(0, 0, RING_Z), geared=True)
    a.take_slew(d, "Waist", "waist yaw")
    bm = P.revolve([(34, 0), (82, 0), (82, DECK_T - 3), (79, DECK_T), (34, DECK_T)], 64)
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(236, 60), 10), 0, DECK_T), T(0, ACT_BOT[1], 0))
    P.merge(bm, P.cyl(84, DECK_T, 48), T(MOTOR[0], MOTOR[1], DECK_T / 2))
    deck = a.add("Waist_Turntable", bm,
                 "Turntable on the rotating race: carries the spine, the pitch actuators and the yaw drive.", "alu",
                 W @ T(0, 0, DECK_Z), bevel=0.8)
    C.boolean_cut(deck, C.cutter(P.cyl(17, 40, 16), W @ T(MOTOR[0], MOTOR[1], DECK_Z)), lip=0.3)
    zm = DECK_Z + DECK_T + 64.0
    d = mech.rotary_actuator("_wy", 60, 60, W @ T(MOTOR[0], MOTOR[1], zm) @ R("X", 180), bolts=6, connector_angle=0)
    a.take_rotary(d, "Waist_Yaw_Drive", "waist yaw drive")
    pin = mech.gear_bm(2.5, 14, 16, 8)
    P.merge(pin, P.cyl(12, 36, 16), T(0, 0, 14))
    a.add("Waist_Yaw_Pinion", pin, "Pinion on the yaw drive shaft, walking round the fixed ring gear.", "steel",
          W @ T(MOTOR[0], MOTOR[1], RING_Z + 11), bevel=0.25, seg=1)

    # ── spine column and the pitch pivot at its head ────────────────────────
    z0 = DECK_Z + DECK_T
    col = a.add("Spine_Column", P.revolve([(30, 0), (56, 0), (56, 8), (45.5, 8), (44, 12), (43, 12), (43, HEAD_Z - z0),
                                           (30, HEAD_Z - z0)], 48),
                "Hollow spine column carrying torso loads; the harness runs up its bore.", "alu",
                W @ T(0, SPINE_Y, z0), bevel=0.6)
    a.take(mech.fasteners("_sb", mech.ring((0, SPINE_Y, z0 + 8), (0, 0, 1), 50.6, 10), "M4", target=col, matrix=W),
           "Spine_Base_Screws", "Screws fixing the spine column to the turntable.")
    bm = P.cyl(86, 14, 48)
    bm.transform(T(0, SPINE_Y, HEAD_Z + 7))
    for o in (1, -1):
        P.merge(bm, P.lug(22, 10, 32, 12, 32), frame((o * 31, SPINE_Y, PIVOT_Z), (1, 0, 0), (0, 0, 1)))
    a.add("Spine_Head_Fork", bm, "Fork at the head of the spine; the thorax pitches about the pin through it.", "ti", W,
          bevel=0.8)
    a.add("Waist_Pitch_Pin", mech.pin_bm(20, 80), "Pivot pin of the waist pitch joint.", "steel",
          W @ T(0, SPINE_Y, PIVOT_Z) @ R("Y", 90), bevel=0)
    bm = P.lug(22, 10, 26, 48, 32)
    bm.transform(frame((0, SPINE_Y, PIVOT_Z), (1, 0, 0), (0, 0, -1)))
    # the foot runs forward of the fork cheeks so it clears them as the thorax pitches
    P.merge(bm, P.prism(P.rrect(48, 46, 4, 3), TH.FLOOR_Z - 8, TH.FLOOR_Z), T(0, SPINE_Y, 0))
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(96, 20), 5), TH.FLOOR_Z - 8, TH.FLOOR_Z), T(0, -6, 0))
    tang = a.add("Thorax_Pitch_Tang", bm, "Tang bolted under the thorax floor, riding on the waist pitch pin.", "alu", W,
                 bevel=0.8)
    seats = [W @ T(x, -6, TH.FLOOR_Z - 8) @ R("X", 180) for x in (-37, -13, 13, 37)]
    a.take(mech.fasteners("_tt", seats, "M6", target=tang), "Thorax_Tang_Screws",
           "Screws fixing the pitch tang to the thorax floor.")
    a.add("Waist_Pitch_Encoder", D.encoder_bm(38), "Absolute encoder reading waist pitch at the pin end.",
          ["alu", "fastener"], W @ T(-40.5, SPINE_Y, PIVOT_Z) @ R("Y", -90) @ R("Z", 90), bevel=0.3)

    # ── waist pitch actuators: rod ends on the turntable, bodies up inside the thorax ──
    for s, tag in ((1, "L"), (-1, "R")):
        p0 = W @ Vector((s * TH.WELL[0], TH.WELL[1], ACT_TOP_Z))
        p1 = W @ Vector((s * ACT_BOT[0], ACT_BOT[1], ACT_BOT[2]))
        d = mech.linear_actuator("_wp", p0, p1, 38, 22, 30, pin_axis=(1, 0, 0), body_len=58,
                                 base_dir0=(0, 0, 1), base_dir1=(0, 0, -1))
        a.take_actuator(d, f"Waist_Pitch_{tag}", "waist pitch")

    # ── conduit and coolant hoses across the joint ──────────────────────────
    pts = [W @ Vector(p) for p in ((CONDUIT_FOOT[0], CONDUIT_FOOT[1], RING_Z + 2), (-44, 118, 1098), (-36, 102, 1150),
                                    (-22, 78, 1196), (TH.CONDUIT[0], TH.CONDUIT[1], TH.FLOOR_Z + 8))]
    path = P.catmull(pts, step=2.5)
    length = sum((q - p).length for p, q in zip(path, path[1:]))
    n = max(8, round(length / 5.5))
    a.add("Waist_Conduit", P.sweep(path, lambda t: 14.6 + 1.5 * math.sin(t * n * 2 * math.pi), 14),
          "Corrugated conduit carrying power and data across the waist joint.", "rubber", None, bevel=0)
    coll = bmesh.new()
    for i, j, back in ((0, 1, 6.0), (-1, -2, 23.0)):       # the upper collar sits just under the thorax floor
        P.merge(coll, P.tube(42, 27, 12, 1.0),
                frame(path[i] + (path[j] - path[i]).normalized() * back, path[j] - path[i]))
    a.add("Waist_Conduit_Collars", coll, "Clamp collars anchoring both ends of the waist conduit.", "alu", None, bevel=0)
    for k, (fx, fy) in enumerate(HOSE_FEET):
        run = [W @ Vector(p) for p in ((fx, fy, RING_Z + 9), (fx - 3, fy + 5, 1088), (fx + 3, fy + 30, 1112 - 2 * k),
                                        (fx + 14 - 2 * k, 162, 1139))]
        h = H.hose("_wh", run, 7.0)
        nm = ("Supply", "Return")[k]
        a.take(h["hose"], f"Waist_Coolant_Hose_{nm}",
               f"Coolant {nm.lower()} hose from the backpack radiators down to the hip and leg actuators.")
        a.take(h["ferrules"], f"Waist_Coolant_Ferrules_{nm}", f"Crimped end fittings of the coolant {nm.lower()} hose.")

    # ── lames: four overlapping bands hung off the spine, open at the rear ──
    for i, (zc, w, dp) in enumerate(LAMES):
        secs = [A.rsec(zc - LAME_H / 2, w, dp, 0, LAME_Y, 46), A.rsec(zc + LAME_H / 2, w, dp, 0, LAME_Y, 46)]
        lame = raw(A.shell(secs, 10.0), W, "armour", 1.2, 3)
        C.boolean_cut(lame, C.cutter(P.box(w + 80, 300, 90), W @ T(0, LAME_REAR + 150, zc)), lip=0.6)
        a.take(lame, f"Lame_{i + 1}", f"Abdominal lame {i + 1} of 4: an armour band that slides over its neighbour as the waist moves.")
        zr = RING_ZS[i]                                       # rings stack up the column; the top one clamps the fork head
        bm = P.tube(112, 87, RING_H, 1.0)
        bm.transform(T(0, SPINE_Y, zr))
        for o in (1, -1):
            xi = o * (w / 2 - 10)
            P.merge(bm, _bar((o * 40, SPINE_Y - 40, zr), (xi - o * 5, -8, zc), 10.0))
            P.merge(bm, P.box(6, 34, 22), T(xi - o * 3.4, -10, zc))
        a.add(f"Lame_{i + 1}_Carrier", bm, f"Clamp ring and arms hanging lame {i + 1} off the spine.", "ti", W, bevel=0.5,
              seg=1)
        pts = [W @ Vector((o * 200, -10, zc)) for o in (1, -1)]
        seats = D.seats_on(lame, pts[:1], (1, 0, 0)) + D.seats_on(lame, pts[1:], (-1, 0, 0))
        a.take(mech.fasteners("_ls", seats, "M6", target=lame), f"Lame_{i + 1}_Screws",
               f"Screws fixing lame {i + 1} to its carrier arms.")

    # ── bellows: seals the gap between the top lame and the chest armour ────
    zs = [1216 + 4 * k for k in range(11)]
    bel = raw(P.thicken(P.loft([TH.tub_at(z, 3.0 if k % 2 == 0 else 10.5) for k, z in enumerate(zs)], cap=False), 2.0),
              W, "rubber", 0)
    C.boolean_cut(bel, C.cutter(P.box(500, 300, 120), W @ T(0, 30 + 150, 1236)))
    a.take(bel, "Waist_Bellows", "Rubber bellows sealing the under-chest gap while the waist pitches and turns.")
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    RV.closeup(objs, out / f"04_abdomen_rear_clay{tag}.jpg", "04 abdomen, rear three-quarter", (0.6, 0.78, 0.22), "clay",
               res=(1300, 1100), isolate=True, dist=3.0)
    RV.closeup(objs, out / f"04_abdomen_rear_final{tag}.jpg", "04 abdomen, rear three-quarter", (-0.55, 0.8, 0.2),
               "final", res=(1300, 1100), isolate=True, dist=3.0)
