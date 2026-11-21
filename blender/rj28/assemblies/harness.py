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
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .. import frames as FR, params as PR, parts, poses
from ..lib import core as C, detail as D, harness as H, mech, prims as P
from ..lib.core import MM, T, R, frame
from ..parts import Asm
from . import leg as LEG


def _dir(m, v):
    return (m.to_3x3() @ Vector(v)).normalized()


class Surface:
    """The outside of one or more assemblies, for laying a run on it."""

    def __init__(self, *aas):
        verts, tris = [], []
        for ob in parts.all_parts():
            if ob.type == "MESH" and ob.get("rj28_assembly") in aas and len(ob.data.vertices):
                v, t = poses._tris(ob)
                off = len(verts)
                verts += v
                tris += [(a + off, b + off, c + off) for a, b, c in t]
        self.bvh = BVHTree.FromPolygons(verts, tris) if tris else None

    def hug(self, p, toward, r):
        """Point on the run's centreline where a run of radius r, coming from p and
        pressed towards `toward`, lies on the surface; and the direction into the surface."""
        p, toward = Vector(p), Vector(toward)
        d = (toward - p).normalized()
        hit = self.bvh.ray_cast(p * MM, d, 0.6) if self.bvh else (None,)
        if hit[0] is None:
            return p, d
        return hit[0] / MM - d * (r + 1.5), d


def tail_of(ob):
    """Where a cable leaves a lib connector: (point, direction), found from its mesh
    (the thin boot end of its long axis)."""
    v = np.array([tuple(q.co) for q in ob.data.vertices]) / MM
    c = v.mean(axis=0)
    ax = np.linalg.eigh(np.cov((v - c).T))[1][:, -1]
    t = (v - c) @ ax

    def radius(sel):
        w = v[sel] - c
        return np.linalg.norm(w - np.outer(w @ ax, ax), axis=1).max()

    lo_thin = radius(t < np.percentile(t, 15)) < radius(t > np.percentile(t, 85))
    tip = v[t.argmin()] if lo_thin else v[t.argmax()]
    d = -ax if lo_thin else ax
    axis_pt = c + ax * ((tip - c) @ ax)
    return Vector(axis_pt.tolist()), Vector(d.tolist())


def connector(aa, short):
    for o in parts.all_parts():
        if o.get("rj28_assembly") == aa and o["rj28_name"].replace(" ", "_") == short:
            return o
    return None


