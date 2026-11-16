"""Whole-robot build. Each assembly lives in rj28/assemblies/<name>.py and
exposes build(s=None) -> Asm (s = +1 left / -1 right for sided assemblies).

While an assembly has no module yet, or when building only a few, the
blockout volumes stand in for the rest so every assembly is judged in context.
"""
import importlib

import bpy

from . import materials as M, parts, poses
from .lib import core as C, fittings as F

# (module, side, assembly number, blockout zones it replaces)
PLAN = [
    ("head", None, "01", {"head", "cap"}),
    ("neck", None, "02", {"neck"}),
    ("thorax", None, "03", {"thorax"}),
    ("abdomen", None, "04", {"abdomen"}),
    ("pelvis", None, "05", {"pelvis"}),
    ("backpack", None, "06", {"backpack"}),
    ("arm", 1, "07", {"arm_L", "pauldron_L"}),
    ("arm", -1, "08", {"arm_R", "pauldron_R"}),
    ("hand", 1, "09", {"hand_L"}),
    ("hand", -1, "10", {"hand_R"}),
    ("leg", 1, "11", {"leg_L"}),
    ("leg", -1, "12", {"leg_R"}),
    ("foot", 1, "13", {"foot_L"}),
    ("foot", -1, "14", {"foot_R"}),
    ("mount", None, "15", {"mount_fix", "mount_trav", "mount_elev", "mount_pin", "lock"}),
    ("harness", None, "16", set()),
    ("marks", None, "17", set()),
]


def _module(name):
    try:
        return importlib.import_module(f"rj28.assemblies.{name}")
    except ModuleNotFoundError as e:
        if e.name == f"rj28.assemblies.{name}":
            return None
        raise


def build(only=None, context=True):
    """Build the robot. only: set of module names to build in detail (default all
    that exist). context: fill everything else with blockout stand-ins."""
    from .assemblies import blockout
    C.reset_scene()
    M.reset()
    parts.reset()
    F.DECALS.clear()
    todo = [(m, s, aa, z) for m, s, aa, z in PLAN if (only is None or m in only) and _module(m) is not None]
    replaced = set().union(*[z for *_, z in todo]) if todo else set()
    if context:
        b = blockout.Blk()
        blockout.build_into(b)
        for ob in [o for o in bpy.data.objects if o.name.startswith("BLK_")]:
            if ob.get("zone") in replaced:
                me = ob.data
                bpy.data.objects.remove(ob)
                if me.users == 0:
                    bpy.data.meshes.remove(me)
    built = {}
    for m, s, aa, _ in todo:
        mod = _module(m)
        a = mod.build(s) if s is not None else mod.build()
        built[aa] = a
        print(f"ASM {aa} {a.title}: {len(a.parts)} parts")
    poses.set_mount("stowed")
    print(f"PARTS {len(parts.all_parts())}")
    return built
