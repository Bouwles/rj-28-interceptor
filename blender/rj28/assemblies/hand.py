"""Assemblies 09 / 10: hand, left / right.

Two-axis wrist under a rubber boot, palm frame with armoured knuckle plate,
thumb and three fingers. Every finger segment is its own part; the knuckles of
each finger are coupled by link bars, so one tendon closes the whole finger.

Six degrees of freedom: thumb opposition, thumb flexion, one driven flexion per
finger, and a ganged splay of the three fingers.

Frame (rj28.frames.arm hand frame, with the torso offset): origin at the wrist
centre, -Z towards the fingers, +Y to the rear, +X lateral. The back of the
hand faces s * X (outward), the palm faces the body, the thumb points forward.
The forearm roll output flange is at z = +17; the hand bolts on there.
"""
import math

import bmesh
from mathutils import Vector

from .. import frames as FR
from ..lib import armour as A, core as C, detail as D, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm

FINGERS = (("Index", -38.0), ("Middle", 0.0), ("Outer", 38.0))
SEGS = ((44.0, 32.0, 28.0), (32.0, 29.0, 36.0), (25.0, 26.0, 30.0))     # length, thickness, curl in the neutral pose
TIP = 20.0
WIDTH = 28.0


def _dir(m, v):
    return (m.to_3x3() @ Vector(v)).normalized()


def _segment_bm(ln, th, th_next, s, width=WIDTH):
    """Finger segment in its joint frame: knuckle axis Y through the origin, body
    running to (0, 0, -ln). A central tongue sits in the fork of the segment before
    it; two side cheeks form the fork for the segment after it, so no two segments
    share a face. Slot 0 body, slot 1 dorsal armour cap, slot 2 pin."""
    r0, r1 = th / 2, th_next / 2
    core_w = width - 9.0
    arc0 = [(r0 * math.cos(math.radians(a)), r0 * math.sin(math.radians(a))) for a in range(0, 181, 15)]
    arc1 = [(r1 * math.cos(math.radians(a)), -ln + r1 * math.sin(math.radians(a))) for a in range(180, 361, 15)]
    bm = P.prism(arc0 + arc1, -core_w / 2, core_w / 2)
    bm.transform(R("X", 90))
    zc = -(r0 + 1.0)
    xw = r0 + (r1 - r0) * (-zc / ln)
    for o in (1, -1):
        ck = P.prism([(xw, zc), (-xw, zc)] + arc1, -2.0, 2.0)
        P.merge(bm, ck, T(0, o * (width / 2 - 2.0), 0) @ R("X", 90))
    cl = max(10.0, ln - r0 - 4.0)
    cap = P.prism(P.chamfer_poly(P.rrect(cl, width - 7), 3), 0, 3.2)
    P.merge(bm, cap, T(s * ((r0 + r1) / 2 - 0.9), 0, zc - cl / 2) @ R("Y", s * 90), mat_index=1)
    pin = P.revolve([(0, -width / 2 - 2.6), (4.6, -width / 2 - 2.6), (4.6, -width / 2 - 1.2), (3.2, -width / 2 - 1.2),
                     (3.2, width / 2 + 1.2), (4.6, width / 2 + 1.2), (4.6, width / 2 + 2.6), (0, width / 2 + 2.6)], 12)
    P.merge(bm, pin, R("X", 90), mat_index=2)
    return bm


