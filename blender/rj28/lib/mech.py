"""Mechanical catalogue: fasteners, bearings, gears, actuators. Dimensions mm.

Functions ending in _bm return a BMesh in local coordinates; the others return
finished objects (or dicts of objects) already placed in the scene.
"""
import math

import bmesh
from mathutils import Matrix, Vector

from .. import materials as M
from . import prims as P
from .core import T, R, boolean_cut, cutter, frame, obj_from_bm

# Three screw sizes only (section 5.4). ISO 4762 proportions.
SCREW = {
    "M4":  dict(d=4.0,  head_d=7.0,  head_h=4.0,  hex=3.0, washer_d=9.0,  washer_t=0.8),
    "M6":  dict(d=6.0,  head_d=10.0, head_h=6.0,  hex=5.0, washer_d=12.5, washer_t=1.6),
    "M10": dict(d=10.0, head_d=16.0, head_h=10.0, hex=8.0, washer_d=21.0, washer_t=2.0),
}


# ── fasteners ────────────────────────────────────────────────────────────────
def _hex12(across_flats, z):
    rc = across_flats / math.sqrt(3)
    pts = []
    for i in range(6):
        a0, a1 = math.radians(60 * i), math.radians(60 * i + 60)
        c0 = Vector((rc * math.cos(a0), rc * math.sin(a0), z))
        c1 = Vector((rc * math.cos(a1), rc * math.sin(a1), z))
        pts += [tuple(c0), tuple((c0 + c1) / 2)]
    return pts


def screw_bm(size="M6", kind="shcs", washer=False):
    """Head seat at z=0, head towards +Z, short shank below.

    kind: 'shcs' socket head cap screw | 'csk' flush countersunk |
          'quarter' quarter-turn panel fastener (slotted, with retainer ring).
    """
    s = SCREW[size]
    d, hd, hh, hx = s["d"], s["head_d"], s["head_h"], s["hex"]
    z0 = s["washer_t"] if washer else 0.0

    def circ(r, z, n=12):
        return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), z)
                for i in range(n)]

    if kind == "shcs":
        c = 0.08 * hd
        secs = [circ(d / 2, -2.0 * d), circ(d / 2, z0), circ(hd / 2, z0),
                circ(hd / 2, z0 + hh - c), circ(hd / 2 - c, z0 + hh),
                _hex12(hx, z0 + hh), _hex12(hx, z0 + hh - 0.55 * d)]
        bm = P.loft(secs)
    elif kind == "csk":
        secs = [circ(d / 2, -2.0 * d), circ(d / 2, -0.5 * d), circ(d, 0.0),
                _hex12(hx * 0.9, 0.0), _hex12(hx * 0.9, -0.45 * d)]
        bm = P.loft(secs)
    elif kind == "quarter":
        r = hd * 0.6
        prof = [(0, -1.5 * d), (d / 2, -1.5 * d), (d / 2, 0), (r + 1.6, 0), (r + 1.6, 0.9),
                (r + 0.6, 1.2), (r, 1.2), (r, 2.0), (r - 0.9, 2.6), (0, 2.6)]
        bm = P.revolve(prof, 20)
        slot = P.box(r * 2.4, 1.3, 1.6)                  # coin slot
        slot.transform(T(0, 0, 2.6))
        bm = _notch(bm, slot)
    else:
        raise ValueError(kind)
    if washer:
        P.merge(bm, P.revolve(P.ring_profile(d / 2 + 0.2, s["washer_d"] / 2, 0, s["washer_t"], 0.2), 16))
    return bm


def _notch(bm, cut_bm):
    """Subtract cut_bm from bm via temporary objects (used for small masters)."""
    import bpy
    from .core import MM, evaluated_mesh
    a = obj_from_bm("_a", bm, bevel=0)
    for m in list(a.modifiers):
        a.modifiers.remove(m)
    c = cutter(cut_bm)
    boolean_cut(a, c)
    out = bmesh.new()
    out.from_mesh(a.data)
    bmesh.ops.scale(out, vec=(1 / MM,) * 3, verts=out.verts)
    me = a.data
    bpy.data.objects.remove(a)
    bpy.data.meshes.remove(me)
    return out


