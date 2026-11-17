"""Assembly 02: neck. Three degrees of freedom in 55 mm of height.

Yaw: a geared slewing ring on the thorax top deck, driven by a small motor
that rides on the rotating side and walks its pinion round the fixed gear.
Pitch and roll: a two-axis gimbal. The pitch yoke stands on the turntable;
the roll ears hang from the head and swing down into the bore of the ring,
which is what lets the joint be this short. Two roller-screw actuators at the
rear tilt the head, and stay visible under the cap brim.

Body coordinates (FR.torso() applied). Neck axis at (0, 4).
"""
import bmesh
from mathutils import Vector

from .. import frames as FR
from ..lib import core as C, detail as D, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm

CY = 4.0             # neck axis, y
Z_DECK = 1490.0      # thorax top deck
Z_GIMBAL = 1526.0    # pitch and roll axes cross here
Z_HEAD = 1546.0      # underside of the skull frame's base ring
RANGE = dict(yaw=70.0, pitch=15.0, roll=12.0)


def build():
    a = Asm("02")
    W = FR.torso()
    N = W @ T(0, CY, 0)

    # ── yaw: geared slewing ring, motor and pinion on the rotating side ─────
    ring = mech.slewing_ring("_ny", 128, 78, 18, bolts=12, size="M4", matrix=W @ T(0, CY, Z_DECK), geared=True,
                             module=2.0)
    a.take_slew(ring, "Neck_Yaw", "neck yaw")
    z_top = Z_DECK + 18.0

    bm = P.revolve(P.ring_profile(40, 53, z_top, z_top + 5, 0.8), 48)                 # turntable ring on the inner race
    P.merge(bm, P.box(108, 8, 22), T(0, 22 - CY, z_top + 15))                         # rear wall: actuator fork seats
    P.merge(bm, P.box(30, 60, 6), T(0, 52 - CY, z_top + 9))                           # arm out to the yaw motor
    for o in (1, -1):
        P.merge(bm, P.lug(10, 5.2, Z_GIMBAL - z_top - 4, 10, 24), frame((o * 46, 0, Z_GIMBAL), (1, 0, 0), (0, 0, 1)))
        P.merge(bm, P.box(10, 34, 12), T(o * 49, 14 - CY, z_top + 10))                # ties from the yoke ears to the wall
    a.add("Gimbal_Base", bm, "Turntable on the yaw ring: carries the pitch yoke, the actuator seats and the yaw motor.",
          "ti", N, bevel=0.5)
    a.add("Neck_Yaw_Motor", P.revolve([(0, 0), (15, 0), (16, 1.5), (16, 30), (13, 33), (13, 36), (0, 36)], 32),
          "Motor that walks its pinion round the fixed ring gear to yaw the head.", "alu", N @ T(0, 74, z_top + 12),
          bevel=0.5)
    pin = mech.gear_bm(2.0, 12, 12, 8)
    P.merge(pin, P.cyl(8, 22, 16), T(0, 0, 14))
    a.add("Neck_Yaw_Pinion", pin, "Pinion and shaft meshing the neck ring gear.", "steel", N @ T(0, 74, Z_DECK + 9),
          bevel=0.2, seg=1)
    a.add("Neck_Yaw_Encoder", D.encoder_bm(26), "Encoder on the yaw motor shaft.", ["alu", "fastener"],
          N @ T(0, 74, z_top + 48) @ R("Z", 90), bevel=0.3, seg=1)

    # ── pitch / roll gimbal ─────────────────────────────────────────────────
    cross = P.box(34, 34, 16)
    P.merge(cross, P.cyl(10, 110, 24), R("Y", 90))                                    # pitch trunnions (X)
    P.merge(cross, P.cyl(10, 72, 24), R("X", 90))                                     # roll trunnions (Y)
    a.add("Gimbal_Cross", cross, "Cross of the neck gimbal: pitch trunnions to the base yoke, roll trunnions to the head yoke.",
          "steel", N @ T(0, 0, Z_GIMBAL), bevel=0.6)
    bm = P.prism(P.chamfer_poly(P.rrect(30, 104), 6), Z_HEAD - 8, Z_HEAD)             # bar under the skull base ring
    for o in (1, -1):
        P.merge(bm, P.lug(10, 5.2, Z_HEAD - 8 - Z_GIMBAL + 1, 10, 24), frame((0, o * 27, Z_GIMBAL), (0, 1, 0), (0, 0, -1)))
    hy = a.add("Gimbal_Head_Yoke", bm, "Yoke under the skull frame whose ears ride the gimbal's roll trunnions.", "ti", N,
               bevel=0.5)
    seats = [T(x, y, Z_HEAD - 8) @ R("X", 180) for x in (-8, 8) for y in (-44, 44)]
    a.take(mech.fasteners("_hy", seats, "M4", target=hy, matrix=N), "Head_Yoke_Screws",
           "Screws fixing the head yoke up into the skull frame's base ring.")
    caps = bmesh.new()
    for o in (1, -1):
        P.merge(caps, P.revolve([(0, 0), (8, 0), (8, 2.5), (6, 4), (0, 4)], 20), T(o * 51, 0, 0) @ R("Y", o * 90))
        P.merge(caps, P.revolve([(0, 0), (8, 0), (8, 2.5), (6, 4), (0, 4)], 20), T(0, o * 32, 0) @ R("X", -o * 90))
    a.add("Gimbal_Bearing_Caps", caps, "Caps retaining the four gimbal trunnion bearings.", "alu", N @ T(0, 0, Z_GIMBAL),
          bevel=0.3, seg=1)

    # ── two actuators at the rear: together they pitch the head, opposed they roll it ──
    for o, tag in ((1, "Left"), (-1, "Right")):
        p0 = W @ Vector((o * 42, 40, z_top + 16))
        p1 = W @ Vector((o * 46, 64, 1580))
        d = mech.linear_actuator("_na", p0, p1, 20, 10, 12, bellows=False, pin_axis=(1, 0, 0), body_len=26,
                                 base_dir0=(0, -1, 0), base_dir1=(0, 0, 1))
        a.take_actuator(d, f"Neck_{tag}", "neck pitch and roll")
        ax = (p1 - p0).normalized()
        a.add(f"Neck_{tag}_Boot", mech.bellows_bm(5.0, 9.0, 12.0, pitch=3.0, cuff=2.0),
              "Rubber boot over the neck actuator rod.", "rubber", frame(p0 + ax * 37.6, ax), bevel=0)
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    for name, d, mode in (("rear", (0.5, 1.0, 0.45), "clay"), ("front", (-0.6, -1.0, 0.5), "clay"),
                          ("rear_final", (0.5, 1.0, 0.45), "final")):
        RV.closeup(objs, out / f"02_neck_{name}{tag}.jpg", f"02 neck, {name}", d, mode, isolate=True, dist=4.4,
                   res=(1300, 1000))
