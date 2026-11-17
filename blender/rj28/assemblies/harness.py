"""Assembly 16: harness. Cables, coolant hoses, connectors and clips.

Rules: every run ends in a connector or a ferrule at both ends, is clipped
every 80 to 120 mm where it lies on structure, and carries a service loop
across every joint that moves. Nothing is dead straight and nothing floats.
Cables are braided (radius 3 to 5); coolant lines are a little thicker with
crimped ferrules.

Routes are written against the frames of the assembly they run on, so they
follow if a dimension changes.
"""
import bmesh
from mathutils import Vector

from .. import frames as FR, params as PR
from ..lib import core as C, harness as H, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm
from . import leg as LEG


def _dir(m, v):
    return (m.to_3x3() @ Vector(v)).normalized()


class Runs:
    """Small helper that keeps the part naming and function sentences uniform."""

    def __init__(self, a):
        self.a = a

    def cable(self, name, pts, what, r=3.6, sag=0.0, clips=None, clip_dir=None, spacing=100.0):
        self.a.take(H.cable("_c", pts, r, sag=sag), name, f"Braided cable: {what}.")
        if clips:
            self.a.take(H.p_clips("_p", clips, r, clip_dir, spacing=spacing), name + "_Clips",
                        f"P-clips holding the {what} cable to the structure.")

    def hose(self, name, pts, what, r=6.0, sag=0.0, clips=None, clip_dir=None, spacing=110.0):
        d = H.hose("_h", pts, r, sag=sag)
        self.a.take(d["hose"], name, f"Coolant hose: {what}.")
        self.a.take(d["ferrules"], name + "_Ferrules", f"Crimped ferrules and swivel nuts on the {what} hose.")
        if clips:
            self.a.take(H.p_clips("_p", clips, r, clip_dir, spacing=spacing), name + "_Clips",
                        f"P-clips holding the {what} hose to the structure.")

    def plug(self, name, point, direction, what, d=11.0):
        """Connector with its flange at `point`; returns where its cable leaves."""
        ob, tail = H.connector("_k", point, direction, d)
        self.a.take(ob, name, f"Connector: {what}.")
        return tail

    def box(self, name, matrix, size, what):
        bm = P.prism(P.chamfer_poly(P.rrect(size[0], size[1]), 3), 0, size[2])
        return self.a.add(name, bm, f"Junction box: {what}.", "alu", matrix, bevel=0.6)