class Runs:
    """Small helper that keeps the part naming and function sentences uniform."""

    def __init__(self, a):
        self.a = a

    def cable(self, name, pts, what, r=3.6, sag=0.0, clips=None, clip_dir=None, spacing=100.0, group=None, zone=None):
        self.a.take(H.cable("_c", pts, r, sag=sag), name, f"Braided cable: {what}.", group=group, zone=zone)
        if clips:
            self.a.take(H.p_clips("_p", clips, r, clip_dir, spacing=spacing), name + "_Clips",
                        f"P-clips holding the {what} cable to the structure.", group=group, zone=zone)

    def loom(self, name, pts, what, strands=4, r=2.1, clips=None, clip_dir=None, spacing=100.0, flip=False):
        self.a.take(H.loom("_l", pts, strands, r), name, f"Loom of {strands} braided cables bound with ties: {what}.")
        if clips:
            self.a.take(H.p_clips("_p", clips, H.loom_radius(strands, r), clip_dir, spacing=spacing, flip=flip), name + "_Clips",
                        f"P-clips holding the {what} loom to the structure.")

    def hose(self, name, pts, what, r=6.0, sag=0.0, clips=None, clip_dir=None, spacing=110.0):
        d = H.hose("_h", pts, r, sag=sag)
        self.a.take(d["hose"], name, f"Coolant hose: {what}.")
        self.a.take(d["ferrules"], name + "_Ferrules", f"Crimped ferrules and swivel nuts on the {what} hose.")
        if clips:
            self.a.take(H.p_clips("_p", clips, r, clip_dir, spacing=spacing), name + "_Clips",
                        f"P-clips holding the {what} hose to the structure.")

    def plug(self, name, point, direction, what, d=11.0, group=None, zone=None):
        """Connector with its flange at `point`; returns where its cable leaves."""
        ob, tail = H.connector("_k", point, direction, d)
        self.a.take(ob, name, f"Connector: {what}.", group=group, zone=zone)
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
    start = rn.plug(f"Leg_Trunk_Plug_{n}", Vector((s * 44, 109, 1012)), (s, 0, 0),
                    f"{('left', 'right')[s < 0]} leg power and signal leaving the pelvis", d=13.0)
    pts = [start, Vector((s * 62, 116, 962)), Lg @ Vector((i * 76, 104, 4)), Th @ Vector((i * 77, 100, -70)),
           Th @ Vector((cx, 74, -150)),
           Th @ Vector((cx, 70, -230)), j_top]
    rn.loom(f"Thigh_Loom_{n}", pts, f"{('left', 'right')[s < 0]} leg power and signal from the pelvis to the knee junction",
            4, 2.1, clips=[Th @ Vector((cx, 74, -150)), Th @ Vector((cx, 70, -230)), Th @ Vector((cx, 70, -296))],
            clip_dir=_dir(Th, (0, -1, 0)), spacing=75.0, flip=s < 0)      # tabs away from the actuators on both legs

    # leads from the two knee actuator ports: down the valley behind and between the bodies, round the back of
    # the inner body below the hamstring guard, into the junction either side of the loom
    Ti = Th.inverted()
    for k, (o, tag) in enumerate(((-s, "Inner"), (s, "Outer"))):
        p0 = Th @ Vector((o * LEG.KNEE_P0[0], LEG.KNEE_P0[1], LEG.KNEE_P0[2]))
        p1 = Sh @ Vector((o * LEG.KNEE_P1[0], LEG.KNEE_P1[1], LEG.KNEE_P1[2]))
        tip, out = mech.actuator_port(p0, p1, 46, 30, LEG.KNEE_STROKE, xk, 200, port=LEG.knee_port(o, tag))
        tail = rn.plug(f"Knee_{tag}_Plug_{n}", tip, out, f"power to the {tag.lower()} knee actuator", d=8.0)
        q = Ti @ p1
        slope = (q.y - LEG.KNEE_P0[1]) / (q.z - LEG.KNEE_P0[2])

        def ay(z):                                   # y of the actuator axes at thigh height z
            return LEG.KNEE_P0[1] + (z - LEG.KNEE_P0[2]) * slope

        zt = (Ti @ tail).z
        end = Th @ Vector((cx + (1 - 2 * k) * i * 9, 70, -306))
        pts = [tail, tail + out * 6 + _dir(Th, (0, 0, -1)) * 13, Th @ Vector((o * 5, ay(zt - 46) + 16 + 5 * k, zt - 46)),
               Th @ Vector((o * 5, ay(-218) + 16 + 5 * k, -218)), Th @ Vector((i * 30, ay(-250) + 33 + 7 * k, -250 + 6 * k)),
               Th @ Vector((i * 71, ay(-276) + 24 + 6 * k, -274 + 6 * k)), end + _dir(Th, (0, 0.25, 1)) * 16, end]
        rn.cable(f"Knee_{tag}_Lead_{n}", pts, f"junction to the {tag.lower()} knee actuator", r=3.2)

    # knee encoder cable: from the gland on the outer housing, over the fork crosshead, to the junction
    xe = LEG.CHEEK_X + 7.0
    Ko = Kn @ T(s * xe, 0, 0) @ R("Y", s * 90)
    gland = Ko @ Vector((0, 43.5, 27.2))
    pts = [gland, gland + _dir(Kn, (0, 1, 0.5)) * 26, Th @ Vector((s * 84.5, 64, -330)), Th @ Vector((s * 84.5, 65, -214)),
           Th @ Vector((s * 62, 64, -201)), Th @ Vector((s * 30, 61.5, -189)), Th @ Vector((i * 40, 61.5, -195)),
           Th @ Vector((cx, 74, -250)), j_top]
    rn.cable(f"Knee_Encoder_Cable_{n}", pts, "knee encoder to the junction", r=2.4)

    # shin loom: junction, service loop behind the knee, into the covered channel, out to the foot
    pts = [j_bot, Th @ Vector((cx + i * 8, 86, -PR.THIGH + 10)), Sh @ Vector((i * 62, 96, -60)),
           Sh @ Vector((i * 26, 64, -150)), Sh @ Vector((0, 50, -184)), Sh @ Vector((0, 38, -208))]      # into the channel mouth
    rn.loom(f"Knee_Loop_{n}", pts, "service loop carrying the shin loom across the knee", 3, 2.05)
    foot_in = rn.plug(f"Foot_Plug_{n}", Ft @ Vector((0, 86, -36)), (0, 0, 1), "sensors and toe drive in the foot", d=12.0)
    pts = [Sh @ Vector((0, 38, -322)), Sh @ Vector((0, 49, -344)), Sh @ Vector((0, 66, -372)), Ft @ Vector((0, 84, 30)),
           foot_in + Vector((0, 0, 6)), foot_in]
    rn.loom(f"Ankle_Loop_{n}", pts, "service loop carrying the foot cables across the ankle", 2, 2.0)

    # leads to the two ankle actuator ports
    for o, tag in ((s, "Outer"), (-s, "Inner")):
        p0 = Sh @ Vector((o * LEG.ANKLE_P0[0], LEG.ANKLE_P0[1], LEG.ANKLE_P0[2]))
        p1 = Ft @ Vector((o * LEG.ANKLE_P1[0], LEG.ANKLE_P1[1], LEG.ANKLE_P1[2]))
        tip, out = mech.actuator_port(p0, p1, 34, 20, 60, xk, 112, port=LEG.ankle_port(o, tag))
        tail = rn.plug(f"Ankle_{tag}_Plug_{n}", tip, out, f"power to the {tag.lower()} ankle actuator", d=8.0)
        zt = (Sh.inverted() @ tail).z                # each stays at its own height until it turns into the channel mouth
        pts = [tail, tail + out * 5 + _dir(Sh, (0, -1, 0)) * 5, Sh @ Vector((-o * 9, 62, zt + 1)), Sh @ Vector((-o * 9, 49, -195)),
               Sh @ Vector((-o * 9, 38, -207))]
        rn.cable(f"Ankle_{tag}_Lead_{n}", pts, f"shin channel to the {tag.lower()} ankle actuator", r=3.0)


