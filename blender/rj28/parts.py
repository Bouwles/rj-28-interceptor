"""Part registry. Every object on the robot is created through an Asm, which
numbers it RJ28-AA-NNN, names it, and records what it is for.

    a = Asm("01")
    a.add("Skull_Frame", bm, "Carries the cap, faceplate and sensors.", "alu", matrix)
    a.take(obj, "Neck_Ring", "Yaw bearing race bolted to the thorax.")

Numbers follow creation order, so the build is deterministic.
"""
import bpy

from . import materials as M
from .lib import core as C

ASSEMBLIES = {
    "01": "Head and cap", "02": "Neck", "03": "Thorax", "04": "Abdomen and spine", "05": "Pelvis",
    "06": "Backpack", "07": "Arm, left", "08": "Arm, right", "09": "Hand, left", "10": "Hand, right",
    "11": "Leg, left", "12": "Leg, right", "13": "Foot, left", "14": "Foot, right",
    "15": "Interceptor mount", "16": "Harness", "17": "Markings",
}
# default zone tag per assembly (zones drive the mount sweep check and the blockout stand-ins)
ZONE = {
    "01": "head", "02": "neck", "03": "thorax", "04": "abdomen", "05": "pelvis", "06": "backpack",
    "07": "arm_L", "08": "arm_R", "09": "hand_L", "10": "hand_R", "11": "leg_L", "12": "leg_R",
    "13": "foot_L", "14": "foot_R", "15": "mount_fix", "16": "harness", "17": "markings",
}
ACTUATOR_FN = {
    "body": "Roller-screw actuator body with motor for the {what}.",
    "rod": "Polished actuator rod and rod-end eye for the {what}.",
    "bellows": "Rubber bellows keeping grit off the {what} actuator rod.",
    "clevis_a": "Fork bracket anchoring the body end of the {what} actuator.",
    "clevis_b": "Fork bracket taking the rod-end load of the {what} actuator.",
    "pin_a": "Clevis pin with retaining clip, body end of the {what} actuator.",
    "pin_b": "Clevis pin with retaining clip, rod end of the {what} actuator.",
}
ROTARY_FN = {
    "housing": "Frameless motor and reduction housing for {what}.",
    "flange": "Output flange of the {what} actuator.",
    "bolts": "Screws clamping the {what} output flange.",
    "connector": "Power and encoder connector for the {what} actuator.",
}
SLEW_FN = {
    "outer": "Fixed outer race of the {what} slewing ring.",
    "inner": "Rotating inner race of the {what} slewing ring.",
    "seal": "Lip seal between the races of the {what} slewing ring.",
    "bolts_inner": "Screws fixing the inner race of the {what} slewing ring.",
    "bolts_outer": "Screws fixing the outer race of the {what} slewing ring.",
}
SUFFIX = {"body": "Act_Body", "rod": "Act_Rod", "bellows": "Act_Bellows", "clevis_a": "Clevis_A", "clevis_b": "Clevis_B",
          "pin_a": "Pin_A", "pin_b": "Pin_B", "housing": "Housing", "flange": "Flange", "bolts": "Flange_Bolts",
          "connector": "Connector", "outer": "Outer_Race", "inner": "Inner_Race", "seal": "Seal",
          "bolts_inner": "Inner_Bolts", "bolts_outer": "Outer_Bolts"}

REGISTRY = []


def reset():
    REGISTRY.clear()


class Asm:
    def __init__(self, aa):
        self.aa = aa
        self.title = ASSEMBLIES[aa]
        self.n = 0
        slug = self.title.replace(", ", "_").replace(" ", "_")
        self.coll = C.coll(f"RJ28-{aa}_{slug}")
        self.parts = []

    def _register(self, ob, short, fn, zone, group, ex):
        assert fn and fn[0].isupper() and fn.endswith("."), f"{short}: function must be one plain sentence"
        self.n += 1
        num = f"RJ28-{self.aa}-{self.n:03d}"
        ob.name = f"{num}_{short}"
        if ob.data is not None:
            ob.data.name = ob.name
        ob["rj28_number"] = num
        ob["rj28_name"] = short.replace("_", " ")
        ob["rj28_assembly"] = self.aa
        ob["rj28_function"] = fn
        ob["zone"] = zone or ZONE[self.aa]
        if group:
            ob["mount_group"] = group
        if ex is not None:
            ob["explode_dir"] = [float(v) for v in ex]
        if ob.type == "MESH" and ob.data.materials and ob.data.materials[0] is not None:
            ob["rj28_material"] = ob.data.materials[0].get("rj28_key", "")
        for c in list(ob.users_collection):
            if c is not self.coll:
                c.objects.unlink(ob)
        if ob.name not in self.coll.objects:
            self.coll.objects.link(ob)
        self.parts.append(ob)
        REGISTRY.append(ob)
        return ob

    def add(self, short, bm, fn, mat="armour", matrix=None, bevel=1.0, seg=2, zone=None, group=None, ex=None):
        """New part from a bmesh (mm, local) placed by matrix (mm, world)."""
        mats = [M.get(k) for k in mat] if isinstance(mat, (list, tuple)) else M.get(mat)
        ob = C.obj_from_bm("_new", bm, matrix, self.coll, mats, bevel=bevel, segments=seg)
        return self._register(ob, short, fn, zone, group, ex)

    def take(self, ob, short, fn, zone=None, group=None, ex=None):
        """Adopt an object made by a lib helper."""
        return self._register(ob, short, fn, zone, group, ex)

    def take_set(self, d, short, what, table, zone=None, group=None, ex=None):
        out = {}
        for key, ob in d.items():
            out[key] = self._register(ob, f"{short}_{SUFFIX[key]}", table[key].format(what=what), zone, group, ex)
        return out

    def take_actuator(self, d, short, what, **kw):
        """Adopt the dict from mech.linear_actuator (7 parts)."""
        return self.take_set(d, short, what, ACTUATOR_FN, **kw)

    def take_rotary(self, d, short, what, **kw):
        """Adopt the dict from mech.rotary_actuator (4 parts)."""
        return self.take_set(d, short, what, ROTARY_FN, **kw)

    def take_slew(self, d, short, what, **kw):
        """Adopt the dict from mech.slewing_ring (5 parts)."""
        return self.take_set(d, short, what, SLEW_FN, **kw)


def raw(bm, matrix=None, mat="armour", bevel=1.0, seg=2):
    """Unregistered working object (to be cut, split and then adopted with Asm.take)."""
    mats = [M.get(k) for k in mat] if isinstance(mat, (list, tuple)) else M.get(mat)
    return C.obj_from_bm("_raw", bm, matrix, None, mats, bevel=bevel, segments=seg)


def all_parts():
    return [o for o in bpy.data.objects if "rj28_number" in o]