def row(p0, p1, count, normal, inset=0.0):
    """Evenly spaced screw seats from p0 to p1 (mm), heads along `normal`."""
    a, b = Vector(p0), Vector(p1)
    d = (b - a)
    L = d.length
    out = []
    for i in range(count):
        t = 0.5 if count == 1 else (inset + (L - 2 * inset) * i / (count - 1)) / L
        out.append(frame(a + d * t, normal, d))
    return out


def ring(center, axis, radius, count, phase=0.0, x_hint=(1, 0, 0)):
    """Screw seats on a bolt circle about `axis`."""
    base = frame(center, axis, x_hint)
    return [base @ R("Z", phase + 360.0 * i / count) @ T(radius, 0, 0) for i in range(count)]


def fasteners(name, seats, size="M6", kind="shcs", washer=False, target=None,
              counterbore=True, collection=None, matrix=None):
    """One part holding a set of identical screws at `seats` (list of matrices).

    If target is given and counterbore is True, a counterbore is cut at every
    seat and the screw is sunk into it so the head sits just below flush.
    """
    s = SCREW[size]
    sink = (s["head_h"] + 0.4) if (target is not None and counterbore and kind == "shcs") else 0.0
    if matrix is not None:
        seats = [matrix @ m for m in seats]
    if sink:
        cut = bmesh.new()
        for m in seats:
            cb = P.cyl(s["head_d"] + 1.6, sink + 20.0, 16)          # counterbore, open above
            P.merge(cut, cb, m @ T(0, 0, 10.0 - sink / 2))
            th = P.cyl(s["d"] + 0.6, 2.2 * s["d"], 12)              # clearance hole below seat
            P.merge(cut, th, m @ T(0, 0, -sink - 1.1 * s["d"] + 0.05))
        boolean_cut(target, cutter(cut), lip=0.35)
    elif target is not None and kind == "csk":
        cut = bmesh.new()
        d = s["d"]
        for m in seats:
            P.merge(cut, P.cyl(d, 0.5 * d + 0.6, 12, d2=2 * d + 2.4), m @ T(0, 0, -0.25 * d + 0.3))
            P.merge(cut, P.cyl(d + 0.6, 2.2 * d, 12), m @ T(0, 0, -1.55 * d))
        boolean_cut(target, cutter(cut))
    bm = bmesh.new()
    for m in seats:
        P.merge(bm, screw_bm(size, kind, washer), m @ T(0, 0, -sink))
    ob = obj_from_bm(name, bm, collection=collection, material=M.get("fastener"),
                     bevel=0.0)
    ob["rj28_count"] = len(seats)
    ob["rj28_size"] = size
    return ob


# ── bearings, rings, gears ───────────────────────────────────────────────────
def bearing_bm(od, id_, width):
    """Sealed bearing along Z, centred. Slot 0 steel races, slot 1 rubber seal."""
    t = (od - id_) / 2 * 0.30
    c = min(0.6, width * 0.08)
    segs = P.auto_segs(od)
    bm = P.revolve(P.ring_profile(od / 2 - t, od / 2, -width / 2, width / 2, c), segs)
    P.merge(bm, P.revolve(P.ring_profile(id_ / 2, id_ / 2 + t, -width / 2, width / 2, c), segs))
    P.merge(bm, P.revolve(P.ring_profile(id_ / 2 + t - 0.2, od / 2 - t + 0.2,
                                          -width / 2 + 0.9, width / 2 - 0.9, 0.2), segs),
            mat_index=1)
    return bm


def bearing(name, od, id_, width, matrix=None, collection=None):
    return obj_from_bm(name, bearing_bm(od, id_, width), matrix, collection,
                       [M.get("steel"), M.get("rubber")], bevel=0.0)


def gear_outline(module, teeth, phase=0.0, first=0, count=None, flank=5):
    """2D spur gear outline (CCW): true involute flanks at 20 degrees pressure angle,
    radial below the base circle, with a relieved root."""
    z = teeth
    r = module * z / 2
    ra, rf, rb = r + module, r - 1.25 * module, r * math.cos(math.radians(20.0))
    inv = lambda al: math.tan(al) - al
    half = math.pi / (2 * z) + inv(math.radians(20.0))        # half tooth angle on the base circle

    def theta(rr):
        return max(half - inv(math.acos(min(1.0, rb / rr))), 0.04 * module / ra)

    r0 = max(rb, rf + 0.3 * module)
    radii = [r0 + (ra - r0) * i / (flank - 1) for i in range(flank)]
    root = min(theta(r0) + 0.22 * module / rf, math.pi / z - 0.06 * module / rf)
    tooth = [(rf, -root)] + [(rr, -theta(rr)) for rr in radii] + [(rr, theta(rr)) for rr in reversed(radii)] + [(rf, root)]
    p = 2 * math.pi / z
    pts = []
    for k in range(first, first + (count or z)):
        a = phase + k * p
        pts += [(rr * math.cos(a + off), rr * math.sin(a + off)) for rr, off in tooth]
    return pts