def neck(rn):
    """Head loom and one coolant line through the neck gimbal, with slack for all three axes."""
    W = FR.torso()
    top = tail_of(connector("01", "Neck_Connector"))[0]
    for k, x in enumerate((-9, 0, 9)):
        pts = [W @ Vector((-26 + x * 1.6, 96, 1492)), W @ Vector((-26 + x * 1.5, 104, 1512)), W @ Vector((-24 + x * 1.0, 90, 1532)),
               top + Vector((x * 0.5, 6, -14)), top + Vector((x * 0.35, 0, 0))]
        rn.cable(f"Neck_Loom_{k + 1}", pts, "head power and data across the neck", r=2.8)
    pts = [W @ Vector((30, 92, 1492)), W @ Vector((34, 108, 1518)), W @ Vector((30, 96, 1546)), W @ Vector((26, 80, 1566)),
           W @ Vector((22, 64, 1578))]
    rn.hose("Neck_Coolant_Line", pts, "coolant to the head heat spreader", r=4.2)


def arm(rn, s):
    """One arm: a trunk from the thorax flank across the shoulder to a junction on the
    upper arm, leads to the roll, yaw and elbow actuators, a jumper to the forearm roll
    actuator, and a coolant hose to the hand-drive controller in the forearm."""
    n = "L" if s > 0 else "R"
    aa = "07" if s > 0 else "08"
    side = ("left", "right")[s < 0]
    W = FR.torso()
    sv, upper, fore, hand = [W @ m for m in FR.arm(s)]
    surf = Surface(aa)

    def up_pt(x, y, z):
        return upper @ Vector((x, y, z))

    # junction box on the back of the upper arm
    jc, jd = surf.hug(up_pt(-s * 10, 260, -196), up_pt(-s * 10, 0, -196), 0.0)
    back = _dir(upper, (0, 1, 0))
    rn.box(f"Arm_Junction_{n}", frame(jc - jd * 1.5, -jd, _dir(upper, (0, 0, 1))) @ T(0, 0, 0), (44, 26, 15),
           f"splits the {side} arm trunk to the shoulder and elbow actuators")
    j_top = jc - jd * 9 + _dir(upper, (0, 0, 1)) * 24
    j_bot = jc - jd * 9 - _dir(upper, (0, 0, 1)) * 24

    # trunk: plug on the thorax flank, slack across the shoulder, clipped down the upper arm
    t0 = rn.plug(f"Arm_Trunk_Plug_{n}", W @ Vector((s * (PR.SX - 82), 86, 1388)), (s, 0, 0),
                 f"{side} arm power and signal leaving the thorax", d=14.0)
    c1, d1 = surf.hug(up_pt(-s * 10, 260, -146), up_pt(-s * 10, 0, -146), 5.0)
    # on the right the mount hardpoint fills the space behind the shoulder from y = 106: the trunk stays in front of it
    ty = 118 if s > 0 else 93
    pts = [t0, t0 + Vector((s * 26, 16 if s > 0 else 6, -6)), W @ Vector((s * (PR.SX + 6), ty + 2, 1372)),
           up_pt(-s * 16, ty, -112), c1, j_top]
    rn.loom(f"Arm_Trunk_{n}", pts, f"{side} arm trunk from the thorax to the upper-arm junction", 4, 2.1,
            clips=[c1, c1 + (j_top - c1) * 0.6], clip_dir=d1, spacing=60.0)

    # leads to the three actuators whose connectors are on the back of the arm
    # each enters the box end-on, beside the trunk, instead of folding into the end face from behind
    up, lat = _dir(upper, (0, 0, 1)), _dir(upper, (0, 0, 1)).cross(jd)
    for short, tag, bend, off in (("Shoulder_Roll_Connector", "Shoulder_Roll", (s * 0.1, 0.6, -0.8), -8.0),
                                  ("Shoulder_Yaw_Connector", "Shoulder_Yaw", (0.0, 0.7, -0.7), 8.0),
                                  ("Elbow_Connector", "Elbow", (0.0, 0.8, 0.6), 7.0)):
        ob = connector(aa, short)
        if ob is None:
            print("HARNESS SKIP", aa, short)
            continue
        tip, out = tail_of(ob)
        b = Vector(bend).normalized()
        ax = up if tag != "Elbow" else -up
        end = (j_top if tag != "Elbow" else j_bot) + lat * off
        pts = [tip, tip + out * 16 + b * 14, (tip + end) / 2 + back * 34, end + ax * 22 + back * 9, end + ax * 7, end]
        rn.cable(f"{tag}_Lead_{n}", pts, f"junction to the {side} {tag.lower().replace('_', ' ')} actuator", r=3.0)

    # forearm: jumper from the roll actuator into a grommet in the armour; coolant to the controller
    ob = connector(aa, "Forearm_Roll_Connector")
    fsurf_pt, fd = surf.hug(fore @ Vector((0, 260, -150)), fore @ Vector((0, 0, -150)), 0.0)
    rn.a.add(f"Forearm_Grommet_{n}", P.torus(15, 5, 24, 10), "Rubber grommet where the forearm loom passes through the armour.",
             "rubber", frame(fsurf_pt, -fd), bevel=0)
    if ob is not None:
        tip, out = tail_of(ob)
        pts = [tip, tip + out * 20 + _dir(fore, (0, 0, 1)) * 14, fsurf_pt - fd * 30 + _dir(fore, (0, 0, -1)) * 22,
               fsurf_pt - fd * 12, fsurf_pt + fd * 6]
        rn.cable(f"Forearm_Roll_Lead_{n}", pts, f"{side} forearm roll actuator into the forearm loom", r=3.0)
    j_bot = j_bot - lat * 5
    pts = [j_bot, j_bot - up * 8, j_bot + back * 20 - up * 36, up_pt(0, 132, -PR.UPPER_ARM - 30),
           fsurf_pt - fd * 46 + _dir(fore, (0, 0, 1)) * 70, fsurf_pt - fd * 14 + _dir(fore, (0, 0, 1)) * 16, fsurf_pt + fd * 6]
    rn.loom(f"Elbow_Loop_{n}", pts, f"service loop carrying the {side} forearm loom across the elbow", 3, 2.05)
    h0 = W @ Vector((s * (PR.SX - 84), 94, 1356))
    hc, hd = surf.hug(up_pt(s * 26, 260, -200), up_pt(s * 26, 0, -200), 6.0)
    g2, gd = surf.hug(fore @ Vector((s * 30, 260, -120)), fore @ Vector((s * 30, 0, -120)), 0.0)
    pts = [h0, h0 + Vector((s * 30, 22 if s > 0 else 6, -14)), up_pt(s * 20, ty + 6, -120), hc, up_pt(s * 22, 128, -PR.UPPER_ARM - 10),
           g2 - gd * 40 + _dir(fore, (0, 0, 1)) * 50, g2 - gd * 4]
    along = _dir(upper, (0, 0, 1))
    rn.hose(f"Arm_Coolant_Line_{n}", pts, f"coolant to the {side} hand-drive controller", r=5.5,
            clips=[hc + along * 24, hc - along * 24], clip_dir=hd, spacing=60.0)


