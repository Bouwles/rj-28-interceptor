"""Kinematic rig for the site: which joint every part follows.

Reads the part list measure.py wrote and the joint axes, and writes
site/src/data/rig.json. Nothing is built: the pivots come from axes.py, from
the hand's own knuckle chain and from the measured pins of the actuators.

  links      the tree. A link turns about `pivot`/`axis` (rest pose, mm) by
             gain * joint angle, on top of its parent.
  parts      part number -> link index, for parts that move as one piece.
  actuators  body pinned on one link, rod on another: the site keeps the two
             in line as the joint moves and stretches the bellows between.
  flex       cables, hoses and boots that bend across joints, and sets of
             pieces that sit on more than one link.
"""
import json
import re
from pathlib import Path

from mathutils import Vector

from . import axes, frames as FR
from .assemblies import hand as HAND
from .lib.core import R, T

DATA = Path(__file__).resolve().parents[2] / "site" / "src" / "data"

# Spec ranges are magnitudes; this is the turn about the axis that the positive sense needs.
SENSE = {"elbow_pitch": -1.0}
# Joints whose axis is not mirrored left to right: the right side turns the other way.
MIRRORED = ("hip_yaw", "hip_roll", "ankle_roll", "shoulder_roll", "shoulder_yaw", "forearm_roll", "wrist_yaw",
            "thumb_opposition", "thumb_flexion", "finger1_flexion", "finger2_flexion", "finger3_flexion")
KNUCKLE_GAIN = (1.0, 1.15, 0.9)          # coupled knuckles: share of the flexion each one takes


def _v(v):
    return [round(float(c), 2) for c in v]