def gear_bm(module, teeth, width, bore):
    outer = gear_outline(module, teeth)
    inner = [(bore / 2 * x / math.hypot(x, y), bore / 2 * y / math.hypot(x, y)) for x, y in outer]
    return P.ring_solid(outer, inner, -width / 2, width / 2)


def gear(name, module, teeth, width, bore, matrix=None, collection=None, material="steel"):
    return obj_from_bm(name, gear_bm(module, teeth, width, bore), matrix, collection,
                       M.get(material), bevel=0.25, segments=1)


def sector_gear_bm(module, teeth_total, sweep, width, inner_r):
    """Gear segment spanning `sweep` degrees (centred on +X) with a solid web
    down to inner_r."""
    n = max(2, round(teeth_total * sweep / 360.0))
    p = 360.0 / teeth_total
    start = -math.radians(p * (n - 1) / 2)
    outer = gear_outline(module, teeth_total, phase=start, count=n)
    a0 = math.atan2(outer[0][1], outer[0][0])
    a1 = math.atan2(outer[-1][1], outer[-1][0])
    k = max(6, n * 2)
    inner = [(inner_r * math.cos(a1 + (a0 - a1) * i / k), inner_r * math.sin(a1 + (a0 - a1) * i / k))
             for i in range(k + 1)]
    return P.prism(outer + inner, -width / 2, width / 2)


def sector_gear(name, module, teeth_total, sweep, width, inner_r, matrix=None,
                collection=None, material="steel"):
    return obj_from_bm(name, sector_gear_bm(module, teeth_total, sweep, width, inner_r),
                       matrix, collection, M.get(material), bevel=0.25, segments=1)


def slewing_ring(name, od, id_, height, bolts=16, size="M6", matrix=None, collection=None,
                 geared=False, module=2.5):
    """Two-ring slewing bearing along Z, base at z=0. Returns dict of objects:
    outer (fixed race, optionally external gear), inner (rotating race), seal, bolts."""
    matrix = matrix or Matrix.Identity(4)
    segs = P.auto_segs(od)
    teeth = max(24, round((od - 2 * module) / module))
    # bolt lands: equal radial width on both races, measured inside the tooth roots
    r_land = (module * teeth / 2 - 1.25 * module - 1.0) if geared else od / 2
    r_split = (id_ / 2 + r_land) / 2
    land = r_split - 0.6 - id_ / 2
    for size in (size, "M6", "M4"):                       # largest screw the land can take
        if SCREW[size]["head_d"] + 1.6 + 2.4 <= land:
            break
    if geared:
        go = gear_outline(module, teeth)
        gi = [((r_split + 0.6) * x / math.hypot(x, y), (r_split + 0.6) * y / math.hypot(x, y))
              for x, y in go]
        outer_bm = P.ring_solid(go, gi, 0, height * 0.86)
    else:
        outer_bm = P.revolve(P.ring_profile(r_split + 0.6, od / 2, 0, height * 0.86, 0.8), segs)
    outer = obj_from_bm(name + "_Outer_Race", outer_bm, matrix, collection, M.get("ti"),
                        bevel=0.4, segments=1)
    inner = obj_from_bm(name + "_Inner_Race",
                        P.revolve(P.ring_profile(id_ / 2, r_split - 0.6, height * 0.14, height, 0.8), segs),
                        matrix, collection, M.get("steel"), bevel=0.4, segments=1)
    seal = obj_from_bm(name + "_Seal",
                       P.revolve(P.ring_profile(r_split - 0.7, r_split + 0.7, height * 0.2,
                                                height * 0.80, 0.2), segs),
                       matrix, collection, M.get("rubber"), bevel=0.0)
    r_in = (id_ / 2 + r_split - 0.6) / 2
    r_out = (r_split + 0.6 + r_land) / 2
    seats_i = ring((0, 0, height), (0, 0, 1), r_in, bolts)
    seats_o = ring((0, 0, height * 0.86), (0, 0, 1), r_out, bolts, phase=180.0 / bolts)
    b_in = fasteners(name + "_Inner_Bolts", seats_i, size, target=inner, collection=collection,
                     matrix=matrix)
    b_out = fasteners(name + "_Outer_Bolts", seats_o, size, target=outer, collection=collection,
                      matrix=matrix)
    return dict(outer=outer, inner=inner, seal=seal, bolts_inner=b_in, bolts_outer=b_out)