def mount(rn):
    """Mount: the elevation drive lead with slack for traverse, and the tracker's jumper to the breech."""
    ob = connector("15", "Elevation_Drive_Connector")
    if ob is None:
        print("HARNESS SKIP mount")
        return
    tip, out = tail_of(ob)
    zb = PR.TRUNNION_Z - PR.YOKE_DROP
    plug = Vector((PR.BORE_X + 78, PR.TRUNNION_Y - 66, zb - 54))            # on the hardpoint, clear of the ring
    tail = rn.plug("Mount_Drive_Plug", plug, (0, 0, 1), "elevation drive power from the hardpoint", d=13.0, zone="mount_fix")
    pts = [tip, tip + out * 22 + Vector((30, -10, 6)), Vector((plug.x - 16, plug.y - 24, tip.z - 10)),
           tail + Vector((6, -16, 42)), tail]
    rn.cable("Mount_Drive_Lead", pts, "hardpoint to the elevation drive, with slack for traverse", r=4.0, zone="mount_chain")
    cn = FR.cannon()
    xo = -(PR.BARREL_OD / 2 + 63)
    up = cn.to_3x3() @ Vector((0, 1, 0))
    seat = D.seats_on(connector("15", "Breech_Housing"), [cn @ Vector((-58, PR.BREECH_H / 2 + 30, 34))], up)
    t2 = rn.plug("Tracker_Plug", seat[0].translation if seat else cn @ Vector((-58, PR.BREECH_H / 2, 34)), up,
                 "tracking head signal into the breech", d=10.0, group="elev", zone="mount_elev")
    pts = [cn @ Vector((xo, 30, PR.BREECH_FWD + 20)), cn @ Vector((xo + 8, 72, PR.BREECH_FWD + 8)),
           t2 + up * 14 + Vector((-10, 0, 0)), t2]
    rn.cable("Tracker_Lead", pts, "tracking head to the breech", r=2.8, group="elev", zone="mount_elev")


