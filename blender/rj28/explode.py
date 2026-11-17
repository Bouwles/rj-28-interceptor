"""Exploded-view data.

Two stages, as the site plays them:

1. Assemblies leave the body along the direction they would be removed in.
   Each assembly gets an Empty (RJ28-AA_<name>) that parents its parts and
   carries explode_stage = 1 and explode_offset (metres).
2. Parts leave their assembly. Each part carries explode_stage = 2 and an
   explode_offset in metres, relative to its assembly.

Stage 2 offsets follow assembly logic rather than a blanket scale-up: every
assembly has a spine line (limb axis, torso axis, bore axis). Parts move
radially away from that line, so armour lifts off outwards, mechanism slides
out to the open side, and the frame on the spine stays put. Screw sets back
out along their own axis; a part can override its direction with explode_dir.
"""
import bpy
from mathutils import Vector

from . import frames as FR, params as PR, parts
from .lib import core as C
from .lib.core import MM

# stage 1: assembly offsets in mm
ASM_OFFSET = {
    "01": (0, -20, 430), "02": (0, 0, 210), "03": (0, 0, 0), "04": (0, 0, -150), "05": (0, 0, -330),
    "06": (0, 420, 40), "07": (430, 0, 40), "08": (-430, 0, 40), "09": (600, -60, -210), "10": (-600, -60, -210),
    "11": (210, 0, -560), "12": (-210, 0, -560), "13": (300, -60, -800), "14": (-300, -60, -800),
    "15": (-360, 560, 300), "16": (0, -520, 0), "17": (0, 0, 0),
}


def spines():
    """Spine line (two points, mm) per assembly."""
    W = FR.torso()
    out = {
        "01": (W @ Vector((0, 0, 1540)), W @ Vector((0, 0, 1730))),
        "02": (W @ Vector((0, 4, 1490)), W @ Vector((0, 4, 1546))),
        "03": (W @ Vector((0, -20, 1200)), W @ Vector((0, -20, 1500))),
        "04": (W @ Vector((0, 20, 1040)), W @ Vector((0, 20, 1220))),
        "05": (Vector((0, 0, 860)), Vector((0, 0, 1040))),
        "06": (W @ Vector((0, 205, 1150)), W @ Vector((0, 205, 1480))),
    }
    for s, arm_aa, hand_aa, leg_aa, foot_aa in ((1, "07", "09", "11", "13"), (-1, "08", "10", "12", "14")):
        sv, upper, fore, hand = FR.arm(s)
        out[arm_aa] = (W @ sv, W @ hand.translation)
        out[hand_aa] = (W @ hand.translation, W @ (hand @ Vector((0, 0, -190))))
        hip, thigh, knee, shin, ankle, foot = FR.leg(s)
        out[leg_aa] = (hip.translation, ankle.translation)
        out[foot_aa] = (ankle.translation + Vector((0, PR.FOOT_L / 3, -40)), ankle.translation + Vector((0, PR.FOOT_L / 3 - PR.FOOT_L, -40)))
    cn = FR.cannon()
    out["15"] = (cn @ Vector((0, 0, -PR.BREECH_AFT)), cn @ Vector((0, 0, PR.BREECH_FWD + PR.BARREL_L)))
    return out


def _centre(ob):
    lo, hi = C.bounds_mm([ob])
    return (lo + hi) / 2, (hi - lo)


def apply(gain=1.15, base=28.0, along=0.35):
    """Create assembly empties, parent parts, and write explode properties."""
    sp = spines()
    by_asm = {}
    for ob in parts.all_parts():
        by_asm.setdefault(ob["rj28_assembly"], []).append(ob)
    roots = {}
    for aa, obs in sorted(by_asm.items()):
        title = parts.ASSEMBLIES[aa].replace(", ", "_").replace(" ", "_")
        root = bpy.data.objects.get(f"RJ28-{aa}_{title}")
        if root is None:
            root = bpy.data.objects.new(f"RJ28-{aa}_{title}", None)
            root.empty_display_size = 0.05
            obs[0].users_collection[0].objects.link(root)
        root["rj28_assembly"] = aa
        root["rj28_title"] = parts.ASSEMBLIES[aa]
        root["explode_stage"] = 1
        root["explode_offset"] = [v * MM for v in ASM_OFFSET[aa]]
        roots[aa] = root
        p0, p1 = sp.get(aa, (Vector((0, 0, 1000)), Vector((0, 0, 1100))))
        axis = (p1 - p0).normalized()
        mid = (p0 + p1) / 2
        for ob in obs:
            if ob.type != "MESH" or len(ob.data.vertices) == 0:
                continue
            ob.parent = root
            c, size = _centre(ob)
            rel = c - p0
            t = rel.dot(axis)
            radial = rel - axis * t
            r = radial.length
            if "explode_dir" in ob:
                d = Vector(ob["explode_dir"]).normalized()
                off = d * (base + r * gain * 0.6 + max(size) * 0.25)
            elif r < 12.0:
                off = Vector((0, 0, 0))
            else:
                off = radial.normalized() * (base + r * gain)
            off += axis * ((c - mid).dot(axis) * along)
            ob["explode_stage"] = 2
            ob["explode_offset"] = [v * MM for v in off]
    # decals travel with the part they are on
    for ob in parts.all_parts():
        host = bpy.data.objects.get(ob.get("rj28_host", ""))
        if host is not None and "explode_offset" in host:
            ob.parent = roots.get(host["rj28_assembly"], ob.parent)
            ob["explode_offset"] = list(host["explode_offset"])
            ob["rj28_explode_with"] = host["rj28_assembly"]
    return roots


def pose(amount=1.0):
    """Preview: move everything to the exploded state (0..1). Stage 1 plays over
    0..0.5, stage 2 over 0.5..1, as on the site."""
    a1 = min(max(amount * 2.0, 0.0), 1.0)
    a2 = min(max(amount * 2.0 - 1.0, 0.0), 1.0)
    for ob in bpy.data.objects:
        if "explode_offset" not in ob:
            continue
        off = Vector(ob["explode_offset"])
        if ob.get("explode_stage") == 1:
            ob.location = off * a1
        else:
            ob.location = off * a2
    bpy.context.view_layer.update()
