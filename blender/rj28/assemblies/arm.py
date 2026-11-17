"""Assemblies 07 / 08: arm, left / right.

Shoulder roll actuator in its cradle, roll yoke, shoulder armour on its carrier,
shoulder yaw actuator, upper-arm member and half-shell, elbow joint, forearm frame
with the hand drive, forearm armour, forearm roll actuator and bearing. The
thorax owns the shoulder pitch actuator (output face at x = +/-(SX - 77)); the
hand (09 / 10) owns the wrist.

Frames (rj28.frames.arm, with the torso offset applied): upper-arm and forearm
frames have +X lateral, +Y to the rear and -Z running down the limb. "Outer"
is s * X. The elbow axis is local X at z = -UPPER_ARM of the upper-arm frame.

Kinematic notes
- The shoulder armour rides on the roll yoke, so it follows the arm in
  abduction; it does not turn with shoulder yaw.
- Forearm roll is at the wrist end, so the forearm armour never turns against
  the elbow. The finger tendons pass through the hollow roll shaft.
- Elbow: 0 deg (stop) to about 105 deg of flexion before the forearm armour
  meets the upper-arm half-shell.
"""
import math

import bmesh
import bpy
from mathutils import Vector

from .. import frames as FR, params as PR
from ..lib import armour as A, core as C, detail as D, fittings as F, harness as H, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm, raw

SHELL_T = 12.0           # shoulder armour thickness


def _dir(m, v):
    return (m.to_3x3() @ Vector(v)).normalized()


def _local(m, ob):
    lo, hi = C.bounds_mm([ob])
    return m.inverted() @ ((lo + hi) / 2)


def _drop(ob):
    me = ob.data
    bpy.data.objects.remove(ob)
    if me.users == 0:
        bpy.data.meshes.remove(me)


def _round_polyline(pts, radii, n=5):
    """Fillet the interior corners of an open 2D polyline."""
    out = [tuple(pts[0])]
    for i in range(1, len(pts) - 1):
        p = Vector(pts[i])
        u = Vector(pts[i - 1]) - p
        v = Vector(pts[i + 1]) - p
        r = radii[i]
        if r <= 0:
            out.append(tuple(p))
            continue
        la, lb = u.length, v.length
        u, v = u / la, v / lb
        phi = math.acos(max(-1.0, min(1.0, u.dot(v))))
        t = min(r / math.tan(phi / 2), 0.45 * la, 0.45 * lb)
        r = t * math.tan(phi / 2)
        c = p + (u + v).normalized() * (r / math.sin(phi / 2))
        s0, s1 = p + u * t - c, p + v * t - c
        a0, a1 = math.atan2(s0.y, s0.x), math.atan2(s1.y, s1.x)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for k in range(n + 1):
            a = a0 + da * k / n
            out.append((c.x + r * math.cos(a), c.y + r * math.sin(a)))
    out.append(tuple(pts[-1]))
    return out


def _offset(pts, d):
    """Offset an open 2D polyline to its right-hand side by d (miter joins)."""
    q = [Vector(p) for p in pts]

    def nrm(a, b):
        t = (b - a).normalized()
        return Vector((t.y, -t.x))

    out = []
    for i in range(len(q)):
        if i == 0:
            m, k = nrm(q[0], q[1]), 1.0
        elif i == len(q) - 1:
            m, k = nrm(q[-2], q[-1]), 1.0
        else:
            n0, n1 = nrm(q[i - 1], q[i]), nrm(q[i], q[i + 1])
            m = (n0 + n1).normalized()
            k = 1.0 / max(0.3, m.dot(n0))
        out.append(tuple(q[i] + m * d * k))
    return out


def _pauldron_outer(out, skirt, drop):
    """Outer line of the shoulder armour in (x, z) for the left side: inner flank,
    top slab, outer shoulder, outer wall down to the skirt."""
    sx, top = PR.SX, PR.PAULDRON_TOP_Z - drop
    pts = [(sx - 58, top - 54), (sx - 14, top), (out - 66, top), (out - 6, top - 54), (out, 1400), (out - 12, skirt)]
    return _round_polyline(pts, [0, 16, 30, 34, 46, 0], 5)