def pelvis(rn):
    """Hip actuator leads. Each leaves its plug on the pelvis panel straight back, turns outboard in
    a flat rank with its neighbours, passes a saddle clip at the panel edge and only then fans out
    to its actuator. Nothing crosses the centreline. The waist yaw drive rides on the turntable, so
    its lead goes up to the thorax floor instead of across the yaw joint."""
    for s in (1, -1):
        n = "L" if s > 0 else "R"
        aa = "11" if s > 0 else "12"
        rank = Vector((s * 58, 141, 1006))                      # where the three leads pass the saddle clip
        for (asm, short, nm), (x, z), mid in (
                ((aa, "Hip_Pitch_Connector", f"Hip_Pitch_{n}"), (26, 996), [(s * 64, 136, 978)]),
                (("05", f"Hip_Yaw_Connector_{n}", f"Hip_Yaw_{n}"), (26, 1016), [(s * 76, 128, 1030)]),
                (("05", f"Hip_Roll_{n}_Connector", f"Hip_Roll_{n}"), (12, 1006),
                 [(s * 104, 147, 1032), (s * 186, 151, 1032), (s * 238, 154, 1008)])):   # up under the plate rim
            ob = connector(asm, short)
            if ob is None:
                print("HARNESS SKIP", asm, short)
                continue
            tip, out = tail_of(ob)
            tail = rn.plug(f"{nm}_Panel_Plug", Vector((s * x, 126, z)), (0, 1, 0),
                           f"{nm.replace('_', ' ').lower()} at the pelvis panel", d=9.5)
            lane = Vector((rank.x, rank.y, z))
            pts = [tail, tail + Vector((0, 9, 0)), lane - Vector((s * 12, 0, 0)), lane + Vector((s * 4, 0, 0))]
            pts += [Vector(m) for m in mid] + [tip + out * 16, tip]
            rn.cable(f"{nm}_Lead", pts, f"pelvis panel to the {nm.replace('_', ' ').lower()} actuator", r=3.0,
                     clips=[lane - Vector((s * 3, 0, 0)), lane + Vector((s * 3, 0, 0))] if short.startswith("Hip_Yaw") else None,
                     clip_dir=(0, -1, 0))
    ob = connector("04", "Waist_Yaw_Drive_Connector")
    if ob is not None:
        tip, out = tail_of(ob)
        W = FR.torso()
        tail = rn.plug("Waist_Yaw_Thorax_Plug", W @ Vector((30, 84, 1205)), (0, 0, -1),
                       "waist yaw drive at the thorax floor", d=9.5)
        pts = [tip, tip + out * 16, tip + out * 22 + Vector((0, -4, 22)), tail + Vector((14, 6, -16)), tail]
        rn.cable("Waist_Yaw_Lead", pts, "thorax floor to the waist yaw drive", r=3.0)