def leg(rn, s):
    """Power and signal down one leg: thigh loom to a junction at the knee, leads to the
    four actuators, encoder cable, and a shin loom through the covered channel to the foot."""
    n = "L" if s > 0 else "R"
    Lg, Th, Kn, Sh, An, Ft = FR.leg(s)
    xk = _dir(Th, (1, 0, 0))
    i = -s                                           # inner side of this leg
    cx = i * LEG.CHEEK_X                             # inner cheek of the knee fork

    # junction box on the rear edge of the inner cheek, above the knee
    jb = Th @ T(cx, 61, -330) @ R("X", -90)
    rn.box(f"Knee_Junction_{n}", jb, (26, 46, 16), f"splits the {('left', 'right')[s < 0]} leg loom to the knee and ankle actuators")
    j_top = Th @ Vector((cx, 70, -306))
    j_bot = Th @ Vector((cx, 70, -354))

    # thigh loom: from the hip, behind the inner hanger, down the rear edge of the inner cheek
    start = Lg @ Vector((i * 74, 78, 52))
    pts = [start, Lg @ Vector((i * 76, 104, 4)), Th @ Vector((i * 77, 100, -70)), Th @ Vector((cx, 74, -150)),
           Th @ Vector((cx, 70, -230)), j_top]
    rn.cable(f"Thigh_Loom_{n}", pts, f"{('left', 'right')[s < 0]} leg power and signal from the pelvis to the knee junction",
             r=5.0, clips=[Th @ Vector((cx, 74, -150)), Th @ Vector((cx, 70, -230)), Th @ Vector((cx, 70, -296))],
             clip_dir=_dir(Th, (0, -1, 0)), spacing=75.0)

    # leads up to the two knee actuator ports (under the anchor block)
    for o, tag in ((s, "Outer"), (-s, "Inner")):
        p0 = Th @ Vector((o * LEG.KNEE_P0[0], LEG.KNEE_P0[1], LEG.KNEE_P0[2]))
        p1 = Sh @ Vector((o * LEG.KNEE_P1[0], LEG.KNEE_P1[1], LEG.KNEE_P1[2]))
        tip, out = mech.actuator_port(p0, p1, 46, 30, LEG.KNEE_STROKE, xk, 200)
        tail = rn.plug(f"Knee_{tag}_Plug_{n}", tip, out, f"power to the {tag.lower()} knee actuator")
        mid = tail + out * 14 + _dir(Th, (i * (1 if o == s else 0.2), 0, -0.4)) * 30
        pts = [tail, mid, Th @ Vector((i * 60, 62, -200)), Th @ Vector((cx, 72, -262)), j_top + _dir(Th, (0, 1, 0)) * 3]
        rn.cable(f"Knee_{tag}_Lead_{n}", pts, f"junction to the {tag.lower()} knee actuator", r=3.2)

    # knee encoder cable: from the gland on the outer housing, over the fork crosshead, to the junction
    xe = LEG.CHEEK_X + 7.0
    Ko = Kn @ T(s * xe, 0, 0) @ R("Y", s * 90)
    gland = Ko @ Vector((0, 43.5, 27.2))
    pts = [gland, gland + _dir(Kn, (0, 1, 0.5)) * 26, Th @ Vector((s * 84, 64, -330)), Th @ Vector((s * 80, 56, -210)),
           Th @ Vector((s * 30, 54, -186)), Th @ Vector((i * 40, 56, -196)), Th @ Vector((cx, 74, -250)), j_top]
    rn.cable(f"Knee_Encoder_Cable_{n}", pts, "knee encoder to the junction", r=2.4)

    # shin loom: junction, service loop behind the knee, into the covered channel, out to the foot
    pts = [j_bot, Th @ Vector((cx + i * 8, 86, -PR.THIGH + 10)), Sh @ Vector((i * 62, 96, -60)),
           Sh @ Vector((i * 26, 64, -150)), Sh @ Vector((0, 52, -192))]
    rn.cable(f"Knee_Loop_{n}", pts, "service loop carrying the shin loom across the knee", r=4.4)
    foot_in = rn.plug(f"Foot_Plug_{n}", Ft @ Vector((0, 86, -36)), (0, 0, 1), "sensors and toe drive in the foot", d=12.0)
    pts = [Sh @ Vector((0, 52, -338)), Sh @ Vector((0, 66, -372)), Ft @ Vector((0, 84, 30)), foot_in + Vector((0, 0, 6)), foot_in]
    rn.cable(f"Ankle_Loop_{n}", pts, "service loop carrying the foot cable across the ankle", r=4.0)

    # leads to the two ankle actuator ports
    for o, tag in ((s, "Outer"), (-s, "Inner")):
        p0 = Sh @ Vector((o * LEG.ANKLE_P0[0], LEG.ANKLE_P0[1], LEG.ANKLE_P0[2]))
        p1 = Ft @ Vector((o * LEG.ANKLE_P1[0], LEG.ANKLE_P1[1], LEG.ANKLE_P1[2]))
        tip, out = mech.actuator_port(p0, p1, 34, 20, 60, xk, 112)
        tail = rn.plug(f"Ankle_{tag}_Plug_{n}", tip, out, f"power to the {tag.lower()} ankle actuator", d=9.0)
        pts = [tail, tail + out * 10 + _dir(Sh, (-o * 0.5, 0, 0.6)) * 16, Sh @ Vector((o * 14, 58, -186)),
               Sh @ Vector((0, 53, -196))]
        rn.cable(f"Ankle_{tag}_Lead_{n}", pts, f"shin channel to the {tag.lower()} ankle actuator", r=3.0)


def neck(rn):
    """Head loom and one coolant line through the neck gimbal, with slack for all three axes."""
    W = FR.torso()
    top = W @ Vector((0, 58, 1540 - 16 * 2.3 + 1))               # tail of the head's neck connector
    for k, x in enumerate((-9, 0, 9)):
        pts = [W @ Vector((x * 2.2, 96, 1492)), W @ Vector((x * 2.0, 104, 1512)), W @ Vector((x * 1.2, 92, 1532)),
               top + Vector((x * 0.5, 6, -14)), top + Vector((x * 0.35, 0, 0))]
        rn.cable(f"Neck_Loom_{k + 1}", pts, "head power and data across the neck", r=2.8)
    pts = [W @ Vector((30, 92, 1492)), W @ Vector((34, 108, 1518)), W @ Vector((30, 96, 1546)), W @ Vector((26, 80, 1566)),
           W @ Vector((22, 64, 1578))]
    rn.hose("Neck_Coolant_Line", pts, "coolant to the head heat spreader", r=4.2)


def build():
    a = Asm("16")
    rn = Runs(a)
    neck(rn)
    for s in (1, -1):
        leg(rn, s)
    return a


def review(a, out, tag=""):
    from .. import parts, review as RV
    legs = [o for o in parts.all_parts() if o.get("rj28_assembly") in ("11", "16") and o.type == "MESH"]
    kc = FR.leg(1)[2].translation
    RV.closeup(legs, out / f"16_harness_leg_inner{tag}.jpg", "16 harness, left leg inner side", (-1.0, 0.75, 0.15), "clay",
               target=kc + Vector((0, 20, 60)), dist=1.9, isolate=True, res=(1100, 1500))
    RV.closeup(legs, out / f"16_harness_leg_rear_final{tag}.jpg", "16 harness, left leg rear", (0.35, 1.0, 0.12), "final",
               target=kc + Vector((0, 20, 60)), dist=1.9, isolate=True, res=(1100, 1500))
