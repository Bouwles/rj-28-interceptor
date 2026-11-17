"""Assembly 01: head and cap. The signature of the machine.

A faceless sensor head: one raked faceplate with a single slit and an
off-centre lens cluster, under a rigid armoured cap worn backwards. The cap
gets its identity from shape alone: six-panel crown with real seams, antenna
puck where the button would be, snapback arch with strap and studs on the
forehead, stiff curved brim over the nape.

Built in body coordinates (FR.torso() applied). Faceplate frame Fm: X lateral,
Y up the plate, +Z out of the face. Cap frame Cm: origin at the centre of the
crown base, +Y to the rear (brim side), +Z up through the crown.
"""
import math

import bmesh
from mathutils import Vector

from .. import frames as FR, params as PR
from ..lib import armour as A, core as C, detail as D, fittings as F, harness as H, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm, raw

Z0, Z1 = 1538.0, 1632.0                  # skull base, skull top (under the cap)
RAKE = math.tan(math.radians(PR.FACE_RAKE))
ZC = 1598.0                              # faceplate datum height
SHEAR = 14.0                             # crown high point sits this far towards the brim


def front(z):
    """Y of the skull's front surface at height z (raked: the top is further forward)."""
    return -86.0 - (z - Z0) * RAKE


def cap_frame():
    tilt = math.degrees(math.atan2(PR.CAP_FRONT_Z - PR.CAP_REAR_Z, PR.CAP_L))
    base_z = (PR.CAP_FRONT_Z + PR.CAP_REAR_Z) / 2
    h = (PR.Z_CROWN - PR.CAP_BUTTON_H * 0.55 - base_z) / math.cos(math.radians(tilt))
    return tilt, h, FR.torso() @ T(0, PR.CAP_Y, base_z) @ R("X", -tilt)


def crown_uv(a, phi, h):
    """Point on the crown at plan angle a and latitude phi (0 at the base, pi/2 at the top)."""
    t = math.sin(phi) ** 0.8
    k = math.cos(phi) ** 0.8
    c, s = math.cos(a), math.sin(a)
    return Vector((PR.CAP_W / 2 * math.copysign(abs(c) ** (2 / 2.2), c) * k,
                   PR.CAP_L / 2 * math.copysign(abs(s) ** (2 / 2.2), s) * k + SHEAR * t ** 1.4, h * t))


def crown_normal(a, phi, h):
    """Outward unit normal of the crown at (a, phi)."""
    e = 1e-3
    phi = min(max(phi, 2 * e), math.pi / 2 - 2 * e)
    n = (crown_uv(a + e, phi, h) - crown_uv(a - e, phi, h)).cross(crown_uv(a, phi + e, h) - crown_uv(a, phi - e, h))
    n.normalize()
    return n if n.z >= 0 or True and n.dot(crown_uv(a, phi, h) - Vector((0, 0, -h))) > 0 else -n


def crown_pt(a, z, h, grow=0.0):
    """Point on the crown at plan angle a and height z above its base, pushed out by grow."""
    t = min(max(z / h, 0.0), 1.0)
    k = math.cos(math.asin(t ** 1.25)) ** 0.8
    c, s = math.cos(a), math.sin(a)
    x = PR.CAP_W / 2 * math.copysign(abs(c) ** (2 / 2.2), c) * k
    y = PR.CAP_L / 2 * math.copysign(abs(s) ** (2 / 2.2), s) * k
    r = math.hypot(x, y) or 1.0
    return (x + grow * x / r, y + grow * y / r + SHEAR * t ** 1.4, z)


def crown_bm(h, inset=0.0):
    bm = P.dome(PR.CAP_W - 2 * inset, PR.CAP_L - 2 * inset, h - inset, 48, 12, 2.2, 2.5)
    for v in bm.verts:
        v.co.y += SHEAR * (v.co.z / h) ** 1.4
    return bm