def build():
    a = Asm("16")
    rn = Runs(a)
    if connector("01", "Neck_Connector") is not None:
        neck(rn)
    for s in (1, -1):
        leg(rn, s)
        if connector("07" if s > 0 else "08", "Shoulder_Roll_Connector") is not None:
            arm(rn, s)
    if connector("05", "Pelvis_Connector_Panel") is not None:
        pelvis(rn)
    mount(rn)
    return a


def review(a, out, tag=""):
    from .. import parts, review as RV
    legs = [o for o in parts.all_parts() if o.get("rj28_assembly") in ("11", "16") and o.type == "MESH"]
    kc = FR.leg(1)[2].translation
    RV.closeup(legs, out / f"16_harness_leg_inner{tag}.jpg", "16 harness, left leg inner side", (-1.0, 0.75, 0.15), "clay",
               target=kc + Vector((0, 20, 60)), dist=1.9, isolate=True, res=(1100, 1500))
    RV.closeup(legs, out / f"16_harness_leg_rear_final{tag}.jpg", "16 harness, left leg rear", (0.35, 1.0, 0.12), "final",
               target=kc + Vector((0, 20, 60)), dist=1.9, isolate=True, res=(1100, 1500))
    RV.closeup(legs, out / f"16_harness_thigh_loom{tag}.jpg", "16 harness, thigh loom and knee junction", (-0.8, 0.9, 0.1), "final",
               target=kc + Vector((-60, 60, 130)), dist=0.5, isolate=True)
    arms = [o for o in parts.all_parts() if o.get("rj28_assembly") in ("07", "16") and o.type == "MESH"]
    if any(o.get("rj28_assembly") == "07" for o in arms):
        ec = (FR.torso() @ FR.arm(1)[1]) @ Vector((0, 60, -200))
        RV.closeup(arms, out / f"16_harness_arm_rear{tag}.jpg", "16 harness, left arm rear", (0.25, 1.0, 0.2), "final",
                   target=ec, dist=0.55, isolate=True, res=(1100, 1400))