def _chain(a, base, s, name, segs, tip, what):
    """Build one digit: its segments, coupling links and grip pads. base is the
    frame of the first knuckle before the neutral-pose curl."""
    ax = _dir(base, (0, 1, 0))
    frames = []
    m = base
    for j, (ln, th, curl) in enumerate(segs):
        m = m @ R("Y", s * curl)
        frames.append(m)
        th_next = segs[j + 1][1] if j + 1 < len(segs) else tip
        tag = ("Proximal", "Middle", "Distal")[j] if len(segs) == 3 else ("Proximal", "Distal")[j]
        a.add(f"{name}_{tag}", _segment_bm(ln, th, th_next, s), f"{tag} segment of the {what}.", ["alu", "armour", "steel"],
              m, bevel=0.6)
        m = m @ T(0, 0, -ln)
    # coupling links: a dorsal bar from the base to the second segment, a palmar bar from the first to the last
    links = bmesh.new()
    for o in (1, -1):
        yb = o * (WIDTH / 2 + 1.5)
        P.merge(links, D.link_between(base @ Vector((s * 12, yb, 9)), frames[1] @ Vector((s * 8.5, yb, -7)), ax, 4.2, 1.6, 2.5))
        if len(frames) > 2:
            P.merge(links, D.link_between(frames[0] @ Vector((-s * 8, yb, -24)), frames[2] @ Vector((-s * 6.5, yb, -6)), ax,
                                          4.2, 1.6, 2.5))
    a.add(f"{name}_Links", links, f"Link bars coupling the knuckles of the {what}.", "ti", None, bevel=0.3, seg=1)
    pads = bmesh.new()
    for j, (ln, th, _c) in enumerate(segs):
        th_next = segs[j + 1][1] if j + 1 < len(segs) else tip
        last = j == len(segs) - 1
        pl = (ln - th / 2 + (th_next / 2 if last else 0.0)) * 0.9
        pad = P.prism(P.rrect(pl, WIDTH - 10, 4, 3), 0, 3.0)
        P.merge(pads, pad, frames[j] @ T(-s * ((th + th_next) / 4 - 0.6), 0, -(th / 2 + 1.0) - pl / 2) @ R("Y", -s * 90))
    a.add(f"{name}_Pads", pads, f"Rubber grip pads on the {what}.", "rubber", None, bevel=0.4, seg=1)
    return frames