def _elbow_housing_bm():
    """Elbow actuator housing: clamp land in the middle, cooling fins either side."""
    r = 69.0
    prof = [(0, -62), (60, -62), (63, -59), (63, -53)]
    for z0 in (-52, -47, -42, -37):
        prof += [(61, z0), (61, z0 + 1.6), (r, z0 + 2.2), (r, z0 + 4.2)]
    prof += [(61, -32.5), (61, -31), (r, -30), (r, 30), (61, 31), (61, 32.5)]
    for z0 in (33, 38, 43, 48):
        prof += [(r, z0 - 0.2), (r, z0 + 1.8), (61, z0 + 2.4), (61, z0 + 4.0)]
    prof += [(63, 53), (63, 59), (60, 62), (0, 62)]
    return P.revolve(prof, 64)


def _half_clamp(lower):
    """Half of the split clamp around the elbow housing, with its bolt ears.
    Built on the elbow frame: axis X, split plane z = 0."""
    bm = P.revolve(P.ring_profile(69.3, 84.0, -27, 27, 1.0), 48, angle=180)
    bm.transform(R("Y", 90) @ R("Z", -90 if lower else 90))
    for o in (1, -1):
        P.merge(bm, P.box(54, 22, 13.5), T(0, o * 94, -6.75 if lower else 6.75))
    return bm