# ── actuators ────────────────────────────────────────────────────────────────
def bellows_bm(r_in, r_out, length, pitch=7.0, cuff=8.0):
    """Rubber bellows along Z from z=0 to z=length. Convolutions have rounded crests
    and valleys; each cuff carries a raised bead either side of the clamp seat."""
    n = max(2, round((length - 2 * cuff) / pitch))
    p = (length - 2 * cuff) / n
    bore, collar, valley = r_in + 0.4, r_in + 3.0, r_in + 2.2
    bead = min(0.9, cuff * 0.12)
    amp = r_out - valley
    prof = [(bore, 0.0), (collar, 0.0), (collar + bead, cuff * 0.12), (collar, cuff * 0.24), (collar, cuff * 0.76),
            (collar + bead, cuff * 0.88), (collar, cuff)]
    steps = 8
    for i in range(n):
        for k in range(1, steps + 1):
            t = k / steps
            prof.append((valley + amp * (0.5 - 0.5 * math.cos(2 * math.pi * t)) ** 0.8, cuff + (i + t) * p))
    prof[-1] = (collar, length - cuff)
    prof += [(collar + bead, length - cuff * 0.88), (collar, length - cuff * 0.76), (collar, length - cuff * 0.24),
             (collar + bead, length - cuff * 0.12), (collar, length), (bore, length)]
    return P.revolve(prof, P.auto_segs(r_out * 2))


def clevis_bm(eye_r, pin_r, gap, ear_t, reach, base_t=None):
    """Fork bracket. Pin axis = local Z through the origin; ears reach back along
    -X to a base plate whose mounting face is at x = -(reach + base_t)."""
    base_t = base_t or ear_t * 1.3
    bm = bmesh.new()
    for sgn in (1, -1):
        P.merge(bm, P.lug(eye_r, pin_r, reach + 0.01, ear_t), T(0, 0, sgn * (gap / 2 + ear_t / 2)))
    base = P.box(base_t, eye_r * 2, gap + 2 * ear_t)
    P.merge(bm, base, T(-(reach + base_t / 2), 0, 0))
    if eye_r > 12:                                       # cap screws through the base, between the ears
        for sgn in (1, -1):
            P.merge(bm, screw_bm("M6" if eye_r > 24 else "M4"), T(-reach, sgn * eye_r * 0.66, 0) @ R("Y", 90))
    return bm


def clevis_seat(rod_d):
    """Where the clevis of a linear_actuator with this rod wants its pad: (distance from the pin to the
    mounting face, pad width across the pin, pad length along the pin)."""
    eye_r, ear_t = rod_d * 0.95, rod_d * 0.32
    return eye_r * 1.35 + ear_t * 1.3, eye_r * 2.04, rod_d * 0.9 + 1.0 + 2 * ear_t


def pin_bm(d, length, head=True):
    """Clevis pin along Z, centred: head one side, retaining clip the other."""
    L = length
    prof = [(0, -L / 2), (d / 2 - 0.4, -L / 2), (d / 2, -L / 2 + 0.4), (d / 2, L / 2)]
    if head:
        prof += [(d * 0.8, L / 2), (d * 0.8, L / 2 + d * 0.22), (d * 0.8 - 0.5, L / 2 + d * 0.3),
                 (0, L / 2 + d * 0.3)]
    else:
        prof += [(0, L / 2)]
    bm = P.revolve(prof, P.auto_segs(d * 2))
    clip = P.revolve(P.ring_profile(d / 2, d * 0.82, -L / 2 + 1.2, -L / 2 + 2.3, 0.1),
                     P.auto_segs(d * 2), angle=300.0)
    P.merge(bm, clip)
    return bm