def build(s):
    a = Asm("09" if s > 0 else "10")
    Ah = FR.torso() @ FR.arm(s)[3]

    # ── wrist: universal joint between the forearm roll output and the palm ──
    bm = P.cyl(80, 8, 40)
    bm.transform(T(0, 0, 13))
    for o in (1, -1):
        P.merge(bm, P.lug(16, 7.2, 16, 8, 24), frame((o * 30, 0, 0), (1, 0, 0), (0, 0, -1)))
    uy = a.add("Wrist_Yoke_Upper", bm, "Upper wrist yoke, bolted to the forearm roll output.", "ti", Ah, bevel=0.6)
    a.take(mech.fasteners("_wf", mech.ring((0, 0, 9), (0, 0, -1), 21, 6), "M4", target=uy, matrix=Ah), "Wrist_Flange_Screws",
           "Screws fixing the upper wrist yoke to the forearm roll output flange.")
    cr = P.prism(P.chamfer_poly(P.rrect(40, 40), 7), -13, 13)
    P.merge(cr, P.cyl(14, 78, 16), R("Y", 90))
    P.merge(cr, P.cyl(14, 78, 16), R("X", 90))
    a.add("Wrist_Cross", cr, "Cross of the two-axis wrist joint.", "steel", Ah, bevel=0.5)
    bm = P.tube(88, 40, 8, 1.0)
    bm.transform(T(0, 0, -28))
    for o in (1, -1):
        P.merge(bm, P.lug(16, 7.2, 26, 8, 24), frame((0, o * 30, 0), (0, 1, 0), (0, 0, 1)))
    a.add("Wrist_Yoke_Lower", bm, "Lower wrist yoke carrying the palm.", "ti", Ah, bevel=0.6)
    pod = [(0, 0), (15, 0), (15, 7), (12.5, 10), (0, 10)]
    a.add("Wrist_Yaw_Drive", P.revolve(pod, 24), "Geared drive for wrist yaw at the trunnion end of the cross.", "alu",
          Ah @ T(s * 34, 0, 0) @ R("Y", s * 90), bevel=0.3)
    a.add("Wrist_Pitch_Drive", P.revolve(pod, 24), "Geared drive for wrist pitch at the trunnion end of the cross.", "alu",
          Ah @ T(0, -34, 0) @ R("X", 90), bevel=0.3)
    a.add("Wrist_Boot", mech.bellows_bm(46, 56, 44, 7.0, 6.0), "Rubber boot sealing the wrist joint.", "rubber",
          Ah @ T(0, 0, -32), bevel=0)
    cl = P.tube(104, 98.6, 5, 0.4)
    cl.transform(T(0, 0, 9))
    lo = P.tube(104, 98.6, 5, 0.4)
    P.merge(cl, lo, T(0, 0, -29))
    a.add("Wrist_Boot_Clamps", cl, "Band clamps holding the wrist boot at both ends.", "steel", Ah, bevel=0)

    # ── palm ────────────────────────────────────────────────────────────────
    bm = P.loft([A.csec(-30, 50, 100, 0, 0, 0.2), A.csec(-100, 46, 112, 0, 0, 0.18)])
    for y in (-57.5, -19, 19, 57.5):                              # knuckle forks either side of each finger
        fk = P.prism(P.round_poly([(-13, 14), (13, 14), (13, -16), (-13, -16)], [0, 0, 12, 12], 4), -2, 2)
        P.merge(bm, fk, T(0, y, -98) @ R("X", 90))
    for y in (-36, 36):                                           # standoffs under the knuckle plate
        for z in (-44, -92):
            P.merge(bm, P.cyl(10, 7, 12), T(s * 26, y, z) @ R("Y", 90))
    pf = a.add("Palm_Frame", bm, "Machined palm frame carrying the knuckle forks and the thumb base.", "alu", Ah, bevel=0.7)
    D.pocket_grid(pf, Ah @ T(-s * 24.2, 0, -64) @ R("Y", -s * 90), 1, 2, 44, 34, 0, 44, depth=4)
    mf = P.cyl(36, 8, 24)
    for k in range(6):
        ang = math.radians(60 * k)
        P.merge(mf, P.cyl(6, 7, 10), T(10 * math.cos(ang), 10 * math.sin(ang), 6))
    a.add("Tendon_Manifold", mf, "Manifold where the six tendons leave the roll shaft and enter the palm.", "alu",
          Ah @ T(0, 0, -26), bevel=0.3, seg=1)
    kp = a.add("Knuckle_Plate", P.plate(P.chamfer_poly(P.rrect(108, 84), 14), 8, crown=4, slices=8),
               "Armour plate over the back of the hand and the knuckles.", "armour",
               Ah @ T(s * 30, 0, -70) @ R("Y", s * 90) @ R("Z", 90), bevel=1.0, seg=3)
    pts = [Ah @ Vector((s * 120, y, z)) for y in (-36, 36) for z in (-44, -92)]
    a.take(mech.fasteners("_kp", D.seats_on(kp, pts, _dir(Ah, (s, 0, 0))), "M4", target=kp), "Knuckle_Plate_Screws",
           "Screws fixing the knuckle plate to the palm frame.")
    pad = bmesh.new()
    for z in (-46, -66, -86):
        P.merge(pad, P.prism(P.rrect(15, 84, 4, 3), 0, 3.5), T(-s * 24.6, 0, z) @ R("Y", -s * 90))
    a.add("Palm_Pad", pad, "Ribbed rubber grip pad on the palm.", "rubber", Ah, bevel=0.5, seg=1)
    sp = P.cyl(5, 100, 12)
    sp.transform(R("X", 90))
    for _n, y in FINGERS:
        P.merge(sp, P.box(6, 8, 10), T(0, y, -4))
    a.add("Finger_Splay_Link", sp, "Ganged link that spreads the three fingers together.", "ti", Ah @ T(s * 27.5, 0, -84),
          bevel=0.3, seg=1)

    # ── fingers and thumb ───────────────────────────────────────────────────
    for name, y in FINGERS:
        _chain(a, Ah @ T(0, y, -98), s, f"Finger_{name}", SEGS, TIP, f"{name.lower()} finger")
    Tb = Ah @ T(-s * 8, -52, -34)
    tb = P.revolve([(0, -17), (17, -17), (19, -15), (19, 13), (16, 17), (0, 17)], 32)
    P.merge(tb, P.box(30, 20, 26), T(s * 14, 8, 0))
    a.add("Thumb_Base", tb, "Opposition joint of the thumb on the front edge of the palm.", "ti", Tb, bevel=0.5)
    _chain(a, Tb @ R("X", -42) @ R("Y", s * 2), s, "Thumb", ((42.0, 31.0, 28.0), (32.0, 28.0, 28.0)), 22.0, "thumb")
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    s = 1 if a.aa == "09" else -1
    RV.closeup(objs, out / f"{a.aa}_hand_back_clay{tag}.jpg", f"{a.aa} hand, back", (s * 1.0, -0.5, 0.15), "clay", dist=4.2,
               isolate=True)
    RV.closeup(objs, out / f"{a.aa}_hand_palm_final{tag}.jpg", f"{a.aa} hand, palm side", (-s * 1.0, -0.6, 0.0), "final",
               dist=4.2, isolate=True)