def build(s):
    a = Asm("07" if s > 0 else "08")
    n = "L" if s > 0 else "R"
    zp = f"pauldron_{n}"
    W = FR.torso()
    sv0, au0, af0, ah0 = FR.arm(s)
    Au, Af = W @ au0, W @ af0
    S = W @ sv0                                  # shoulder centre
    El = Au @ T(0, 0, -PR.UPPER_ARM)             # elbow, upper-arm orientation
    Ts = T(*S)
    sx = PR.SX

    # ── shoulder roll actuator, held in a cradle on the pitch output ────────
    d = mech.rotary_actuator("_roll", 150, 122, Ts @ T(0, 61, 0) @ R("X", 90), bolts=0)
    _drop(d.pop("connector"))                    # its cable leaves on the axis instead (no twist in roll)
    a.take_rotary(d, "Shoulder_Roll", "shoulder roll")
    cr = a.add("Shoulder_Roll_Cradle", P.prism(P.chamfer_poly(P.rrect(27, 92), 4), -46, 46),
               "Cradle clamping the shoulder roll housing to the shoulder pitch output.", "ti",
               Ts @ T(-s * 63.5, 8, 0), bevel=0.8)
    C.boolean_cut(cr, C.cutter(P.cyl(151.4, 240, 64), Ts @ R("X", 90)), lip=0.5)
    band = P.revolve(P.ring_profile(75.4, 79.5, -7, 7, 0.6), 64)
    P.merge(band, P.box(22, 12, 14), T(0, 84.5, 0))
    bandm = Ts @ T(0, -27, 0) @ R("X", 90)
    a.add("Shoulder_Roll_Clamp_Band", band, "Clamp band holding the shoulder roll housing down in its cradle.", "ti",
          bandm, bevel=0.5)
    a.take(mech.fasteners("_cb", [bandm @ T(s * 11, 84.5, 0) @ R("Y", s * 90)], "M6"), "Shoulder_Roll_Clamp_Screw",
           "Screw drawing the shoulder roll clamp band tight.")
    cn, _ = H.connector("_rc", S + Vector((0, 61, 0)), (0, 1, 0), 12.0)
    a.take(cn, "Shoulder_Roll_Connector", "Power and encoder connector on the shoulder roll axis.")

    # ── roll yoke: front plate on the output flange, rear plate on the idler, bridge below ──
    yk = bmesh.new()
    P.merge(yk, P.lug(62, 22, 102, 14, 40), frame((0, -71, 0), (0, 1, 0), (0, 0, 1)))
    P.merge(yk, P.lug(52, 30, 102, 8, 40), frame((0, 66, 0), (0, 1, 0), (0, 0, 1)))
    P.merge(yk, P.prism(P.chamfer_poly(P.rrect(150, 148), 14), -100, -84), T(0, -4, 0))
    yoke = a.add("Shoulder_Yoke", yk, "Roll yoke: hangs the arm from the shoulder roll output and its rear idler.", "ti",
                 Au, bevel=1.0)
    D.pocket_grid(yoke, Au @ T(0, -78.2, -70) @ R("X", 90), 1, 1, 70, 14, 0, 0, depth=5)
    for o in (1, -1):
        D.pocket_grid(yoke, Au @ T(o * 75.2, -3, -92) @ R("Y", o * 90), 1, 2, 8, 46, 0, 62, depth=5)
    seats = mech.ring((0, -78, 0), (0, -1, 0), 44, 10, x_hint=(1, 0, 0))
    a.take(mech.fasteners("_yb", seats, "M6", target=yoke, matrix=Au), "Shoulder_Yoke_Bolts",
           "Screws clamping the roll yoke to the shoulder roll output flange.")
    a.add("Shoulder_Roll_Idler_Retainer", P.tube(78, 61, 4, 0.6), "Polished ring retaining the rear idler bearing of the roll yoke.",
          "steel", Au @ T(0, 72, 0) @ R("X", -90), bevel=0)

    # ── shoulder armour: thick shell over the roll actuator, on a carrier bolted to the yoke ──
    out = PR.PAULDRON_L_OUT if s > 0 else PR.PAULDRON_R_OUT
    skirt, drop = (1296, 0.0) if s > 0 else (1326, PR.PAULDRON_R_DROP)
    yf, yr = (-132, 118) if s > 0 else (-124, 20)             # right is cut back to clear the mount
    top = PR.PAULDRON_TOP_Z - drop
    outer = _pauldron_outer(out, skirt, drop)
    inner = _offset(outer, SHELL_T)

    def mx(pts):
        return [(x * s, z) for x, z in pts]

    Pm = W @ R("X", 90)                                       # profile (x, z) extruded along -Y
    sh = raw(P.prism(mx(outer + inner[::-1]), -yr, -yf), Pm, "armour", 1.2, 3)
    for yy in (yf, yr):
        C.boolean_cut(sh, C.cutter(P.box(700, 15, 15), W @ T(s * (sx + 60), yy, top) @ R("X", 45)), lip=0.6)
    A.gap_cut(sh, W @ Vector((s * out, (yf + yr) / 2, 1376 if s > 0 else 1384)), (0.0, 0.12, 1.0))
    pieces = sorted(A.islands(sh), key=lambda o: -len(o.data.vertices))[:2]
    skirt_ob, shell = sorted(pieces, key=lambda o: C.bounds_mm([o])[1].z)
    a.take(shell, "Pauldron_Shell", "Shoulder armour shell over the roll actuator; rides on the roll yoke.", zone=zp)
    a.take(skirt_ob, "Pauldron_Skirt", "Lower skirt panel of the shoulder armour.", zone=zp)
    # cheeks: close the ends above an arch that leaves the actuator and yoke bolts in view
    cin = _offset(outer, SHELL_T + A.GAP)
    zb = 1404 if s > 0 else 1410
    x0 = sx - 34.0                                            # inner edge of the cheek
    chk = []
    for p, q in zip(cin, cin[1:]):
        if p[0] < x0 <= q[0] and not chk:
            f = (x0 - p[0]) / (q[0] - p[0])
            chk.append((x0, p[1] + (q[1] - p[1]) * f))
        elif chk:
            chk.append(p)
        if chk and q[1] < zb <= p[1] and q[0] > sx:
            f = (p[1] - zb) / (p[1] - q[1])
            chk.append((p[0] + (q[0] - p[0]) * f, zb))
            break
    a_end = math.degrees(math.acos((x0 - sx) / 66.0))
    chk += [(sx + 66 * math.cos(math.radians(-20 + (a_end + 20) * k / 20)),
             PR.Z_SHOULDER + 66 * math.sin(math.radians(-20 + (a_end + 20) * k / 20))) for k in range(21)]
    cheeks = [("Front", yf + 3)] + ([("Rear", yr - 13)] if s > 0 else [])
    cheek_obs = {}
    for tag, y0 in cheeks:
        cheek_obs[tag] = a.add(f"Pauldron_Cheek_{tag}", P.prism(mx(chk), -(y0 + 10), -y0),
                               f"{tag} cheek of the shoulder armour, arched to show the roll actuator.", "armour", Pm,
                               bevel=1.0, seg=3, zone=zp)
    # carrier: two ribs inside the shell joined by a stringer
    r0, r1 = _offset(outer, SHELL_T + 0.6), _offset(outer, SHELL_T + 5.6)
    ribs_y = [(yf + 16, yf + 32), ((yr - 32, yr - 16) if s > 0 else (yr - 28, yr - 12))]
    car = bmesh.new()
    for y0, y1 in ribs_y:
        P.merge(car, P.prism(mx(r0 + r1[::-1]), -y1, -y0))
    xs = (sx + 8, out - 84)                                   # on the flat of the top slab
    for x in xs:
        P.merge(car, P.box(26, 5, ribs_y[1][1] - ribs_y[0][0]), T(s * x, top - SHELL_T - 3.1, -(ribs_y[1][1] + ribs_y[0][0]) / 2))
    a.add("Pauldron_Carrier", car, "Carbon ribs and stringers bonded inside the shoulder armour.", "cfrp", Pm, bevel=0.3,
          seg=1, zone=zp)
    # brackets from the yoke plates up to the ribs
    rib_z = top - SHELL_T - 5.6
    xb = s * (sx - 12)
    br = bmesh.new()
    P.merge(br, P.box(40, 52, rib_z - 1478), T(xb, -90, (rib_z + 1478) / 2))
    if s > 0:
        P.merge(br, P.box(40, 40, rib_z - 1478), T(xb, 82, (rib_z + 1478) / 2))
    else:
        P.merge(br, P.box(30, 82, rib_z - 1510.5), T(xb, 31, (rib_z + 1510.5) / 2))      # strap over the housing
        P.merge(br, P.box(30, 10, rib_z - 1478), T(xb, 67, (rib_z + 1478) / 2))
    a.add("Pauldron_Mount_Brackets", br, "Brackets carrying the shoulder armour carrier on the roll yoke.", "ti", W,
          bevel=0.8, zone=zp)
    pts = [W @ Vector((s * x, (y0 + y1) / 2, top + 60)) for x in xs for y0, y1 in ribs_y]
    a.take(mech.fasteners("_ps", D.seats_on(shell, pts, (0, 0, 1), x_hint=(1, 0, 0)), "M6", target=shell),
           "Pauldron_Shell_Screws", "Screws fixing the shoulder armour shell to its carrier.", zone=zp)
    pts = [W @ Vector((s * (out + 80), y, (skirt + (1376 if s > 0 else 1384)) / 2)) for y in (yf + 24, (yr - 24) if s > 0 else (yr - 20))]
    a.take(mech.fasteners("_pk", D.seats_on(skirt_ob, pts, (s, 0, 0)), "M6", target=skirt_ob), "Pauldron_Skirt_Screws",
           "Screws fixing the shoulder armour skirt to its carrier.", zone=zp)
    F.panel_cut(shell, [W @ Vector((s * (sx - 2 + (out - 78 - sx) * k / 14), (yf + yr) / 2 + (6 if s > 0 else 0), top + 3))
                        for k in range(15)], 1.5, 2.0)
    for tag, y0 in cheeks:
        fwd = (0, -1, 0) if tag == "Front" else (0, 1, 0)
        yy = y0 - 60 if tag == "Front" else y0 + 70
        pts = [W @ Vector((s * x, yy, z)) for x, z in ((sx + 20, top - 30), (out - 70, top - 34), (out - 34, 1440))]
        a.take(mech.fasteners("_pc", D.seats_on(cheek_obs[tag], pts, fwd, x_hint=(1, 0, 0)), "M4", target=cheek_obs[tag]),
               f"Pauldron_Cheek_Screws_{tag}", f"Screws fixing the {tag.lower()} cheek to the shoulder armour carrier.",
               zone=zp)

    # ── shoulder yaw actuator: the finned drum at the top of the upper arm ──
    d = mech.rotary_actuator("_yaw", 164, 96, Au @ T(0, 0, -100) @ R("X", 180), bolts=0, connector_angle=270 - 45 * s)
    a.take_rotary(d, "Shoulder_Yaw", "shoulder yaw")

    # ── upper-arm member: flange on the yaw output, neck, upper half of the elbow clamp ──
    bm = bmesh.new()
    P.merge(bm, P.cyl(132, 10, 48), T(0, 0, -204))
    P.merge(bm, P.loft([A.csec(-207, 84, 84, 0, 0, 0.16), A.csec(-246, 92, 106, 0, 0, 0.16)]))
    P.merge(bm, _half_clamp(False), T(0, 0, -PR.UPPER_ARM))
    P.merge(bm, P.box(40, 14, 30), T(0, 46, -232))                                   # connector boss
    um = a.add("Upper_Arm_Member", bm, "Upper-arm member: bolts to the yaw output and clamps the elbow actuator.", "alu",
               Au, bevel=1.0)
    for o in (1, -1):
        D.pocket_grid(um, Au @ T(o * 44.2, 0, -228) @ R("Y", o * 90), 1, 1, 22, 50, 0, 0, depth=6)
    seats = mech.ring((0, 0, -209), (0, 0, -1), 54, 8, x_hint=(1, 0, 0))
    a.take(mech.fasteners("_ub", seats, "M6", target=um, matrix=Au), "Upper_Arm_Flange_Bolts",
           "Screws clamping the upper-arm member to the shoulder yaw output flange.")

    # upper-arm armour: outer half-shell below the shoulder armour skirt
    zt = -164 if s > 0 else -136

    def usec(z):
        f = (z + 100) / -154.0
        return A.rsec(z, 2 * (102 - 9 * f), 2 * (93 - 12 * f), 0, 0, 50 - 6 * f)

    usecs = [usec(zt), usec(-254)]

    def open_upper(ob, lip=0.6):
        C.boolean_cut(ob, C.cutter(P.box(300, 400, 400), Au @ T(s * (38 - 150), 0, -200)), lip=lip)
        C.boolean_cut(ob, C.cutter(P.cyl(152, 500, 64), El @ R("Y", 90)), lip=lip)

    ush = a.add("Upper_Arm_Armour", A.shell(usecs, 10.0), "Armour half-shell over the outer side of the upper arm.",
                "armour", Au, bevel=1.2, seg=3)
    open_upper(ush)
    ucar = a.add("Upper_Arm_Armour_Carrier", A.hoops(usecs, (-222,), band=18.0),
                 "Carbon rib bonded inside the upper-arm armour.", "cfrp", Au, bevel=0.3, seg=1)
    open_upper(ucar, lip=None)
    posts = bmesh.new()
    for y in (-30, 30):
        P.merge(posts, P.cyl(14, 39, 16), T(s * 62, y, -222) @ R("Y", 90))
    a.add("Upper_Arm_Carrier_Standoffs", posts, "Standoff posts fixing the upper-arm armour carrier to the member.", "alu",
          Au, bevel=0.4, seg=1)
    pts = [Au @ Vector((s * 160, y, z)) for y in (-48, 48) for z in (zt - 20, -240)]
    a.take(mech.fasteners("_us", D.seats_on(ush, pts, _dir(Au, (s, 0, 0))), "M6", target=ush), "Upper_Arm_Armour_Screws",
           "Screws fixing the upper-arm armour to its carrier.")

    # ── elbow: finned actuator clamped by the upper arm, forearm hung on its two ends ──
    a.add("Elbow_Housing", _elbow_housing_bm(), "Cycloidal elbow actuator housing with cooling fins.", "alu",
          El @ R("Y", 90), bevel=0)
    a.add("Elbow_Clamp_Cap", _half_clamp(True), "Lower half of the split clamp holding the elbow actuator.", "ti", El,
          bevel=0.8)
    seats = [El @ T(x, y, -13.5) @ R("X", 180) for x in (-16, 16) for y in (-94, 94)]
    a.take(mech.fasteners("_ec", seats, "M10", washer=True), "Elbow_Clamp_Bolts",
           "Bolts closing the split clamp around the elbow actuator.")
    a.add("Elbow_Hard_Stop", D.hard_stop_bm(20, 30, 16), "Bumpered stop that limits elbow extension.", ["ti", "rubber"],
          El @ frame((s * 27, 94, 7), (s, 0, 0), (0, 0, -1)), bevel=0.5)
    cn, _ = H.connector("_ecn", Au @ Vector((0, 53, -232)), _dir(Au, (0, 1, 0)), 14.0)
    a.take(cn, "Elbow_Connector", "Power and encoder connector for the elbow actuator.")

    # ── forearm frame: hangers on the elbow, spine carrying the hand drive, roll actuator seat ──
    bm = bmesh.new()
    P.merge(bm, P.lug(56, 26, 106, 10, 40), frame((s * 68, 0, 0), (1, 0, 0), (0, 0, 1)))
    P.merge(bm, P.lug(50, 22, 106, 8, 40), frame((-s * 67, 0, 0), (1, 0, 0), (0, 0, 1)))
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(158, 92), 12), -126, -100))
    P.merge(bm, P.loft([A.csec(-124, 72, 66, 0, 0, 0.16), A.csec(-204, 62, 60, 0, 0, 0.16)]))
    P.merge(bm, P.cyl(112, 8, 48), T(0, 0, -206))
    P.merge(bm, P.box(33, 56, 12), T(s * 56.5, 76, -12))                              # arm that meets the elbow hard stop
    ff = a.add("Forearm_Frame", bm, "Forearm frame: hangs from the elbow actuator and carries the hand drive.", "alu",
               Af, bevel=1.0)
    for o in (1, -1):
        D.pocket_grid(ff, Af @ T(0, o * 31.8, -164) @ R("X", o * 90), 1, 1, 44, 56, 0, 0, depth=6)
    D.pocket_grid(ff, Af @ T(s * 73.2, 0, -72) @ R("Y", s * 90), 1, 1, 30, 56, 0, 0, depth=4)
    Eo = Af @ T(s * 73, 0, 0) @ R("Y", s * 90)                  # outer face of the outer hanger, +Z out
    ret = a.add("Elbow_Retainer", P.tube(110, 86, 8, 0.8),
                "Polished ring clamping the forearm hanger to the elbow output flange.", "steel", Eo @ T(0, 0, 4), bevel=0)
    a.take(mech.fasteners("_er", mech.ring((0, 0, 8), (0, 0, 1), 49, 8), "M6", target=ret, matrix=Eo),
           "Elbow_Retainer_Screws", "Screws through the retainer ring into the elbow output flange.")
    prof, rb, zl = D.bolted_cover_profile(40, 7, 0.0, 10.0, 4.0)
    dc = a.add("Elbow_Dust_Cover", P.revolve(prof, 48), "Dust cover over the elbow output bearing.", "alu", Eo, bevel=0.6)
    a.take(mech.fasteners("_ed", mech.ring((0, 0, zl), (0, 0, 1), rb, 6), "M4", target=dc, matrix=Eo),
           "Elbow_Dust_Cover_Screws", "Screws holding the elbow dust cover.")
    Ei = Af @ T(-s * 71, 0, 0) @ R("Y", -s * 90)
    a.add("Elbow_Encoder", D.encoder_bm(52), "Absolute encoder reading elbow angle at the idler end.",
          ["alu", "fastener"], Ei @ R("Z", -90 * s), bevel=0.4)

    # hand drive: six motors on the spine, their controller, tendons down into the roll shaft
    mb = bmesh.new()
    tend = bmesh.new()
    for y in (-46, 46):
        for x in (-25, 0, 25):
            P.merge(mb, P.revolve([(0, 0), (13, 0), (13, 52), (11, 54), (11, 60), (5, 62), (0, 62)], 20), T(x, y, -194))
            path = P.catmull([(x, y, -194), (x * 0.7, y * 0.8, -203), (x * 0.36, y * 0.22, -209)], step=3.0)
            P.merge(tend, P.sweep(path, 3.2, 8))
        P.merge(mb, P.box(84, 6, 16), T(0, y * 0.74, -150))
        P.merge(mb, P.box(84, 6, 10), T(0, y * 0.74, -186))
    a.add("Hand_Drive_Motors", mb, "Six motors driving the finger and thumb tendons.", "alu", Af, bevel=0.4, seg=1)
    a.add("Hand_Drive_Tendons", tend, "Sheathed tendons running from the hand drive into the hollow roll shaft.", "rubber",
          Af, bevel=0)
    a.add("Hand_Drive_Controller", D.finned_block_bm(64, 84, 20, 8), "Motor controller for the hand drive, with its heat sink.",
          "alu", Af @ T(s * 33, 0, -164) @ R("Y", s * 90) @ R("Z", 90), bevel=0.3, seg=1)

    # forearm roll: hollow-shaft actuator and the bearing that carries the wrist
    d = mech.rotary_actuator("_fr", 100, 50, Af @ T(0, 0, -210) @ R("X", 180), bolts=8, connector_angle=270)
    a.take_rotary(d, "Forearm_Roll", "forearm roll")
    a.add("Forearm_End_Ring", P.tube(126, 113, 12, 1.0), "End ring of the forearm, seating the wrist bearing.", "alu",
          Af @ T(0, 0, -257), bevel=0)
    a.take(mech.bearing("_rb", 112, 82, 10, Af @ T(0, 0, -262)), "Forearm_Roll_Bearing",
           "Bearing carrying the wrist on the end of the forearm.")

    # ── forearm armour: one thick shell, clamshell split, hatches front and rear ──
    fsecs = [A.rsec(-40, 150, 160, 0, 0, 40), A.rsec(-112, 192, 198, 0, 4, 50), A.rsec(-214, 176, 182, 0, 2, 46),
             A.rsec(-262, 134, 140, 0, 0, 38)]

    def open_fore(ob, lip=0.6):
        C.boolean_cut(ob, C.cutter(P.cyl(220, 500, 64), Af @ R("Y", 90)), lip=lip)          # room for the elbow
        C.boolean_cut(ob, C.cutter(P.box(400, 130, 100), Af @ T(0, -105, -50)), lip=lip)    # front trimmed for flexion

    fsh = raw(A.shell(fsecs, 10.0), Af, "armour", 1.2, 3)
    open_fore(fsh)
    A.gap_cut(fsh, Af @ Vector((0, 0, -150)), _dir(Af, (1, 0, 0)))
    pieces = sorted(A.islands(fsh), key=lambda o: -len(o.data.vertices))[:2]
    inner_h, outer_h = sorted(pieces, key=lambda o: _local(Af, o).x * s)
    a.take(outer_h, "Forearm_Armour_Outer", "Outer half of the forearm armour, vented over the hand drive controller.")
    a.take(inner_h, "Forearm_Armour_Inner", "Inner half of the forearm armour.")
    seat = D.seats_on(outer_h, [Af @ Vector((s * 150, 0, -164))], _dir(Af, (s, 0, 0)), x_hint=_dir(Af, (0, 1, 0)))[0]
    A.slots(outer_h, seat, 4, 66, 7, 15, depth=24)
    vb = bmesh.new()
    uv = vb.loops.layers.uv.new("UVMap")
    fc = vb.faces.new([vb.verts.new((x, y, 0)) for x, y in P.rrect(84, 66, 4)])
    for lp in fc.loops:
        lp[uv].uv = (lp.vert.co.x * C.MM, lp.vert.co.y * C.MM)
    a.add("Forearm_Vent_Screen", vb, "Mesh screen behind the forearm cooling slots.", "mesh", seat @ T(0, 0, -12.5), bevel=0)
    for ob, o, tag, hs in ((outer_h, s, "Front", "L"), (inner_h, -s, "Rear", "R")):
        fy = -1 if tag == "Front" else 1
        seat = D.seats_on(ob, [Af @ Vector((o * 44, fy * 160, -166))], _dir(Af, (0, fy, 0)), x_hint=_dir(Af, (1, 0, 0)))[0]
        h = F.hatch("_fh", 66, 92, seat, target=ob, hinge_side=hs, fasteners=3)
        a.take(h["door"], f"Forearm_Hatch_{tag}", f"{tag} access panel over the hand drive motors.")
        a.take(h["hinge"], f"Forearm_Hatch_{tag}_Hinge", f"Hinge of the {tag.lower()} forearm access panel.")
        a.take(h["fasteners"], f"Forearm_Hatch_{tag}_Quarter_Turns",
               f"Quarter-turn fasteners latching the {tag.lower()} forearm access panel.")
    seat = D.seats_on(outer_h, [Af @ Vector((s * 50, 160, -170))], _dir(Af, (0, 1, 0)), x_hint=_dir(Af, (0, 0, -1)))[0]
    a.add("Forearm_Wear_Plate", P.prism(P.rrect(136, 36, 8), 0, 5), "Replaceable wear plate along the outer edge of the forearm.",
          "ti", seat, bevel=0.6)
    a.take(mech.fasteners("_fw", [seat @ T(x, 0, 5) for x in (-52, 0, 52)], "M6", "csk"), "Forearm_Wear_Plate_Screws",
           "Countersunk screws holding the forearm wear plate.")
    fcar = a.add("Forearm_Armour_Carrier", A.hoops(fsecs, (-130, -238), band=18.0),
                 "Carbon ribs bonded inside the forearm armour.", "cfrp", Af, bevel=0.3, seg=1)
    open_fore(fcar, lip=None)
    posts = bmesh.new()
    for x in (-52, 52):
        P.merge(posts, P.cyl(14, 15, 16), T(x * 1.1, 0, -238) @ R("Y", 90))
        P.merge(posts, P.cyl(14, 40, 16), T(x * 1.16, 0, -130) @ R("Y", 90))
    a.add("Forearm_Carrier_Standoffs", posts, "Standoff posts fixing the forearm armour carrier to the frame.", "alu", Af,
          bevel=0.4, seg=1)
    for ob, o, tag in ((outer_h, s, "Outer"), (inner_h, -s, "Inner")):
        pts = [Af @ Vector((o * 150, y, z)) for y in (-62, 62) for z in (-124, -228)]
        a.take(mech.fasteners("_fs", D.seats_on(ob, pts, _dir(Af, (o, 0, 0))), "M6", target=ob), f"Forearm_{tag}_Screws",
               f"Screws fixing the {tag.lower()} forearm armour half to its carrier.")
    F.panel_cut(inner_h, [Af @ Vector((-s * 104, y, -176)) for y in range(-60, 61, 8)], 1.5, 2.0)
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    s = 1 if a.aa == "07" else -1
    W = FR.torso()
    sv0, au0, af0, _ = FR.arm(s)
    S = W @ sv0
    sh = [o for o in objs if "Shoulder" in o.name or "Pauldron" in o.name]
    RV.closeup(sh, out / f"{a.aa}_shoulder_front_clay{tag}.jpg", f"{a.aa} shoulder, front", (s * 0.45, -1, 0.12), "clay",
               target=S + Vector((s * 20, 0, -30)), dist=5.0)
    RV.closeup(sh, out / f"{a.aa}_shoulder_rear_final{tag}.jpg", f"{a.aa} shoulder, rear", (s * 0.6, 1, 0.15), "final",
               target=S + Vector((s * 20, 0, -30)), dist=5.0, isolate=True)
    el = [o for o in objs if "Elbow" in o.name or "Forearm" in o.name or "Upper_Arm" in o.name or "Hand_Drive" in o.name]
    ec = (W @ au0 @ T(0, 0, -PR.UPPER_ARM)).translation
    RV.closeup(el, out / f"{a.aa}_elbow_outer_clay{tag}.jpg", f"{a.aa} elbow, outer three-quarter", (s * 1.0, -0.55, 0.1),
               "clay", target=ec + Vector((0, 0, -60)), dist=4.4)
    RV.closeup(el, out / f"{a.aa}_elbow_rear_final{tag}.jpg", f"{a.aa} elbow, rear three-quarter", (s * 0.7, 0.9, 0.1),
               "final", target=ec + Vector((0, 0, -60)), dist=4.4)
    RV.closeup(objs, out / f"{a.aa}_arm_inner_clay{tag}.jpg", f"{a.aa} arm, inner side", (-s * 1.0, -0.35, 0.05), "clay",
               res=(1000, 1500), dist=5.0, isolate=True)