def build():
    rows = json.loads((DATA / "parts.json").read_text(encoding="utf-8"))
    J = {j["name"]: j for j in axes.joints()}
    centre = {}
    for r in rows:
        centre[(r["assembly"], r["name"])] = (Vector(r["bbox_min"]) + Vector(r["bbox_max"])) / 2

    links, index = [], {}

    def link(name, parent, joint=None, gain=1.0, pivot=None, axis=None):
        d = dict(name=name, parent=index[parent] if parent else -1, joint=joint, gain=gain)
        if joint:
            j = J[joint]
            base = joint[:-2] if joint[-2:] in ("_L", "_R") else joint
            g = gain * SENSE.get(base, 1.0) * (-1.0 if joint.endswith("_R") and base in MIRRORED else 1.0)
            d.update(gain=round(g, 4), pivot=_v(pivot if pivot is not None else j["origin"]),
                     axis=[round(float(c), 5) for c in (axis if axis is not None else j["axis"])])
        index[name] = len(links)
        links.append(d)

    W = FR.torso()
    link("pelvis", None)
    for s, n in ((1, "L"), (-1, "R")):
        link(f"hipyaw_{n}", "pelvis", f"hip_yaw_{n}")
        link(f"hiproll_{n}", f"hipyaw_{n}", f"hip_roll_{n}")
        link(f"thigh_{n}", f"hiproll_{n}", f"hip_pitch_{n}")
        link(f"shin_{n}", f"thigh_{n}", f"knee_pitch_{n}")
        link(f"kneeguard_{n}", f"thigh_{n}", f"knee_pitch_{n}", gain=0.5)      # the guard's links halve the knee angle
        link(f"across_{n}", f"shin_{n}", f"ankle_pitch_{n}")
        link(f"foot_{n}", f"across_{n}", f"ankle_roll_{n}")
    link("waist", "pelvis", "waist_yaw")
    for i in range(1, 5):
        link(f"lame{i}", "waist", "waist_pitch", gain=i / 5)
    link("thorax", "waist", "waist_pitch")
    link("neckyaw", "thorax", "neck_yaw")
    link("neckpitch", "neckyaw", "neck_pitch")
    link("head", "neckpitch", "neck_roll")
    for s, n in ((1, "L"), (-1, "R")):
        arm_asm, hand_asm = ("07", "09") if s > 0 else ("08", "10")
        link(f"shpitch_{n}", "thorax", f"shoulder_pitch_{n}")
        link(f"skirt_{n}", f"shpitch_{n}", f"shoulder_roll_{n}", gain=0.85, pivot=centre[(arm_asm, "Pauldron Skirt Hinge")])
        link(f"shroll_{n}", f"shpitch_{n}", f"shoulder_roll_{n}")
        link(f"upper_{n}", f"shroll_{n}", f"shoulder_yaw_{n}")
        link(f"fore_{n}", f"upper_{n}", f"elbow_pitch_{n}")
        link(f"froll_{n}", f"fore_{n}", f"forearm_roll_{n}")
        link(f"wpitch_{n}", f"froll_{n}", f"wrist_pitch_{n}")
        link(f"hand_{n}", f"wpitch_{n}", f"wrist_yaw_{n}")
        hand = W @ FR.arm(s)[3]

        def chain(prefix, base, segs, joint, parent):
            m, ax = base, (base.to_3x3() @ Vector((0, 1, 0))).normalized()
            for k, (ln, _th, curl) in enumerate(segs):
                link(f"{prefix}{'abc'[k]}_{n}", parent, joint, gain=KNUCKLE_GAIN[k], pivot=m.translation, axis=ax)
                parent = f"{prefix}{'abc'[k]}_{n}"
                m = m @ R("Y", s * curl) @ T(0, 0, -ln)

        for i, (_name, y) in enumerate(HAND.FINGERS):
            link(f"splay{i + 1}_{n}", f"hand_{n}", f"finger_splay_{n}", gain=float(i - 1))
            chain(f"finger{i + 1}", hand @ T(0, y, -98), HAND.SEGS, f"finger{i + 1}_flexion_{n}", f"splay{i + 1}_{n}")
        tb = hand @ T(-s * 8, -52, -34)
        link(f"thumbopp_{n}", f"hand_{n}", f"thumb_opposition_{n}")
        chain("thumb", tb @ R("X", -42) @ R("Y", s * 2), ((42.0, 31.0, 28.0), (32.0, 28.0, 28.0)), f"thumb_flexion_{n}",
              f"thumbopp_{n}")

    # ── parts ────────────────────────────────────────────────────────────────
    def side(asm, name):
        if asm in ("07", "09", "11", "13"):
            return "L"
        if asm in ("08", "10", "12", "14"):
            return "R"
        m = re.search(r"\b([LR])\b", name)
        return m.group(1) if m else ""

    # first match wins; {n} is the side
    RULES = {
        "01": [(".", "head")],
        "02": [("Outer Race|Outer Bolts|Seal", "thorax"), ("Act |Boot", None), ("Gimbal Cross|Bearing Caps", "neckpitch"),
               ("Head Yoke|Clevis B|Pin B", "head"), (".", "neckyaw")],
        "03": [("Shoulder Pitch . Flange", "shpitch_{n}"), (".", "thorax")],
        "04": [("Act |Conduit|Coolant Hose|Ferrules|Waist Bellows$", None), ("Outer Race|Outer Bolts|Waist Seal|Unions Lower", "pelvis"),
               ("Lame (\\d) (Carrier|Guide)", "waist"), ("Lame 2 Slide", "lame1"), ("Lame 3 Slide", "lame2"), ("Lame 4 Slide", "lame3"),
               ("Lame (\\d)", "lame{d}"), ("Bellows Retainer", "lame4"),
               ("Tang|Clevis A|Pin A|Coolant Bracket|Unions Upper|Bellows Flange|Bellows Clamp", "thorax"), (".", "waist")],
        "05": [("Hip Yaw . Flange|Hip Roll Link|Hip Roll . Housing|Hip Roll . Connector", "hipyaw_{n}"),
               ("Hip Roll . Flange|Hip Saddle", "hiproll_{n}"), (".", "pelvis")],
        "06": [(".", "thorax")],
        "arm": [("Shoulder Roll Flange$|Shoulder Yoke|Shoulder Yaw Housing|Shoulder Yaw Connector", "shroll_{n}"),
                ("Pauldron Skirt$|Rub Strip|Skirt Hinge$", "skirt_{n}"), ("Shoulder Roll|Pauldron", "shpitch_{n}"),
                ("Shoulder Yaw Flange|Upper Arm|Elbow (Housing|Clamp|Hard|Connector|Encoder)", "upper_{n}"),
                ("Forearm Roll Flange", "froll_{n}"), (".", "fore_{n}")],
        "hand": [("Wrist Boot", None), ("Yoke Upper|Flange Screws", "froll_{n}"), ("Wrist Cross|Wrist .* Drive", "wpitch_{n}"),
                 ("Finger Index (Proximal|Links)", "finger1a_{n}"), ("Finger Index Middle", "finger1b_{n}"), ("Finger Index Distal", "finger1c_{n}"),
                 ("Finger Middle (Proximal|Links)", "finger2a_{n}"), ("Finger Middle Middle", "finger2b_{n}"), ("Finger Middle Distal", "finger2c_{n}"),
                 ("Finger Outer (Proximal|Links)", "finger3a_{n}"), ("Finger Outer Middle", "finger3b_{n}"), ("Finger Outer Distal", "finger3c_{n}"),
                 ("Pads", None), ("Thumb (Proximal|Links)", "thumba_{n}"), ("Thumb Distal", "thumbb_{n}"), (".", "hand_{n}")],
        "leg": [("Act |Bellows", None), ("Hip Pitch (Housing|Connector)|Idler Trunnion", "hiproll_{n}"),
                ("Knee Guard", "kneeguard_{n}"), ("Knee Shaft|Crank Pin|Shin|Calf|Ankle .* (Clevis|Pin) A", "shin_{n}"),
                ("Ankle .* (Clevis|Pin) B", "foot_{n}"), (".", "thigh_{n}")],
        "foot": [("Ankle Cross", "across_{n}"), ("Ankle Pitch", "shin_{n}"), (".", "foot_{n}")],
        "15": [(".", "thorax")],
        "16": [("Neck|Thigh Loom .$|Knee Loop|Ankle Loop|Arm Trunk .$|Shoulder Roll Lead|Shoulder Yaw Lead|Elbow Loop|Coolant Line .( Ferrules)?$|"
                "Hip (Pitch|Roll) . Lead|Waist Yaw Lead|(Knee|Ankle) (Inner|Outer)", None),
               ("Knee Junction|Thigh Loom|Knee Encoder", "thigh_{n}"), ("Foot Plug", "foot_{n}"),
               ("Arm Junction|Arm Trunk . Clips|Elbow Lead|Coolant Line . Clips", "upper_{n}"), ("Forearm", "fore_{n}"),
               ("Leg Trunk Plug|Panel Plug|Hip Yaw", "pelvis"), (".", "thorax")],
        "17": [(".", None)],              # a marking goes with the panel it is printed on
    }
    KIND = {"07": "arm", "08": "arm", "09": "hand", "10": "hand", "11": "leg", "12": "leg", "13": "foot", "14": "foot"}
    parts, loose = {}, []
    for r in rows:
        asm, name = r["assembly"], r["name"]
        n = side(asm, name)
        for pat, to in RULES[KIND.get(asm, asm)]:
            m = re.search(pat, name)
            if m:
                if to is None:
                    loose.append(r)
                else:
                    parts[r["number"]] = index[to.format(n=n, d=m.group(1) if m.groups() else "")]
                break

    num = {(r["assembly"], r["name"]): r["number"] for r in rows}
    L = lambda name: index[name]  # noqa: E731

    # ── actuators ────────────────────────────────────────────────────────────
    actuators, act_of = [], {}

    def actuator(asm, stem, a_link, a_pin, b_link, b_pin, soft):
        d = dict(name=f"{asm} {stem}", a=L(a_link), b=L(b_link), pa=_v(centre[(asm, a_pin)]), pb=_v(centre[(asm, b_pin)]),
                 body=[num[(asm, f"{stem} Act Body")]], rod=[num[(asm, f"{stem} Act Rod")]],
                 bellows=[num[(asm, f"{stem} {soft}")]])
        act_of[(asm, stem)] = len(actuators)
        actuators.append(d)

    for asm, n in (("11", "L"), ("12", "R")):
        for io in ("Outer", "Inner"):
            actuator(asm, f"Knee {io}", f"thigh_{n}", f"Knee {io} Pin A", f"shin_{n}", f"Knee {io} Crank Pin", "Act Bellows")
            actuator(asm, f"Ankle {io}", f"shin_{n}", f"Ankle {io} Pin A", f"foot_{n}", f"Ankle {io} Pin B", "Act Bellows")
    for n in ("L", "R"):
        actuator("04", f"Waist Pitch {n}", "thorax", f"Waist Pitch {n} Pin A", "waist", f"Waist Pitch {n} Pin B", "Act Bellows")
    for n in ("Left", "Right"):
        actuator("02", f"Neck {n}", "neckyaw", f"Neck {n} Pin A", "head", f"Neck {n} Pin B", "Boot")
    done = {p for a in actuators for k in ("body", "rod", "bellows") for p in a[k]}

    # ── flexible parts ───────────────────────────────────────────────────────
    # base link, direction the part runs (rest pose), then spans: the links crossed between two
    # fractions of the part's length. `act` hands the far end to an actuator body instead.
    flex = []

    def bend(asm, name, base, direction, *spans, act=None):
        key = (asm, name)
        if key not in num:
            raise KeyError(key)
        d = dict(part=num[key], base=L(base), dir=_v(Vector(direction).normalized()),
                 spans=[dict(links=[L(x) for x in ls], u=[u0, u1]) for ls, u0, u1 in spans])
        if act is not None:
            d["act"] = act
        flex.append(d)
        done.add(num[key])

    up, down = (0, 0, 1), (0, 0, -1)
    neck = (["neckyaw", "neckpitch", "head"], 0.15, 0.85)
    for name in ("Neck Loom 1", "Neck Loom 2", "Neck Loom 3", "Neck Coolant Line", "Neck Coolant Line Ferrules"):
        bend("16", name, "thorax", up, neck)
    for name in ("Waist Conduit", "Waist Conduit Glands", "Waist Coolant Hose Supply", "Waist Coolant Ferrules Supply",
                 "Waist Coolant Hose Return", "Waist Coolant Ferrules Return"):
        bend("04", name, "pelvis", up, (["waist", "thorax"], 0.2, 0.8))
    bend("04", "Waist Bellows", "waist", up, (["thorax"], -2.5, 1.0))         # lower cuff on the top lame (0.8 of the pitch)
    bend("16", "Waist Yaw Lead", "waist", up, (["thorax"], 0.2, 0.8))
    for s, n in ((1, "L"), (-1, "R")):
        leg, arm, hnd = ("11", "07", "09") if s > 0 else ("12", "08", "10")
        hip = [f"hipyaw_{n}", f"hiproll_{n}", f"thigh_{n}"]
        bend("16", f"Thigh Loom {n}", "pelvis", down, (hip, 0.08, 0.55))
        bend("16", f"Hip Roll {n} Lead", "pelvis", (s, 0, 0), ([f"hipyaw_{n}"], 0.25, 0.8))
        bend("16", f"Hip Pitch {n} Lead", "pelvis", (s * 0.5, -0.6, -0.6), (hip[:2], 0.2, 0.8))
        bend("16", f"Knee Loop {n}", f"thigh_{n}", down, ([f"shin_{n}"], 0.1, 0.9))
        bend("16", f"Ankle Loop {n}", f"shin_{n}", down, ([f"across_{n}", f"foot_{n}"], 0.15, 0.85))
        for io in ("Outer", "Inner"):
            ka, aa = act_of[(leg, f"Knee {io}")], act_of[(leg, f"Ankle {io}")]
            bend("16", f"Knee {io} Lead {n}", f"thigh_{n}", up, ([], 0.3, 0.9), act=ka)
            bend("16", f"Knee {io} Plug {n}", f"thigh_{n}", up, ([], -1, 0), act=ka)
            bend("16", f"Ankle {io} Lead {n}", f"shin_{n}", (0, 1, 0), ([], 0.3, 0.9), act=aa)
            bend("16", f"Ankle {io} Plug {n}", f"shin_{n}", (0, 1, 0), ([], -1, 0), act=aa)
        sh = [f"shpitch_{n}", f"shroll_{n}", f"upper_{n}"]
        out = (s * 0.55, 0, -0.85)
        bend("16", f"Arm Trunk {n}", "thorax", out, (sh, 0.1, 0.8))
        bend("16", f"Shoulder Roll Lead {n}", f"shpitch_{n}", down, ([f"shroll_{n}", f"upper_{n}"], 0.2, 0.8))
        bend("16", f"Shoulder Yaw Lead {n}", f"shroll_{n}", (s, 0, 0), ([f"upper_{n}"], 0.2, 0.8))
        bend("16", f"Elbow Loop {n}", f"upper_{n}", down, ([f"fore_{n}"], 0.1, 0.9))
        for name in (f"Arm Coolant Line {n}", f"Arm Coolant Line {n} Ferrules"):
            bend("16", name, "thorax", (s * 0.5, 0, -0.86), (sh, 0.05, 0.45), ([f"fore_{n}"], 0.55, 0.9))
        for name in ("Wrist Boot", "Wrist Boot Clamps"):
            bend(hnd, name, f"froll_{n}", down, ([f"wpitch_{n}", f"hand_{n}"], 0.2, 0.8))
        # grip pads: one node, a pad on every segment
        for i, f in enumerate(("Index", "Middle", "Outer")):
            flex.append(dict(part=num[(hnd, f"Finger {f} Pads")],
                             nearest=[dict(link=L(f"finger{i + 1}{k}_{n}"), at=_v(centre[(hnd, f"Finger {f} {seg}")]))
                                      for k, seg in zip("abc", ("Proximal", "Middle", "Distal"))]))
            done.add(num[(hnd, f"Finger {f} Pads")])
        flex.append(dict(part=num[(hnd, "Thumb Pads")],
                         nearest=[dict(link=L(f"thumb{k}_{n}"), at=_v(centre[(hnd, f"Thumb {seg}")]))
                                  for k, seg in zip("ab", ("Proximal", "Distal"))]))
        done.add(num[(hnd, "Thumb Pads")])

    left = [r["name"] for r in loose if r["number"] not in done and r["assembly"] != "17"]
    assert not left, f"parts with no place in the rig: {left}"
    assert len(parts) + len(done) + sum(1 for r in rows if r["assembly"] == "17") == len(rows)

    joints = {j["name"]: [float(j["range"][0]), float(j["range"][1])] for j in J.values()}
    recoil = [num[("15", n)] for n in ("Barrel", "Barrel Lock Collar", "Barrel Reinforce", "Muzzle Ring")]
    feet = {n: _v(J[f"ankle_pitch_{n}"]["origin"]) for n in ("L", "R")}
    out = dict(units="mm, Z up, robot faces -Y", links=links, joints=joints, parts=parts, actuators=actuators, flex=flex,
               recoil=recoil, feet=feet)
    (DATA / "rig.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8", newline="\n")
    print(f"RIG {len(links)} links, {len(parts)} rigid parts, {len(actuators)} actuators, {len(flex)} flexible parts")