def band_bm(h, z0, z1, grow, thick, a0=None, a1=None, n=48, rows=2):
    """Strip that hugs the crown between heights z0 and z1: a full ring, or an arc a0..a1."""
    bm = bmesh.new()
    full = a0 is None
    cnt = n if full else n + 1
    a0, a1 = (0.0, 2 * math.pi) if full else (a0, a1)
    grid = [[bm.verts.new(crown_pt(a0 + (a1 - a0) * i / n, z0 + (z1 - z0) * j / (rows - 1), h, grow))
             for i in range(cnt)] for j in range(rows)]
    for j in range(rows - 1):
        for i in range(n):
            k = (i + 1) % cnt
            bm.faces.new((grid[j][i], grid[j][k], grid[j + 1][k], grid[j + 1][i]))
    return P.thicken(bm, thick, center=(0, 0, (z0 + z1) / 2))


def build():
    a = Asm("01")
    W = FR.torso()
    Pm = W @ T(0, front(ZC) - 1, ZC) @ R("X", 90 + PR.FACE_RAKE)        # back face of the faceplate
    Fm = Pm @ T(0, 0, 7)                                                 # its outer face
    dz = (PR.Z_SLIT - ZC) / math.cos(math.radians(PR.FACE_RAKE))         # slit centre, up the plate
    tilt, h, Cm = cap_frame()

    # ── skull: frame inside, two-piece shell outside ────────────────────────
    bm = bmesh.new()
    P.merge(bm, P.revolve(P.ring_profile(34, 62, Z0 + 8, Z0 + 16, 1.5), 48), T(0, 4, 0))     # seat of the neck's head yoke
    side = [(front(Z0 + 8) + 16, Z0 + 8), (62, Z0 + 8), (70, Z1 + 6), (front(Z1 + 6) + 16, Z1 + 6)]
    for o in (1, -1):
        P.merge(bm, P.prism(P.chamfer_poly(side, 8), -3, 3), T(o * 66, 0, 0) @ R("Z", 90) @ R("X", 90))
        P.merge(bm, P.box(18, 16, 18), T(o * 46, 64, 1603))                      # neck actuator fork seats
        P.merge(bm, P.box(8, 12, 60), T(o * 59, 64, 1582))                       # ... tied into the side plates
    P.merge(bm, P.box(128, 150, 6), T(0, -12, Z1 + 5))                            # top deck under the cap
    P.merge(bm, P.box(126, 5, 76), T(0, front(1590) + 20, 1590) @ R("X", PR.FACE_RAKE))   # sensor bulkhead
    P.merge(bm, P.box(126, 8, 12), T(0, 40, Z0 + 8))                              # base cross-tie
    sf = a.add("Skull_Frame", bm, "Machined frame carrying the faceplate, sensors, electronics and cap.", "alu", W,
               bevel=0.6)
    for o in (1, -1):
        D.pocket_grid(sf, W @ T(o * 69.2, -4, 1590) @ R("Y", o * 90), 2, 2, 28, 44, 38, 58, depth=3.2)
    C.boolean_cut(sf, C.cutter(P.box(134, 30, 9), Pm @ T(0, dz, -24)), lip=0.3)   # camera window in the bulkhead

    secs = []
    for zz, w, back, r in ((Z0, 148, 78, 26), (1590, 164, 88, 34), (Z1, 170, 91, 42)):   # top kept narrow: the barrel traverses past it
        d = back - front(zz)
        secs.append(A.rsec(zz, w, d, 0, (back + front(zz)) / 2, r))
    bay = P.chamfer_poly([(-54, -43), (54, -43), (64, 29), (-64, 29)], 10)

    def trim(ob, lip=0.5):
        """Sensor bay opening, and a slanted top that tucks under the cap."""
        A.opening(ob, bay, Fm, depth=40, above=12, lip=lip)
        C.boolean_cut(ob, C.cutter(P.box(420, 420, 200), Cm @ T(0, 0, 100 - 3.0)), lip=lip)

    sk = raw(A.shell(secs, 6.0), W, "armour", 1.0, 3)
    trim(sk)
    A.gap_cut(sk, W @ Vector((0, 18, 1590)), (0, 1, 0))
    pieces = sorted(A.islands(sk), key=lambda o: -len(o.data.vertices))[:2]
    pieces.sort(key=lambda o: C.bounds_mm([o])[0].y)
    a.take(pieces[0], "Skull_Shell_Front", "Front skull shell: seats the faceplate and wraps the cheeks.")
    rear = a.take(pieces[1], "Skull_Shell_Rear", "Rear skull shell closing the back of the head above the neck.")
    liner = a.add("Skull_Liner", D.rib_ring_bm(secs, 1.6, 6.6), "Carbon liner behind the skull shells; backs the panel seams.",
                  "cfrp", W, bevel=0.2, seg=1)
    trim(liner, lip=None)
    seat = D.seats_on(rear, [W @ Vector((0, 220, 1581))], (0, 1, 0), x_hint=(1, 0, 0))[0]
    hd = F.hatch("_dh", 46, 26, seat, target=rear, hinge_side="L", fasteners=2, corner=4.0)
    a.take(hd["door"], "Data_Port_Door", "Door over the maintenance data port at the back of the head.")
    a.take(hd["hinge"], "Data_Port_Hinge", "Hinge of the data port door.")
    a.take(hd["fasteners"], "Data_Port_Quarter_Turns", "Quarter-turn fasteners latching the data port door.")

    # ── faceplate: one flat raked plate, one slit, one off-centre lens cluster ──
    fp = P.chamfer_poly([(-62, -50), (62, -50), (72.5, 36), (-72.5, 36)], [16, 16, 10, 10])
    face = raw(P.plate(fp, 7), Pm, "armour", 1.2, 3)
    A.recess(face, P.rrect(128, 19, 5), Fm @ T(0, dz, 0), depth=2.0)
    A.opening(face, P.rrect(PR.SLIT_W + 2, PR.SLIT_H + 2, 4), Fm @ T(0, dz, 0), depth=14, above=6, lip=0.4)
    A.opening(face, P.rrect(28, 38, 9), Fm @ T(44, -12, 0), depth=14, above=6, lip=0.4)
    a.take(face, "Faceplate", "Raked composite faceplate; the only openings are the sensor slit and the lens cluster.")
    a.add("Slit_Bezel", P.ring_solid(P.rrect(128, 19, 5), P.rrect(PR.SLIT_W, PR.SLIT_H, 3), -7.0, -2.0),
          "Recessed bezel framing the sensor slit and clamping its window.", "alu", Fm @ T(0, dz, 0), bevel=0.4)
    a.add("Slit_Window", P.prism(P.rrect(PR.SLIT_W + 4, PR.SLIT_H + 3, 3.5), -PR.SLIT_RECESS - 1.6, -PR.SLIT_RECESS),
          "Smoked window set back in the slit, protecting the stereo cameras.", "glass", Fm @ T(0, dz, 0), bevel=0.2,
          seg=1)
    a.add("Slit_Emitter", P.prism(P.rrect(108, 2.2, 1.0), -8.4, -7.8), "Cyan status strip along the foot of the slit, "
          "behind the window.", "emissive", Fm @ T(0, dz - 3.4, 0), bevel=0)
    a.add("Camera_Bracket", P.prism(P.chamfer_poly(P.rrect(120, 18), 4), -26.0, -22.0),
          "Bracket holding the stereo camera pair at a fixed baseline behind the slit.", "alu", Fm @ T(0, dz, 0),
          bevel=0.4)
    for o, tag in ((1, "Left"), (-1, "Right")):
        cam = P.cyl(15, 13, 24)
        cam.transform(T(0, 0, -15.5))
        P.merge(cam, P.cyl(11, 1.2, 24), T(0, 0, -8.6), mat_index=1)
        a.add(f"Stereo_Camera_{tag}", cam, f"{tag} camera of the forward stereo pair.", ["fastener", "glass"],
              Fm @ T(o * 38, dz + 0.8, 0), bevel=0.3, seg=1)

    bez = a.add("Lens_Cluster_Bezel", P.prism(P.rrect(32, 42, 10), -7.0, 4.5),
                "Shared bezel for the thermal imager, lidar window and spotter camera on the left cheek.", "alu",
                Fm @ T(44, -12, 0), bevel=0.6)
    cut = bmesh.new()
    # a tight triangle: big thermal objective above, lidar and spotter side by side below
    lenses = (("Thermal_Imager_Lens", 20.0, 44.0, -4.0, "Germanium objective of the thermal imager."),
              ("Lidar_Window", 13.0, 37.5, -22.0, "Flat window of the scanning lidar."),
              ("Spotter_Camera_Lens", 9.0, 52.0, -23.0, "Objective of the long-focus spotter camera."))
    for _n, d, x, y, _f in lenses:
        P.merge(cut, P.cyl(d + 0.4, 40, 32), T(x, y, 0))
    C.boolean_cut(bez, C.cutter(cut, Fm), lip=0.3)
    for n, d, x, y, fn in lenses:
        lens = P.tube(d, d - 3.0, 7.0, 0.5, 32)
        P.merge(lens, P.cyl(d - 3.0, 2.0, 32), T(0, 0, 1.0), mat_index=1)
        a.add(n, lens, fn, ["fastener", "glass"], Fm @ T(x, y, 1.6), bevel=0)
    a.add("Lidar_Unit", P.cyl(20, 34, 32), "Scanning lidar body behind its cheek window.", "alu",
          Fm @ T(37.5, -22, -26), bevel=0.8)
    a.add("Thermal_Imager_Core", P.box(24, 18, 24), "Uncooled thermal imager core behind its objective.", "alu",
          Fm @ T(46, -2, -21), bevel=0.8)

    jaw = a.add("Jaw_Guard", P.loft([A.csec(0, 62, 30, 0, 0, 0.2), A.csec(13, 50, 20, 0, -1, 0.24)]),
                "Short guard under the slit with two louvred intakes for the sensor bay.", "armour",
                Fm @ T(-8, -33, 0), bevel=1.0, seg=3)
    for o in (1, -1):
        A.slots(jaw, Fm @ T(-8 + o * 12, -34, 13), 3, 14, 2.2, 4.6, depth=8, lip=0.2)

    # ── electronics under the cap ───────────────────────────────────────────
    board = P.box(98, 72, 2)
    for x in (-42, 42):
        for y in (-30, 30):
            P.merge(board, P.cyl(5, 7, 12), T(x, y, -4.5))
    a.add("Processor_Board", board, "Sensor fusion board on standoffs above the skull frame.", "cfrp",
          W @ T(0, -32, Z1 + 16), bevel=0.2, seg=1)
    a.add("Heat_Spreader", D.finned_block_bm(82, 58, 20, fins=10), "Finned heat spreader; its air exits through the "
          "cap's forehead mesh.", "alu", W @ T(0, -32, Z1 + 17), bevel=0.3, seg=1)
    conn, tail = H.connector("_nc", W @ Vector((0, 58, Z0 + 2)), (0, 0, -1), 16.0)
    a.take(conn, "Neck_Connector", "Bulkhead connector carrying head power and data down through the neck.")
    for i, x in enumerate((-16, 16)):
        pts = [W @ Vector((x, 2, Z1 + 16)), W @ Vector((x * 1.4, 34, Z1 - 6)), W @ Vector((x * 0.9, 54, 1590)),
               W @ Vector((x * 0.4, 58, Z0 + 16))]
        a.take(H.cable("_hc", pts, 3.2, sag=0.0), f"Head_Harness_{'AB'[i]}",
               "Braided harness from the processor board to the neck connector.")

    # ── cap ─────────────────────────────────────────────────────────────────
    crown = raw(P.thicken(crown_bm(h), PR.CAP_SHELL), Cm, "cap", 1.0, 3)
    phi0 = math.asin((6.0 / h) ** 1.25)
    for k in range(3):                                           # three cuts make the six panel seams
        ang = math.radians(30 + 60 * k)
        lats = [phi0 + (math.radians(87) - phi0) * i / 22 for i in range(23)]
        path = [Cm @ (crown_uv(ang + math.pi, p_, h) + crown_normal(ang + math.pi, p_, h) * 2.5) for p_ in lats]
        path.append(Cm @ Vector((0, SHEAR, h + 2.5)))
        path += [Cm @ (crown_uv(ang, p_, h) + crown_normal(ang, p_, h) * 2.5) for p_ in reversed(lats)]
        F.panel_cut(crown, path, PR.SEAM_W, PR.SEAM_D)
    arch = [(33, 14)] + [(33 * math.cos(math.radians(d)), 24 + 26 * math.sin(math.radians(d))) for d in range(0, 181, 12)] \
        + [(-33, 14)]
    C.boolean_cut(crown, C.cutter(P.prism(arch, 40, 140), Cm @ R("X", 90)), lip=0.5)
    a.take(crown, "Cap_Crown", "Rigid six-panel crown shell: armour over the cranium and housing for the head electronics.",
           zone="cap")
    a.add("Cap_Carrier", band_bm(h, 2.0, 16.0, -4.5, 3.0), "Carbon ring inside the crown that bolts the cap to the skull frame.",
          "cfrp", Cm, bevel=0.3, seg=1, zone="cap")
    rim_o = [crown_pt(2 * math.pi * i / 48, 0.0, h, -0.6)[:2] for i in range(48)]
    rim_i = [crown_pt(2 * math.pi * i / 48, 0.0, h, -27.0)[:2] for i in range(48)]
    a.add("Cap_Base_Flange", P.ring_solid(rim_o, rim_i, -2.6, -0.4), "Flange closing the underside of the cap rim onto the "
          "skull.", "cfrp", Cm, bevel=0.3, seg=1, zone="cap")
    sb = a.add("Cap_Sweatband", band_bm(h, 0.0, 10.0, 0.9, 1.6), "Clamp band round the base of the crown, in a satin finish.",
               "cfrp", Cm, bevel=0.4, seg=1, zone="cap")
    pts = [Cm @ Vector(crown_pt(math.radians(d), 5.0, h, 30.0)) for d in (48, 132, 228, 312)]
    seats = []
    for p_, d in zip(pts, (48, 132, 228, 312)):
        n = (Cm.to_3x3() @ Vector((math.cos(math.radians(d)), math.sin(math.radians(d)), 0))).normalized()
        seats += D.seats_on(sb, [p_ - n * 30.0], n)
    a.take(mech.fasteners("_cs", seats, "M4", "csk", target=sb), "Cap_Retaining_Screws",
           "Four countersunk screws holding the cap to the skull frame through the band.", zone="cap")

    # snapback arch: mesh-backed exhaust, strap bar with seven studs across its foot
    a0, a1 = math.radians(270 - 26), math.radians(270 + 26)
    mesh = bmesh.new()
    uv = mesh.loops.layers.uv.new("UVMap")
    grid = [[mesh.verts.new(crown_pt(a0 + (a1 - a0) * i / 12, 10 + 44 * j / 8, h, -PR.CAP_SHELL - 0.6)) for i in range(13)]
            for j in range(9)]
    for j in range(8):
        for i in range(12):
            f = mesh.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
            for lp in f.loops:
                lp[uv].uv = (lp.vert.co.x * C.MM, lp.vert.co.z * C.MM)
    a.add("Cap_Arch_Mesh", mesh, "Fine mesh across the forehead arch: exhaust for the head electronics.", "mesh", Cm,
          bevel=0, zone="cap")
    a.add("Cap_Arch_Baffle", band_bm(h, 8.0, 56.0, -12.0, 1.5, a0 - 0.08, a1 + 0.08, 12, 5),
          "Dark baffle behind the arch mesh that hides the electronics from view.", "cavity", Cm, bevel=0, zone="cap")
    b0, b1 = math.radians(270 - 31), math.radians(270 + 31)
    a.add("Cap_Strap", band_bm(h, 8.5, 17.5, 1.6, 3.2, b0, b1, 14, 2),
          "Strap bar bridging the foot of the arch, stiffening the cut-out.", "cap", Cm, bevel=0.6, zone="cap")
    studs = bmesh.new()
    for i in range(7):
        ang = b0 + (b1 - b0) * (i + 1.5) / 10
        p0 = Vector(crown_pt(ang, 13.0, h, 1.6))
        n = Vector((p0.x, p0.y - SHEAR * (13.0 / h) ** 1.4, 0)).normalized()
        P.merge(studs, P.cyl(6.4, 2.6, 6), frame(p0 + n * 1.3, n))
    a.add("Cap_Strap_Studs", studs, "Seven hex studs locking the strap bar, where a snapback has its pegs.", "fastener",
          Cm, bevel=0.2, seg=1, zone="cap")

    # antenna puck where the button would be
    top = Vector((0, SHEAR, h))
    puck = [(0, -1.0), (PR.CAP_BUTTON_D / 2, -1.0), (PR.CAP_BUTTON_D / 2, PR.CAP_BUTTON_H - 2.5),
            (PR.CAP_BUTTON_D / 2 - 2.5, PR.CAP_BUTTON_H), (0, PR.CAP_BUTTON_H)]
    a.add("Antenna_Puck", P.revolve(puck, 40), "Low-profile antenna where a cap has its button.", "alu",
          Cm @ T(*top) @ T(0, 0, -PR.CAP_BUTTON_H * 0.3), bevel=0.4, zone="cap")
    a.add("Antenna_Gasket", P.revolve(P.ring_profile(PR.CAP_BUTTON_D / 2 - 0.5, PR.CAP_BUTTON_D / 2 + 1.6, -1.4, 0.4, 0.3), 40),
          "Gasket sealing the antenna puck to the crown.", "rubber", Cm @ T(*top) @ T(0, 0, -PR.CAP_BUTTON_H * 0.3),
          bevel=0, zone="cap")

    # brim: stiff crescent over the nape, edges curved down, raked 12 degrees
    b_a0 = math.acos((PR.BRIM_W / PR.CAP_W) ** 1.1)
    ys = crown_pt(b_a0, 0, h)[1]
    n_ = 2.8
    tip = PR.CAP_L / 2 + PR.BRIM_L
    outer = [(PR.BRIM_W / 2 * math.copysign(abs(math.cos(u)) ** (2 / n_), math.cos(u)),
              ys - 4 + (tip - ys + 4) * math.sin(u) ** (2 / n_)) for u in [math.pi * i / 32 for i in range(33)]]
    inner = [(x * 0.97, y - 3.0) for x, y, _z in (crown_pt(b_a0 + (math.pi - 2 * b_a0) * (1 - i / 18), 0, h)
                                                   for i in range(1, 18))]
    Bm = Cm @ T(0, 96, 0) @ R("X", -(PR.BRIM_RAKE - tilt)) @ T(0, -96, -1)
    a.add("Cap_Brim", P.plate(outer + inner, PR.BRIM_T, crown=9, slices=14),
          "Stiff brim over the nape: shades and shelters the rear-aspect sensors under its lip.", "cap", Bm, bevel=1.7,
          seg=3, zone="cap")
    a.add("Rear_Sensor_Bar", P.prism(P.chamfer_poly(P.rrect(106, 11), 2.5), 0, 7.5),
          "Housing under the brim lip for the three rear-aspect sensors.", "alu", Bm @ T(0, tip - 15.5, 1.6), bevel=0.4,
          zone="cap")
    for i, x in enumerate((-31, 0, 31)):
        a.add(f"Rear_Sensor_Window_{i + 1}", P.prism(P.rrect(19, 4.6, 1.6, 3), 0, 1.2),
              "Flush window of a rear-aspect sensor.", "glass", Bm @ T(x, tip - 10, 5.4) @ R("X", -90), bevel=0, zone="cap")
    for i, x in enumerate((-47, 47)):
        a.add(f"Brim_Status_LED_{i + 1}", P.cyl(3.2, 1.2, 12), "Status indicator visible from behind.", "emissive",
              Bm @ T(x, tip - 10, 5.4) @ R("X", -90), bevel=0, zone="cap")
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    c = FR.torso() @ Vector((0, 10, 1640))
    for name, d, mode in (("front", (-0.45, -1.0, 0.12), "clay"), ("rear", (0.55, 1.0, 0.25), "clay"),
                          ("side", (1.0, 0.05, 0.08), "clay"), ("front_final", (-0.5, -1.0, 0.1), "final"),
                          ("rear_final", (0.6, 1.0, 0.3), "final")):
        RV.closeup(objs, out / f"01_head_{name}{tag}.jpg", f"01 head and cap, {name}", d, mode, isolate=True,
                   target=c, dist=2.4, res=(1300, 1100))