PORT = (0.18, 0.0, None)     # power port: fraction of the body length from its rear end, turn about the
                             # actuator axis from `side` towards the pin (degrees), stand-off (None: 0.45 body radii)


def actuator_port(p0, p1, body_d=44.0, rod_d=30.0, stroke=80.0, pin_axis=(1, 0, 0), body_len=None, port=PORT):
    """Where the power port of a linear_actuator built with the same arguments ends up:
    (tip point, outward direction), in mm. The harness plugs in here."""
    p0, p1 = Vector(p0), Vector(p1)
    axis = (p1 - p0).normalized()
    pin = Vector(pin_axis) - axis * axis.dot(Vector(pin_axis))
    pin.normalize()
    side = axis.cross(pin)
    neck = rod_d * 0.95 * 1.25
    body_len = body_len or (stroke + body_d * 1.6)
    rb = body_d / 2
    a = math.radians(port[1])
    out = side * math.cos(a) + pin * math.sin(a)
    proud = rb * 0.45 if port[2] is None else port[2]
    return p0 + axis * (neck + body_len * port[0]) + out * (rb * 1.12 + proud), out


def linear_actuator(name, p0, p1, body_d=44.0, rod_d=30.0, stroke=80.0, bellows=True,
                    pin_axis=(1, 0, 0), collection=None, base_dir0=None, base_dir1=None,
                    body_len=None, port=PORT):
    """Planetary roller-screw actuator posed between pivot p0 (body end) and pivot
    p1 (rod end). Returns dict: body, rod, bellows, clevis_a, clevis_b, pin_a, pin_b.

    The clevises are the structure-side forks; base_dir0/1 point from each pivot
    towards the structure they bolt to (default: straight along the actuator).
    """
    p0, p1 = Vector(p0), Vector(p1)
    axis = (p1 - p0)
    L = axis.length
    axis.normalize()
    pin = Vector(pin_axis) - axis * axis.dot(Vector(pin_axis))
    pin.normalize()
    side = axis.cross(pin)                       # third axis
    # local frame: Z along actuator, X along pin
    F = Matrix((pin, side, axis)).transposed().to_4x4()
    F.translation = p0

    eye_r = rod_d * 0.95
    eye_t = rod_d * 0.9
    pin_d = rod_d * 0.55
    neck = eye_r * 1.25
    body_len = body_len or (stroke + body_d * 1.6)
    z_body0 = neck
    z_body1 = neck + body_len
    z_rod1 = L - neck
    assert z_rod1 - z_body1 > 4.0, f"{name}: no exposed rod (L={L:.0f}, body ends {z_body1:.0f})"

    # body: stepped housing with motor section, gland nut and rear eye.
    # P.lug lies in XY (hole axis Z, root towards -X): R("Y", 90) turns the hole
    # axis onto local X with the root towards +Z, R("Y", -90) with it towards -Z.
    rb = body_d / 2
    prof = [(0, z_body0), (rb * 0.78, z_body0), (rb * 0.78, z_body0 + 4), (rb * 1.12, z_body0 + 6),
            (rb * 1.12, z_body0 + body_len * 0.36), (rb * 1.12 - 1.2, z_body0 + body_len * 0.36 + 1.2),
            (rb, z_body0 + body_len * 0.36 + 3.0), (rb, z_body1 - 14), (rb * 1.08, z_body1 - 12),
            (rb * 1.08, z_body1 - 3), (rb * 0.9, z_body1), (0, z_body1)]
    bm = P.revolve(prof, P.auto_segs(body_d * 1.5))
    rear = P.lug(eye_r, pin_d / 2, neck + 2.0, eye_t)
    rear.transform(R("Y", 90))
    P.merge(bm, rear)
    proud = rb * 0.45 if port[2] is None else port[2]
    P.merge(bm, P.cyl(rb * 0.55, proud + rb * 0.05, 16),
            R("Z", -port[1]) @ T(0, rb * 1.095 + proud / 2, z_body0 + body_len * port[0]) @ R("X", -90))
    body = obj_from_bm(name + "_Body", bm, F, collection, M.get("alu"), bevel=0.6)

    # rod with rod-end eye
    rr = rod_d / 2
    bm = P.revolve([(0, z_body1 - 6), (rr, z_body1 - 6), (rr, z_rod1 - 3), (rr * 0.8, z_rod1),
                    (0, z_rod1)], P.auto_segs(rod_d * 1.5))
    front = P.lug(eye_r, pin_d / 2, neck + 2.0, eye_t)
    front.transform(T(0, 0, L) @ R("Y", -90))
    P.merge(bm, front)
    rod = obj_from_bm(name + "_Rod", bm, F, collection, M.get("steel"), bevel=0.4)

    out = dict(body=body, rod=rod)
    if bellows:
        exposed = z_rod1 - z_body1
        blen = exposed * 0.62
        if blen > 22:
            bb = bellows_bm(rr, rr + max(5.0, rod_d * 0.28), blen)
            out["bellows"] = obj_from_bm(name + "_Bellows", bb, F @ T(0, 0, z_body1), collection,
                                         M.get("rubber"), bevel=0.0)

    ear_t = rod_d * 0.32
    gap = eye_t + 1.0
    for key, pos, bdir in (("a", p0, base_dir0 or -axis), ("b", p1, base_dir1 or axis)):
        bdir = Vector(bdir) - pin * pin.dot(Vector(bdir))
        bdir.normalize()
        Fc = Matrix((-bdir, pin.cross(-bdir), pin)).transposed().to_4x4()
        Fc.translation = pos
        cb = clevis_bm(eye_r * 1.02, pin_d / 2, gap, ear_t, eye_r * 1.35)
        out["clevis_" + key] = obj_from_bm(f"{name}_Clevis_{key.upper()}", cb, Fc, collection,
                                           M.get("ti"), bevel=0.6)
        pb = pin_bm(pin_d, gap + 2 * ear_t + 5.0)
        out["pin_" + key] = obj_from_bm(f"{name}_Pin_{key.upper()}", pb, Fc, collection,
                                        M.get("steel"), bevel=0.0)
    return out


