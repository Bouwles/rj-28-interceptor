"""Assembly 17: markings. Sparse and functional, like real equipment.

White and ice cyan only (plus dark engraving on the data plate), set in
Saira Stencil One. Every label sits on the part it describes, is draped onto
that part's surface, and carries rj28_host so it travels with the part in
the exploded view. All text that states a number takes it from params or
from the part registry, never from a literal here.
"""
import math

from mathutils import Vector

from .. import frames as FR, markings, params as PR, parts, render as RD
from ..lib import core as C, detail as D, fittings as F
from ..parts import Asm
from . import head as HEAD


def find(aa, short):
    """Part of assembly aa whose short name matches (or None)."""
    for o in parts.all_parts():
        if o.get("rj28_assembly") == aa and o["rj28_name"].replace(" ", "_") == short:
            return o
    return None


class Marks:
    def __init__(self, a):
        self.a = a
        self.n = 0

    def put(self, host, text, height, point, normal, reading, color="white", what=None, name=None):
        """Drape `text` onto host at `point` (mm). normal: outward direction at that spot;
        reading: the direction the text reads in."""
        if host is None:
            print("MARK SKIP", text)
            return None
        seats = D.seats_on(host, [Vector(point)], normal, x_hint=reading)
        if not seats:
            print("MARK MISS", text, host.name)
            return None
        ob = F.label("_m", text, height, seats[0], color, target=host)
        ob["rj28_host"] = host.name
        ob["rj28_material"] = "decal"
        ob["rj28_text"] = text
        self.n += 1
        nm = name or ("Mark_" + "".join(ch if ch.isalnum() else "_" for ch in text).strip("_"))
        self.a.take(ob, f"{nm}_{self.n:02d}", what or f"Stencilled marking: {text}.")
        return ob


def build():
    a = Asm("17")
    mk = Marks(a)
    W = FR.torso()
    up = Vector((0, 0, 1))

    # unit identity: 28 on the cap's left panel, RJ-28 on the left shoulder and the right shin
    tilt, h, Cm = HEAD.cap_frame()
    crown = find("01", "Cap_Crown")
    p = Cm @ Vector(HEAD.crown_pt(math.radians(-8), 40.0, h, 20.0))
    n = (Cm.to_3x3() @ Vector((1, -0.12, 0.35))).normalized()
    mk.put(crown, "28", 26.0, p, n, (0, 1, 0), what="Unit number on the cap's left panel.", name="Cap_Number")
    skirt = find("07", "Pauldron_Shell")
    mk.put(skirt, "RJ-28", 34.0, W @ Vector((PR.PAULDRON_L_OUT + 60, -6, 1438)), (1, 0, 0), (0, 1, 0),
           what="Unit designation on the left shoulder armour.", name="Shoulder_Designation")
    hip, thigh, knee, shin, ankle, foot = FR.leg(-1)
    shin_o = find("12", "Shin_Armour_Outer")
    # reads down the shin: the outer panel is taller than it is deep
    mk.put(shin_o, "RJ-28", 17.0, shin @ Vector((-200, -8, -235)), (shin.to_3x3() @ Vector((-1, 0, 0))),
           (shin.to_3x3() @ Vector((0, 0, -1))),
           what="Unit designation on the right shin.", name="Shin_Designation")
    stern = find("03", "Sternum_Panel") or find("03", "Sternum")
    mk.put(stern, "INTERCEPTOR", 9.0, W @ Vector((0, -400, 1452)), (0, -1, 0), (1, 0, 0), "cyan",
           what="Type name on the sternum panel.", name="Sternum_Type_Name")

    # safety and service labels where they belong
    for s, aa_leg, aa_foot in ((1, "11", "13"), (-1, "12", "14")):
        hip, thigh, knee, shin, ankle, foot = FR.leg(s)
        toe = find(aa_foot, "Toe_Armour")
        mk.put(toe, "NO STEP", 8.0, foot @ Vector((0, PR.FOOT_L / 3 - PR.FOOT_L + 62, 200)), up,
               (foot.to_3x3() @ Vector((1, 0, 0))), what="Warning on the hinged toe section: not a step.")
        low = find(aa_leg, "Thigh_Armour_Lower")
        mk.put(low, "PINCH POINT", 5.0, thigh @ Vector((s * 260, -18, -286)), (thigh.to_3x3() @ Vector((s, 0, 0))),
               (thigh.to_3x3() @ Vector((0, s, 0))), "cyan", what="Warning beside the knee joint.")
        door = find(aa_leg, "Thigh_Hatch")
        if door is not None:
            mk.put(find(aa_leg, "Thigh_Armour_Upper"), door["rj28_number"], 4.2, thigh @ Vector((s * 260, -22, -208)),
                   (thigh.to_3x3() @ Vector((s, 0, 0))), (thigh.to_3x3() @ Vector((0, s, 0))),
                   what="Panel reference under the thigh service hatch.", name="Panel_Ref_Thigh")
    for s, aa_arm in ((1, "07"), (-1, "08")):
        sv, upper, fore, hand = [W @ m for m in FR.arm(s)]
        outer = find(aa_arm, "Forearm_Armour_Outer")
        mk.put(outer, "PINCH POINT", 6.0, fore @ Vector((s * 260, 10, -128)), (fore.to_3x3() @ Vector((s, 0, 0))),
               (fore.to_3x3() @ Vector((0, s, 0))), "cyan", what="Warning beside the elbow joint.")
    for s in (1, -1):
        yoke = find("03", f"Shoulder_Yoke_{'L' if s > 0 else 'R'}") or find("03", "Thorax_Frame")
        mk.put(yoke, "LIFT POINT", 5.0, W @ Vector((s * (PR.SX - 132), 4, 1700)), up, (1, 0, 0),
               what="Marks the lifting eye on the shoulder yoke.")
    door = find("06", "Battery_Service_Door")
    if door is not None:
        lo, hi = C.bounds_mm([door])
        c = (lo + hi) / 2
        mk.put(door, f"HV {PR.PACK_VOLTAGE:.0f} V", 8.0, Vector((hi.x + 120, c.y, c.z + 30)), (1, 0, 0), (0, 1, 0),
               what="High-voltage warning on the battery service door.")
    rear = find("06", "Backpack_Rear_Panel")
    if rear is not None:
        lo, hi = C.bounds_mm([rear])
        mk.put(rear, "HOT SURFACE", 5.5, Vector((lo.x + 62, hi.y + 120, hi.z - 15)), (0, 1, 0), (-1, 0, 0), "cyan",
               what="Warning above the blower exhausts.")
    plate = find("03", "Data_Plate")
    if plate is not None:
        lo, hi = C.bounds_mm([plate])
        c = (lo + hi) / 2
        lines = ("RJ-28 INTERCEPTOR", f"SERIAL {PR.SERIAL}", f"MASS {PR.MASS_READY_KG:.0f} KG   {PR.PACK_VOLTAGE:.0f} V DC")
        for i, text in enumerate(lines):
            mk.put(plate, text, 3.4, Vector((c.x, lo.y - 200, c.z + 7.5 - i * 7.5)), (0, -1, 0), (1, 0, 0), "dark",
                   what="Engraved line on the thorax data plate.", name="Data_Plate_Line")
    markings.build_atlas(RD.ROOT / "blender" / "out" / "decals.png", 4096)
    return a
