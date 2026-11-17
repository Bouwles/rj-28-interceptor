"""The 46 joints of the RJ-28: where each axis is, how far it turns, what drives it.

build() drops an Empty named AXIS_<joint> at every pivot with the rotation
axis as local Z. They export with the model: the site uses them for callouts
and for the mount animation, and measure.py lists them in spec.json.
"""
from mathutils import Vector

from . import frames as FR, params as PR
from .lib import core as C
from .lib.core import T, frame

ROTARY = "Frameless BLDC motor with strain-wave reduction"
CYCLO = "Frameless BLDC motor with cycloidal reduction"
LINEAR = "Planetary roller-screw linear actuator"
LINKAGE = "Motor in the forearm, linkage drive"


def _dir(m, v):
    return (m.to_3x3() @ Vector(v)).normalized()


def joints():
    """List of dicts: name, group, origin (mm), axis (unit), range (deg), drive."""
    out = []

    def add(name, group, origin, axis, lo, hi, drive):
        out.append(dict(name=name, group=group, origin=Vector(origin), axis=Vector(axis).normalized(),
                        range=(lo, hi), drive=drive))

    W = FR.torso()
    for s, n in ((1, "L"), (-1, "R")):
        hip, thigh, knee, shin, ankle, foot = FR.leg(s)
        hp, kp, ap = hip.translation, knee.translation, ankle.translation
        add(f"hip_yaw_{n}", "leg", hp, (0, 0, 1), -40, 40, ROTARY)
        add(f"hip_roll_{n}", "leg", hp, (0, -1, 0), -25, 35, ROTARY)
        add(f"hip_pitch_{n}", "leg", hp, _dir(hip, (1, 0, 0)), -110, 30, ROTARY)
        add(f"knee_pitch_{n}", "leg", kp, _dir(knee, (1, 0, 0)), 0, PR.KNEE_RANGE, LINEAR + " x2 on a crank")
        add(f"ankle_pitch_{n}", "leg", ap, _dir(shin, (1, 0, 0)), -35, 35, LINEAR + " x2, common mode")
        add(f"ankle_roll_{n}", "leg", ap, _dir(foot, (0, -1, 0)), -20, 20, LINEAR + " x2, differential")
    add("waist_yaw", "waist", W @ Vector((0, 0, PR.Z_WAIST)), (0, 0, 1), -60, 60, ROTARY + " on a slewing ring")
    add("waist_pitch", "waist", W @ Vector((0, 0, PR.Z_WAIST + 20)), (1, 0, 0), -15, 30, LINEAR + " x2")
    for s, n in ((1, "L"), (-1, "R")):
        sv, upper, fore, hand = [W @ m if hasattr(m, "to_3x3") else W @ m for m in FR.arm(s)]
        ep, wp = fore.translation, hand.translation
        add(f"shoulder_pitch_{n}", "arm", sv, (1, 0, 0), -180, 60, ROTARY)
        add(f"shoulder_roll_{n}", "arm", sv, (0, -1, 0), -10, 120, ROTARY)
        add(f"shoulder_yaw_{n}", "arm", sv + _dir(upper, (0, 0, -1)) * 124, _dir(upper, (0, 0, 1)), -90, 90, ROTARY)
        add(f"elbow_pitch_{n}", "arm", ep, _dir(upper, (1, 0, 0)), 0, 135, CYCLO)
        add(f"forearm_roll_{n}", "arm", ep + _dir(fore, (0, 0, -1)) * 240, _dir(fore, (0, 0, 1)), -90, 90, ROTARY)
        add(f"wrist_pitch_{n}", "arm", wp, _dir(hand, (1, 0, 0)), -60, 60, ROTARY)
        add(f"wrist_yaw_{n}", "arm", wp, _dir(hand, (0, 1, 0)), -30, 30, ROTARY)
        add(f"thumb_opposition_{n}", "hand", hand @ Vector((-s * 8, -52, -34)), _dir(hand, (0, 0, 1)), 0, 80, LINKAGE)
        add(f"thumb_flexion_{n}", "hand", hand @ Vector((-s * 8, -52, -34)), _dir(hand, (0, 1, 0.6)), 0, 75, LINKAGE)
        for i, y in enumerate((-38, 0, 38)):
            add(f"finger{i + 1}_flexion_{n}", "hand", hand @ Vector((0, y, -98)), _dir(hand, (0, 1, 0)), 0, 95,
                LINKAGE + ", coupled knuckles")
        add(f"finger_splay_{n}", "hand", hand @ Vector((0, 0, -98)), _dir(hand, (1, 0, 0)), -8, 8, LINKAGE + ", ganged")
    add("neck_yaw", "neck", W @ Vector((0, 4, 1499)), (0, 0, 1), -70, 70, "Motor and pinion on a geared slewing ring")
    add("neck_pitch", "neck", W @ Vector((0, 4, 1526)), (1, 0, 0), -15, 15, LINEAR + " x2, common mode")
    add("neck_roll", "neck", W @ Vector((0, 4, 1526)), (0, -1, 0), -12, 12, LINEAR + " x2, differential")
    tr = Vector((PR.BORE_X, PR.TRUNNION_Y, PR.TRUNNION_Z))
    add("mount_elevation", "mount", tr, (1, 0, 0), PR.ELEV_MIN, PR.ELEV_MAX, "Motor and pinion on a gear sector")
    add("mount_traverse", "mount", (PR.BORE_X, PR.TRUNNION_Y, PR.TRUNNION_Z - PR.YOKE_DROP - 39), (0, 0, 1),
        -PR.TRAVERSE, PR.TRAVERSE, ROTARY + " on a slewing ring")
    cn = FR.cannon()
    add("tracker_tilt", "mount", cn @ Vector((-(PR.BARREL_OD / 2 + 63), 6, PR.BREECH_FWD + 54)), (1, 0, 0), -20, 45,
        "Small geared motor")
    return out


def build():
    co = C.coll("RJ28-AXES")
    made = []
    for j in joints():
        e = C.empty("AXIS_" + j["name"], frame(j["origin"], j["axis"]), co, size=40.0)
        e["rj28_joint"] = j["name"]
        e["rj28_group"] = j["group"]
        e["rj28_range"] = [float(j["range"][0]), float(j["range"][1])]
        e["rj28_drive"] = j["drive"]
        if j["name"] == "tracker_tilt":
            e["rj28_rides"] = "mount_elevation"          # this pivot moves with the cannon; the site re-parents it
        made.append(e)
    assert len(made) == sum(PR.DOF.values()), f"{len(made)} joints, expected {sum(PR.DOF.values())}"
    return made