def rotary_actuator(name, od=160.0, length=90.0, matrix=None, collection=None, bolts=12,
                    fins=True, connector_angle=90.0):
    """Frameless-motor + strain-wave joint module along Z; output face at +Z,
    base at z=0. Returns dict: housing, flange, bolts, connector."""
    from .harness import connector_bm
    matrix = matrix or Matrix.Identity(4)
    r = od / 2
    L = length
    prof = [(0, 0), (r - 6, 0), (r - 3, 3), (r - 3, L * 0.12)]
    if fins:
        z0, z1 = L * 0.14, L * 0.52
        n = max(3, int((z1 - z0) / 5.5))
        p = (z1 - z0) / n
        for i in range(n):
            z = z0 + i * p
            prof += [(r - 8, z), (r - 8, z + p * 0.35), (r, z + p * 0.45), (r, z + p * 0.9)]
        prof += [(r - 3, z1 + 1)]
    prof += [(r - 3, L * 0.60), (r, L * 0.62), (r, L * 0.80),
             (r - 0.9, L * 0.80 + 0.01), (r - 0.9, L * 0.80 + 1.2), (r, L * 0.80 + 1.21),   # seal line
             (r, L - 4), (r - 2.5, L - 1.5), (r * 0.80, L - 1.5), (r * 0.80, L - 5), (0, L - 5)]
    segs = P.auto_segs(od)
    housing = obj_from_bm(name + "_Housing", P.revolve(prof, segs), matrix, collection,
                          M.get("alu"), bevel=0.5)
    fprof = [(r * 0.30, L - 5), (r * 0.78, L - 5), (r * 0.78, L + 1.0), (r * 0.76, L + 3.0),
             (r * 0.34, L + 3.0), (r * 0.30, L + 1.0)]
    flange = obj_from_bm(name + "_Output_Flange", P.revolve(fprof, segs), matrix, collection,
                         M.get("ti"), bevel=0.4)
    out = dict(housing=housing, flange=flange)
    if bolts:                                    # bolts=0 when the driven part brings its own screws
        seats = ring((0, 0, L + 3.0), (0, 0, 1), r * 0.60, bolts)
        out["bolts"] = fasteners(name + "_Flange_Bolts", seats, "M6", target=flange, collection=collection,
                                 matrix=matrix)
    cm = matrix @ R("Z", connector_angle) @ T(r - 3.5, 0, L * 0.07 + 5) @ R("Y", 90)
    out["connector"] = obj_from_bm(name + "_Connector", connector_bm(14.0), cm, collection,
                                   [M.get("fastener"), M.get("rubber")], bevel=0.0)
    return out
