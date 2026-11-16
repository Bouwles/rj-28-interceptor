"""Phase 2 blockout: the whole robot from simple volumes at exact proportions,
in the final pose, with both mount states. Produces the G1 review sheets.

Volumes here are stand-ins. Each is replaced by real plates, housings and
joints in Phase 3; the frames, landmarks and envelopes carry over unchanged.
"""
import json
import math

import bpy
from mathutils import Vector

from .. import frames as FR, materials as M, params as PR, poses, render as RD
from ..lib import core as C, fittings as F, prims as P
from ..lib.core import T, R


def side(s):
    return "L" if s > 0 else "R"


def oct8(c=0.2):
    h = 0.5
    return [(h - c, -h), (h, -h + c), (h, h - c), (h - c, h), (-h + c, h), (-h, h - c), (-h, -h + c), (-h + c, -h)]


def sec(z, w, d, dx=0.0, dy=0.0, c=0.2):
    """Chamfered-rectangle section: w along X, d along Y, at height z."""
    return [(x * w + dx, y * d + dy, z) for x, y in oct8(c)]


def ends(outline, z0, z1, end=14.0, k=0.9):
    """Prism whose two ends are pulled in, so the end faces get a broad chamfer."""
    cx = sum(p[0] for p in outline) / len(outline)
    cy = sum(p[1] for p in outline) / len(outline)
    small = [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in outline]
    return P.loft([P.at_z(small, z0), P.at_z(outline, z0 + end), P.at_z(outline, z1 - end), P.at_z(small, z1)])


class Blk:
    def __init__(self):
        self.co = C.coll("Blockout")
        self.O = T()                    # placement offset for whatever is being built

    def add(self, name, bm, matrix=None, mat="armour", bevel=3.0, zone="body", seg=2, group=None):
        matrix = self.O @ matrix if matrix is not None else self.O.copy()
        ob = C.obj_from_bm("BLK_" + name, bm, matrix, self.co, M.get(mat), bevel=bevel, segments=seg)
        ob["zone"] = zone
        if group:
            ob["mount_group"] = group
        return ob

    def rod(self, name, p0, p1, d, mat, zone, bevel=1.5, group=None):
        p0, p1 = Vector(p0), Vector(p1)
        return self.add(name, P.cyl(d, (p1 - p0).length), C.frame((p0 + p1) / 2, p1 - p0), mat, bevel, zone,
                        group=group)

    def strut(self, name, p0, p1, body_d, rod_d, zone):
        """Stand-in for a linear actuator: fat body from p0, polished rod to p1."""
        p0, p1 = Vector(p0), Vector(p1)
        mid = p0 + (p1 - p0) * 0.62
        self.rod(name + "_Body", p0, mid, body_d, "alu", zone)
        self.rod(name + "_Rod", mid, p1, rod_d, "steel", zone, 0.8)


# ── legs and feet ────────────────────────────────────────────────────────────
def legs(b):
    for s in (1, -1):
        n = side(s)
        zl, zf = f"leg_{n}", f"foot_{n}"
        Lg, Th, Kn, Sh, An, Ft = FR.leg(s)

        # hip pitch drum: the top of the thigh is the actuator housing
        b.add(f"Hip_Pitch_{n}", P.cyl(174, 150, 64), Lg @ T(s * 8, 0, 0) @ R("Y", 90), "alu", 3, zl)
        b.add(f"Hip_Pitch_Cap_{n}", P.cyl(124, 14, 48), Lg @ T(s * 89, 0, 0) @ R("Y", 90), "ti", 2, zl)

        th = P.loft([sec(-78, 152, 192, -10 * s, -14), sec(-130, 206, 204, 4 * s, -18),
                     sec(-200, 212, 206, 4 * s, -18), sec(-300, 190, 186, 0, -14), sec(-372, 166, 166, 0, -8)])
        b.add(f"Thigh_Armour_{n}", th, Th, "armour", 6, zl, 3)
        b.add(f"Thigh_Frame_{n}", P.loft([sec(-60, 64, 60, 0, 92), sec(-392, 60, 54, 0, 78)]), Th, "alu", 2.5, zl)

        b.add(f"Knee_Barrel_{n}", P.cyl(124, 160, 48), Kn @ R("Y", 90), "ti", 2, zl)
        b.add(f"Knee_Bearing_{n}O", P.cyl(152, 26, 64), Kn @ T(s * 96, 0, 0) @ R("Y", 90), "alu", 3, zl)
        b.add(f"Knee_Bearing_{n}I", P.cyl(132, 12, 64), Kn @ T(-s * 86, 0, 0) @ R("Y", 90), "alu", 2, zl)
        for o in (1, -1):
            b.strut(f"Knee_Act_{n}{'O' if o * s > 0 else 'I'}", Th @ Vector((o * 50, 104, -112)),
                    Sh @ Vector((o * 50, 86, -12)), 46, 30, zl)
        kg = P.plate(P.chamfer_poly(P.rrect(126, 152), 26), 13, crown=9, slices=8)
        b.add(f"Knee_Guard_{n}", kg, Kn @ T(0, -92, 4) @ R("X", 86), "armour", 3, zl, 3)

        sh = P.loft([sec(-40, 168, 164, 0, -8), sec(-112, 190, 196, 0, -2), sec(-236, 170, 160, 0, -12),
                     sec(-336, 158, 142, 0, -12), sec(-366, 168, 152, 0, -10)])
        b.add(f"Shin_Armour_{n}", sh, Sh, "armour", 6, zl, 3)
        b.add(f"Shin_Crank_{n}", P.loft([sec(-36, 124, 40, 0, 74), sec(8, 116, 34, 0, 84)]), Sh, "ti", 2.5, zl)
        for o in (1, -1):
            b.strut(f"Ankle_Act_{n}{'O' if o * s > 0 else 'I'}", Sh @ Vector((o * 40, 92, -170)),
                    Ft @ Vector((o * 40, 100, -12)), 34, 20, zl)

        b.add(f"Ankle_Joint_{n}", P.cyl(88, 150, 40), An @ R("Y", 90), "ti", 2, zf)
        hw = PR.FOOT_W / 2
        y0, y1 = PR.FOOT_L / 3, PR.FOOT_L / 3 - PR.FOOT_L          # heel, toe
        sole = P.round_poly([(-hw * 0.78, y0), (-hw * 0.97, -30), (-hw, -150), (-hw * 0.8, y1), (hw * 0.8, y1),
                             (hw, -150), (hw * 0.97, -30), (hw * 0.78, y0)], [34, 80, 80, 44, 44, 80, 80, 34], 5)
        b.add(f"Sole_{n}", P.prism(sole, -PR.Z_ANKLE, -PR.Z_ANKLE + 22), Ft, "rubber", 2, zf)
        b.add(f"Foot_Frame_{n}", P.prism([(x * 0.95, y * 0.96 - 2) for x, y in sole], -PR.Z_ANKLE + 22,
                                         -PR.Z_ANKLE + 42), Ft, "alu", 2, zf)
        w = PR.FOOT_W
        b.add(f"Foot_Upper_{n}", P.loft([sec(-53, w - 8, 214, 0, -22, 0.16), sec(-6, w - 22, 168, 0, -6, 0.2),
                                         sec(42, w - 44, 128, 0, -4, 0.24)]), Ft, "armour", 4, zf, 3)
        b.add(f"Foot_Toe_{n}", P.loft([sec(-53, w - 10, 96, 0, y1 + 50, 0.2), sec(-12, w - 34, 70, 0, y1 + 60, 0.26)]),
              Ft, "armour", 4, zf, 3)
        b.add(f"Foot_Heel_{n}", P.loft([sec(-53, w - 44, 42, 0, y0 - 22, 0.2), sec(-2, w - 58, 36, 0, y0 - 18, 0.24)]),
              Ft, "alu", 3, zf)


# ── pelvis, abdomen ──────────────────────────────────────────────────────────
def pelvis(b):
    z = "pelvis"
    hx = PR.HX
    b.add("Pelvis_Keel", P.loft([sec(858, 2 * hx - 150, 176), sec(990, 2 * hx - 144, 188)]), None, "alu", 4, z)
    b.add("Pelvis_Block", P.loft([sec(984, 2 * hx + 12, 204, 0, PR.TORSO_Y * 0.4),
                                  sec(1040, 2 * hx - 4, 190, 0, PR.TORSO_Y * 0.8)]), None, "alu", 4, z)
    groin = P.chamfer_poly([(-46, 0), (46, 0), (54, 96), (hx - 14, 132), (hx - 14, 176), (-hx + 14, 176),
                            (-hx + 14, 132), (-54, 96)], [8, 8, 6, 10, 12, 12, 10, 6])
    b.add("Groin_Plate", P.plate(groin, 12, crown=7, slices=8), T(0, -100, 862) @ R("X", 90), "armour", 3, z, 3)
    for s in (1, -1):
        n = side(s)
        b.add(f"Hip_Yaw_{n}", P.cyl(134, 62, 48), T(s * hx, 0, 1008), "alu", 2.5, z)
        b.add(f"Pelvis_Side_{n}", P.plate(P.chamfer_poly(P.rrect(168, 60), 14), 10),
              T(s * (hx + 7), 0, 1010) @ R("Y", s * 90) @ R("Z", 90), "armour", 3, z)
    b.add("Hip_Roll_Housing", P.loft([sec(880, 2 * hx - 90, 56, 0, 112), sec(960, 2 * hx - 44, 64, 0, 108),
                                      sec(1000, 2 * hx - 60, 50, 0, 104)]), None, "alu", 4, z)
    b.add("Waist_Slew", P.cyl(200, 26, 64), T(0, PR.TORSO_Y, PR.Z_WAIST - 7), "ti", 2.5, z)


def abdomen(b):
    z = "abdomen"
    b.add("Spine_Column", P.cyl(96, 150, 48), T(0, 26, 1140), "alu", 2.5, z)
    for s in (1, -1):
        b.strut(f"Waist_Pitch_Act_{side(s)}", (s * 76, 62, 1078), (s * 82, 66, 1222), 44, 28, z)
    for i in range(4):                                           # overlapping lames, open at the rear
        zc = 1084 + i * 37
        w, d = 244 + i * 20, 180 + i * 16
        lame = P.loft([sec(zc - 22, w - 10, d - 8, 0, -22, 0.24), sec(zc + 22, w, d, 0, -24, 0.24)])
        ob = b.add(f"Lame_{i + 1}", lame, None, "armour", 3, z, 2)
        C.boolean_cut(ob, C.cutter(P.box(w + 60, d, 80), b.O @ T(0, d / 2 + 34, zc)), lip=1.0)
        C.boolean_cut(ob, C.cutter(P.loft([sec(zc - 40, w - 34, d - 30, 0, -20, 0.24),
                                           sec(zc + 40, w - 22, d - 20, 0, -22, 0.24)]), b.O), lip=0.0)


# ── thorax, backpack ─────────────────────────────────────────────────────────
def thorax(b):
    z = "thorax"
    sx = PR.SX
    wc = 2 * sx - 164                                            # frame width between the shoulder joints
    core = P.loft([sec(1206, 258, 214, 0, -8), sec(1292, wc - 8, 300, 0, -18), sec(1400, wc, 316, 0, -18),
                   sec(1468, wc - 4, 300, 0, -22), sec(1492, wc - 50, 232, 0, -24)])
    b.add("Thorax_Core", core, None, "alu", 5, z, 3)
    yf = PR.CHEST_FRONT_Y + 15 + 9
    for s in (1, -1):
        n = side(s)
        px = sx - 30
        pec = [(10, 0), (px - 66, 0), (px, 66), (px, 206), (px - 38, 240), (10, 240)]
        pec = P.chamfer_poly([(x * s, y) for x, y in pec], 9)
        b.add(f"Pectoral_{n}", P.plate(pec, 15, crown=9, slices=10), T(0, yf + 1, 1262) @ R("X", 90), "armour", 4, z, 3)
        b.add(f"Flank_{n}", P.plate(P.chamfer_poly(P.rrect(196, 150), 22), 10),
              T(s * wc / 2, -20, 1330) @ R("Y", s * 90) @ R("Z", 90), "armour", 3, z)
        b.add(f"Shoulder_Yoke_{n}", P.loft([sec(1438, 92, 190, s * (sx - 128), -6), sec(1500, 70, 150, s * (sx - 134), -8)]),
              None, "alu", 4, z)
        b.add(f"Shoulder_Pitch_{n}", P.cyl(176, 62, 64), T(s * (sx - 108), 0, PR.Z_SHOULDER) @ R("Y", 90), "alu", 2.5, z)
        b.add(f"Lift_Eye_{n}", F.lifting_eye_bm(34), T(s * (sx - 132), 34, 1500), "ti", 0, z)
    stern = P.chamfer_poly([(-38, 0), (38, 0), (44, 40), (44, 264), (-44, 264), (-44, 40)], [10, 10, 4, 8, 8, 4])
    b.add("Sternum", P.plate(stern, 20, crown=4, slices=6), T(0, yf - 1, 1238) @ R("X", 90), "armour", 3.5, z, 3)
    collar = [(-108, 70), (-108, -62), (-70, -100), (70, -100), (108, -62), (108, 70), (86, 70), (86, -52),
              (60, -78), (-60, -78), (-86, -52), (-86, 70)]
    b.add("Collar_Guard", P.prism(collar, 1486, 1540), T(0, -12, 0), "armour", 3, z, 3)


def backpack(b):
    z = "backpack"
    y0, y1 = PR.THORAX_BACK_Y + 2, PR.PACK_BACK_Y
    yc, d = (y0 + y1) / 2, y1 - y0
    w = PR.PACK_HALF_W * 2
    shell = P.loft([sec(PR.PACK_Z0, w - 34, d - 22, 0, yc - 8, 0.14), sec(PR.PACK_Z0 + 90, w, d, 0, yc, 0.12),
                    sec(PR.PACK_Z1 - 40, w, d, 0, yc, 0.12), sec(PR.PACK_Z1, w - 30, d - 24, 0, yc - 8, 0.14)])
    b.add("Backpack_Shell", shell, None, "armour", 4, z, 3)
    for s in (1, -1):
        b.add(f"Blower_{side(s)}", P.cyl(116, 22, 48), T(s * 78, y1 - 5, 1390) @ R("X", 90), "alu", 2.5, z)
        b.add(f"Radiator_Grille_{side(s)}", P.plate(P.rrect(118, 130, 8), 6), T(s * 78, y1 - 1, 1245) @ R("X", -90),
              "alu", 2, z)
    b.add("Battery_Door", P.plate(P.rrect(150, 44, 6), 6), T(0, y1 - 1, 1172) @ R("X", -90), "armour", 2, z)


# ── neck, head, cap ──────────────────────────────────────────────────────────
def neck(b):
    z = "neck"
    b.add("Neck_Ring", P.cyl(128, 22, 48), T(0, 4, PR.Z_NECK - 3), "ti", 2, z)
    b.add("Neck_Gimbal", P.cyl(84, 34, 40), T(0, 6, 1524), "alu", 2, z)
    for s in (1, -1):
        b.strut(f"Neck_Act_{side(s)}", (s * 40, 52, 1494), (s * 44, 56, 1548), 24, 14, z)


def cap_base(a):
    """Point on the crown's base outline at angle a (cap local frame)."""
    c, s = math.cos(a), math.sin(a)
    return (PR.CAP_W / 2 * math.copysign(abs(c) ** (2 / 2.2), c),
            PR.CAP_L / 2 * math.copysign(abs(s) ** (2 / 2.2), s))


def head(b):
    rake = math.tan(math.radians(PR.FACE_RAKE))
    z0, z1 = 1538.0, 1650.0

    def front(zz):
        return -86.0 - (zz - z0) * rake

    secs = []
    for zz, w, back in ((z0, 148, 78), (1590, 168, 88), (z1, 182, 92)):
        d = back - front(zz)
        secs.append(sec(zz, w, d, 0, (back + front(zz)) / 2, 0.2))
    b.add("Skull", P.loft(secs), None, "armour", 3, "head", 3)

    # faceplate: flat, raked 12 deg top-forward, a little wider at the top
    zc = 1598.0
    fp = P.chamfer_poly([(-62, -50), (62, -50), (74, 48), (-74, 48)], [16, 16, 14, 14])
    Pm = T(0, front(zc) - 1, zc) @ R("X", 90 + PR.FACE_RAKE)
    face = b.add("Faceplate", P.plate(fp, 7), Pm, "armour", 1.5, "head", 3)
    Fm = Pm @ T(0, 0, 7)                         # on the outer face: X lateral, Y up the plate, +Z out
    dz = (PR.Z_SLIT - zc) / math.cos(math.radians(PR.FACE_RAKE))
    C.boolean_cut(face, C.cutter(P.prism(P.rrect(PR.SLIT_W + 4, PR.SLIT_H + 4, 3), -PR.SLIT_RECESS, 5),
                                 b.O @ Fm @ T(0, dz, 0)), lip=0.4)
    b.add("Slit_Emitter", P.prism(P.rrect(PR.SLIT_W, PR.SLIT_H, 2), -PR.SLIT_RECESS - 1, -PR.SLIT_RECESS + 1),
          Fm @ T(0, dz, 0), "emissive", 0, "head")
    b.add("Jaw_Guard", P.loft([sec(0, 78, 32, -4, 0, 0.22), sec(14, 62, 20, -4, -2, 0.26)]), Fm @ T(0, -31, 0),
          "armour", 2, "head")
    b.add("Lens_Bezel", P.prism(P.rrect(30, 60, 9), 0, 6), Fm @ T(53, -16, 0), "alu", 1.5, "head")
    for d, y in ((22, -4), (15, -24.5), (10, -38.5)):
        b.add(f"Lens_{d}", P.cyl(d, 5, 24), Fm @ T(53, y, 6.5), "glass", 0.6, "head")

    # cap: crown shell, six real seams, button, backwards brim
    tilt = math.degrees(math.atan2(PR.CAP_FRONT_Z - PR.CAP_REAR_Z, PR.CAP_L))
    base_z = (PR.CAP_FRONT_Z + PR.CAP_REAR_Z) / 2
    h = (PR.Z_CROWN - PR.CAP_BUTTON_H * 0.55 - base_z) / math.cos(math.radians(tilt))
    Cm = T(0, PR.CAP_Y, base_z) @ R("X", -tilt)
    shear = 14.0                                 # pole sits towards the brim side

    def crown_bm(inset=0.0):
        bm = P.dome(PR.CAP_W - 2 * inset, PR.CAP_L - 2 * inset, h - inset, 48, 12, 2.2, 2.5)
        for v in bm.verts:
            v.co.y += shear * (v.co.z / h) ** 1.4
        return bm

    crown = b.add("Cap_Crown", P.thicken(crown_bm(), PR.CAP_SHELL), Cm, "cap", 1.2, "cap", 3)
    b.add("Cap_Liner", P.thicken(crown_bm(PR.CAP_SHELL + 1.5), 2.0), Cm, "cavity", 0, "head")
    for k in range(3):                           # three cuts = six panel seams
        a = math.radians(30 + 60 * k)
        path = []
        for i in range(-20, 21):
            t = math.radians(i * 4.3)
            rr = math.sin(t)
            zz = (h + 3) * math.cos(t)
            p = Vector((math.cos(a) * (PR.CAP_W / 2 + 3) * rr, math.sin(a) * (PR.CAP_L / 2 + 3) * rr, zz))
            p.y += shear * (max(zz, 0) / h) ** 1.4
            path.append(b.O @ Cm @ p)
        F.panel_cut(crown, path, PR.SEAM_W, PR.SEAM_D)
    # snapback arch on the forehead, with its strap bar
    arch = [(33, 12)] + [(33 * math.cos(math.radians(a)), 22 + 26 * math.sin(math.radians(a)))
                         for a in range(0, 181, 15)] + [(-33, 12)]
    C.boolean_cut(crown, C.cutter(P.prism(arch, 40, 140), b.O @ Cm @ R("X", 90)), lip=0.5)
    b.add("Cap_Strap", P.box(80, 5, 9), Cm @ T(0, -PR.CAP_L / 2 + 1.5, 12.5), "cap", 1, "cap")
    b.add("Cap_Button", P.cyl(PR.CAP_BUTTON_D, PR.CAP_BUTTON_H, 32), Cm @ T(0, shear, h + PR.CAP_BUTTON_H * 0.2),
          "alu", 1.2, "cap")
    # brim: crescent from the crown's rear arc, stiff, gently curved, raked down
    a0 = math.acos((PR.BRIM_W / PR.CAP_W) ** 1.1)
    ys = cap_base(a0)[1]
    n = 2.8
    outer = [(PR.BRIM_W / 2 * math.copysign(abs(math.cos(u)) ** (2 / n), math.cos(u)),
              ys - 4 + (PR.CAP_L / 2 + PR.BRIM_L - ys + 4) * math.sin(u) ** (2 / n))
             for u in [math.pi * i / 28 for i in range(29)]]
    inner = [(x * 0.97, y - 3.0) for x, y in (cap_base(a0 + (math.pi - 2 * a0) * (1 - i / 16)) for i in range(1, 16))]
    brim = P.plate(outer + inner, PR.BRIM_T, crown=9, slices=12)
    Bm = Cm @ T(0, 96, 0) @ R("X", -(PR.BRIM_RAKE - tilt)) @ T(0, -96, -1)
    b.add("Cap_Brim", brim, Bm, "cap", 1.6, "cap", 3)


# ── arms and hands ───────────────────────────────────────────────────────────
def pauldron_outline(out, skirt, t, drop=0.0):
    """C-section of the shoulder armour in (x, z): top slab and outer wall around the roll actuator."""
    d = drop
    sx = PR.SX
    return [(sx - 58, 1506 - d), (sx - 38, 1494 - d * 0.6), (sx - 2, 1530 - d), (out - 70, 1530 - d),
            (out - t - 6, 1488 - d), (out - t, 1400), (out - t - 16, skirt), (out - 12, skirt), (out, 1400),
            (out - 6, 1506 - d), (out - 66, 1560 - d), (sx - 14, 1560 - d)]


def arms(b):
    for s in (1, -1):
        n = side(s)
        za, zh = f"arm_{n}", f"hand_{n}"
        Sv, Au, Af, Ah = FR.arm(s)

        b.add(f"Shoulder_Roll_{n}", P.cyl(150, 122, 64), T(*Sv) @ R("X", 90), "alu", 2.5, za)
        out = PR.PAULDRON_L_OUT if s > 0 else PR.PAULDRON_R_OUT
        skirt, t, drop = (1296, 24, 0) if s > 0 else (1326, 20, PR.PAULDRON_R_DROP)
        yf, yr = (-132, 118) if s > 0 else (-124, 20)            # right is cut back to clear the mount
        pl = ends([(x * s, zz) for x, zz in pauldron_outline(out, skirt, t, drop)], -yr, -yf, 20, 0.88)
        b.add(f"Pauldron_{n}", pl, R("X", 90), "armour", 5, f"pauldron_{n}", 3)
        sx = PR.SX
        chk = P.chamfer_poly([(x * s, zz) for x, zz in ((sx - 46, 1420), (out - 14, 1404), (out - 5, 1504 - drop),
                                                         (out - 64, 1552 - drop), (sx - 10, 1552 - drop),
                                                         (sx - 48, 1508 - drop))], 8)
        for tag, y0 in (("F", yf + 4), ("R", yr - 20)):
            if s < 0 and tag == "R":
                continue                                         # right rear stays open for the mount
            b.add(f"Pauldron_Cheek_{n}{tag}", P.prism(chk, -(y0 + 16), -y0), R("X", 90), "armour", 3,
                  f"pauldron_{n}", 3)

        b.add(f"Shoulder_Yaw_{n}", P.cyl(164, 88, 64), Au @ T(0, 0, -124), "alu", 2.5, za)
        b.add(f"Upper_Arm_Frame_{n}", P.loft([sec(-164, 124, 134), sec(-262, 114, 124)]), Au, "alu", 3, za)
        b.add(f"Upper_Arm_Shell_{n}", P.loft([sec(-100, 46, 186, s * 76, 0, 0.3), sec(-254, 40, 162, s * 70, 0, 0.3)]),
              Au, "armour", 4, za, 3)
        b.add(f"Elbow_{n}", P.cyl(138, 138, 64), Au @ T(0, 0, -PR.UPPER_ARM) @ R("Y", 90), "ti", 2.5, za)

        fa = P.loft([sec(-40, 150, 160), sec(-112, 192, 198, 0, 4), sec(-214, 176, 182, 0, 2), sec(-262, 134, 140)])
        b.add(f"Forearm_{n}", fa, Af, "armour", 6, za, 3)
        b.add(f"Forearm_Wear_Plate_{n}", P.loft([sec(-78, 12, 64, s * 99, 0, 0.3), sec(-226, 12, 56, s * 91, 0, 0.3)]),
              Af, "alu", 2, za)
        b.add(f"Wrist_{n}", P.cyl(92, 86, 40), Ah @ T(0, 0, 6) @ R("Y", 90), "ti", 2, zh)

        b.add(f"Palm_{n}", P.loft([sec(-14, 50, 98, 0, 0, 0.22), sec(-98, 46, 112, 0, 0, 0.2)]), Ah, "alu", 3, zh)
        b.add(f"Knuckle_Plate_{n}", P.loft([sec(-30, 10, 94, s * 28, 0, 0.25), sec(-100, 10, 106, s * 27, 0, 0.25)]),
              Ah, "armour", 2, zh)
        for i, y in enumerate((-38, 0, 38)):
            Fm = Ah @ T(0, y, -98)
            for j, (ln, th, curl) in enumerate(((44, 32, 28), (32, 29, 36), (25, 26, 30))):
                Fm = Fm @ R("Y", s * curl)
                b.add(f"Finger_{n}{i + 1}_{j + 1}", P.box(th, 32, ln), Fm @ T(0, 0, -ln / 2), "alu", 3, zh)
                Fm = Fm @ T(0, 0, -ln)
        Tm = Ah @ T(-s * 8, -52, -34) @ R("X", -42) @ R("Y", s * 30)
        for j, (ln, th) in enumerate(((42, 31), (32, 28))):
            b.add(f"Thumb_{n}_{j + 1}", P.box(th, 31, ln), Tm @ T(0, 0, -ln / 2), "alu", 3, zh)
            Tm = Tm @ T(0, 0, -ln) @ R("Y", s * 28)


# ── interceptor mount ────────────────────────────────────────────────────────
def mount(b, barrel_l):
    """Swing-arm mount. The trunnion sits low behind the right shoulder; the cannon
    rides BORE_RISE above it on a swing arm. Level, the barrel lies over the shoulder
    armour; swung up 90 deg it stands behind the shoulder, clear of the cap brim."""
    xb, yt, zt, rise = PR.BORE_X, PR.TRUNNION_Y, PR.TRUNNION_Z, PR.BORE_RISE
    Cn = T(xb, yt, zt + rise) @ R("X", 90)       # cannon frame on the bore: +Z forward, +Y up, +X inboard
    Sd = R("Z", -90) @ R("X", 90)                # side-plate frame: X forward, Y up, extrusion outboard
    fwd, aft = PR.BREECH_FWD, PR.BREECH_AFT
    hw = PR.BREECH_W / 2
    r = PR.BARREL_OD / 2
    e, t, f = "elev", "trav", "mount_fix"

    breech = ends(P.chamfer_poly(P.rrect(PR.BREECH_W, PR.BREECH_H), 26), -aft, fwd, 20, 0.88)
    b.add("Breech", breech, Cn, "alu", 4, "mount_elev", 3, e)
    z1 = fwd + barrel_l
    prof = [(0, fwd - 4), (r + 10, fwd - 4), (r + 10, fwd + 84), (r, fwd + 104), (r, z1 - 58), (r + 12, z1 - 54),
            (r + 12, z1 - 5), (r + 8, z1), (r - 17, z1), (r - 17, z1 - 80), (0, z1 - 80)]
    b.add("Barrel", P.revolve(prof, 64), Cn, "ti", 2, "mount_elev", 3, e)
    # soft-recoil cradle rides on top of the barrel: nothing inboard (head side), nothing
    # underneath (shoulder armour side)
    rod_l = min(300.0, barrel_l * 0.58)
    for k, w in enumerate((-34, 34)):
        b.add(f"Guide_Rod_{k + 1}", P.cyl(24, rod_l + 70), Cn @ T(w, 76, fwd + rod_l / 2 - 35), "steel", 1,
              "mount_elev", group=e)
    b.add("Recoil_Unit", P.cyl(50, 230), Cn @ T(0, 106, fwd + 25), "alu", 2, "mount_elev", group=e)
    saddle = P.chamfer_poly([(-58, -4), (56, -4), (56, 60), (48, 96), (24, 120), (-24, 120), (-48, 96), (-58, 60)], 8)
    b.add("Cradle_Saddle", P.prism(saddle, 0, 44), Cn @ T(0, 0, fwd + rod_l - 44), "alu", 3, "mount_elev", group=e)
    b.add("Feed_Box", P.prism(P.chamfer_poly(P.rrect(46, 90), 9), -15, 75), Cn @ T(hw + 23, 0, 0), "alu", 3,
          "mount_elev", group=e)
    # tracking head tucked beside the barrel root, outboard
    xo = -(r + 10 + 8 + 45)
    b.add("Tracker_Bracket", P.box(40, 30, 50), Cn @ T(-(r + 26), 6, fwd + 36), "alu", 3, "mount_elev", group=e)
    b.add("Tracker_Optic", P.cyl(90, 76, 48), Cn @ T(xo, 6, fwd + 54), "alu", 2.5, "mount_elev", group=e)
    b.add("Tracker_Lens", P.cyl(64, 4, 40), Cn @ T(xo, 6, fwd + 93), "glass", 1, "mount_elev", group=e)
    b.add("Tracker_Radar", P.box(74, 56, 12), Cn @ T(xo, 82, fwd + 80), "armour", 2, "mount_elev", group=e)

    # swing arm: outboard plate from the trunnion up to the breech flank
    arm = [(72 * math.cos(math.radians(a)), 72 * math.sin(math.radians(a))) for a in range(200, 341, 10)]
    arm += [(85, rise - 70), (85, rise + 55), (-105, rise + 55), (-105, rise - 70)]
    b.add("Swing_Arm", P.prism(arm, 0, 22), T(xb - hw - 5, yt, zt) @ Sd, "ti", 4, "mount_elev", 3, e)
    b.add("Elev_Sector", P.cyl(176, 10, 64), T(xb - hw - 16, yt, zt) @ R("Y", 90), "steel", 1, "mount_pin", group=e)
    b.add("Trunnion_Pin", P.cyl(64, 74, 40), T(xb - hw - 36, yt, zt) @ R("Y", 90), "steel", 1, "mount_pin", group=e)

    # traversing yoke: D-shaped base on the slewing ring (flat at the rear so the breech can
    # swing down past it) and one outboard cheek with the 170 mm pivot housing
    zb = zt - PR.YOKE_DROP
    rh, sw = 85.0, 50.0
    a0 = math.atan2(-math.sqrt(rh * rh - sw * sw), sw)
    key = [(sw, -PR.YOKE_DROP - 2.0)]
    key += [(rh * math.cos(a0 + (math.pi - 2 * a0) * i / 28), rh * math.sin(a0 + (math.pi - 2 * a0) * i / 28))
            for i in range(29)]
    key += [(-sw, -PR.YOKE_DROP - 2.0)]
    b.add("Yoke_Cheek", P.prism(key, 0, 28), T(xb - hw - 32, yt, zt) @ Sd, "alu", 4, "mount_trav", 3, t)
    b.add("Pivot_Housing", P.cyl(150, 20, 64), T(xb - hw - 69, yt, zt) @ R("Y", 90), "alu", 3, "mount_trav", 3, t)
    cut = math.degrees(math.asin(12.0 / 88.0))
    dee = [(88 * math.cos(math.radians(a)), 88 * math.sin(math.radians(a)))
           for a in [180 - cut + (180 + 2 * cut) * i / 40 for i in range(41)]]
    b.add("Yoke_Base", P.prism(dee, zb - 24, zb), T(xb, yt, 0), "alu", 3, "mount_trav", group=t)
    b.add("Yoke_Foot", P.box(hw + 60 - 80, 62, 24), T(xb - (hw + 60 + 80) / 2, yt - 19, zb - 12), "alu", 3,
          "mount_trav", group=t)
    # drive motor sits inboard of the swing arm, forward of and below the trunnion: the one
    # quadrant the cannon never sweeps. Its pinion meshes with the sector on the arm.
    b.add("Elev_Drive", P.cyl(62, 80, 40), T(xb - 43, yt - 50, zt - 85) @ R("Y", 90), "alu", 2, "mount_trav",
          group=t)
    b.add("Slew_Ring", P.cyl(PR.SLEW_OD, 30, 64), T(xb, yt, zb - 39), "ti", 2, f)
    hp = [(-PR.PACK_HALF_W + 8, -84), (xb - 70, -84), (xb - 92, -60), (xb - 92, 60), (xb - 70, 84),
          (-PR.PACK_HALF_W + 8, 84)]
    b.add("Hardpoint", P.prism(hp, zb - 84, zb - 54), T(0, yt, 0), "ti", 3, f)
    b.add("Hardpoint_Gusset", P.loft([sec(zb - 200, 26, 110, -PR.PACK_HALF_W - 6, yt + 14),
                                      sec(zb - 84, 150, 130, -PR.PACK_HALF_W - 62, yt + 14)]), None, "ti", 3, f)
    b.add("Travel_Lock", P.box(40, 60, 18), T(-PR.PACK_HALF_W + 16, PR.PACK_BACK_Y + PR.TORSO_Y - 26, PR.PACK_Z1 + 9),
          "ti", 2, "lock")


# ── build, measure, render ───────────────────────────────────────────────────
def build(barrel_l=None):
    C.reset_scene()
    M.reset()
    F.DECALS.clear()
    b = Blk()
    return build_into(b, barrel_l)


def build_into(b, barrel_l=None):
    """Add the blockout volumes to the current scene (used as stand-ins by model.build)."""
    legs(b)
    pelvis(b)
    b.O = T(0, PR.TORSO_Y, 0)           # everything above the waist sits forward of the hips
    abdomen(b)
    thorax(b)
    backpack(b)
    neck(b)
    head(b)
    arms(b)
    b.O = T()
    mount(b, barrel_l or PR.BARREL_L)   # mount uses absolute pivots from params
    return b


def measure():
    blk = [o for o in bpy.data.objects if o.name.startswith("BLK_")]
    out = {}
    for state in ("deployed", "stowed"):
        poses.set_mount(state)
        lo, hi = C.bounds_mm(blk)
        out[state] = dict(height=round(hi.z, 1), width=round(hi.x - lo.x, 1), depth=round(hi.y - lo.y, 1),
                          min=[round(v, 1) for v in lo], max=[round(v, 1) for v in hi])
    body = [o for o in blk if not o.get("zone", "").startswith("mount") and o.get("zone") != "lock"]
    lo, hi = C.bounds_mm(body)
    out["body"] = dict(height_to_crown=round(hi.z, 1), width=round(hi.x - lo.x, 1), depth=round(hi.y - lo.y, 1))
    lo, hi = C.bounds_mm([o for o in body if o["zone"].startswith("pauldron")])
    out["armour_span"] = round(hi.x - lo.x, 1)
    lo, hi = C.bounds_mm([o for o in body if o["zone"] in ("thorax", "backpack")])
    out["chest_front_to_pack_rear"] = round(hi.y - lo.y, 1)
    lo, hi = C.bounds_mm([o for o in body if o["zone"].startswith("foot")])
    out["foot_length"] = round(hi.y - lo.y, 1)
    return out


VIEWS = {"front": (0, -1), "left": (1, 0), "back": (0, 1), "right": (-1, 0)}
ZC, HGT = 1260.0, 2620.0


def _ortho(view):
    dx, dy = VIEWS[view]
    RD.camera((dx * 9000, dy * 9000, ZC), (0, 0, ZC), ortho=HGT)
    return Vector((dx, dy, 0))


def _clay_light(front):
    RD.studio((0, 0, 1000), 2200.0, power=0.42, front=front)
    RD.floor(0.0, base=0.35, rough=0.7)
    RD.world(0.55, (0.62, 0.64, 0.66))


def render_g1(tag="", samples=64):
    out = RD.REVIEW / "phase2"
    res = (860, 1560)
    sheets = {}
    sil_all = []
    for state in ("stowed", "deployed"):                         # clay turnaround + silhouettes
        poses.set_mount(state)
        clay = []
        for view in VIEWS:
            RD.setup(samples, *res)
            _clay_light(_ortho(view))
            clay.append(RD.render(out / f"clay_{state}_{view}{tag}.jpg", "clay", f"{view.upper()}  {state}"))
            RD.setup(16, *res)
            sil_all.append(RD.render(out / f"sil_{state}_{view}{tag}.png", "silhouette"))
        sheets[f"turn_{state}"] = RD.sheet(clay, out / f"G1_turnaround_{state}{tag}.jpg")
    sheets["sil"] = RD.sheet(sil_all, out / f"G1_silhouettes{tag}.png", cols=4, bg=1.0)

    # three-quarter perspectives: clay and first-pass black materials
    persp = {"q_front": ((-2900, -4300, 1450), (0, -40, 1050), 70), "q_rear": ((-3000, 4200, 1750), (0, 40, 1050), 70)}
    clay, final = [], []
    for state in ("deployed", "stowed"):
        poses.set_mount(state)
        for name, (loc, tgt, lens) in persp.items():
            RD.setup(samples, 1100, 1600)
            RD.camera(loc, tgt, lens)
            _clay_light(Vector((loc[0], loc[1], 0)).normalized())
            clay.append(RD.render(out / f"clay_{state}_{name}{tag}.jpg", "clay", f"{name}  {state}"))
            RD.setup(samples * 2, 1100, 1600)
            RD.studio((0, 0, 1000), 2200.0, power=1.0, front=(0, -1, 0) if "front" in name else (0, 1, 0))
            RD.floor(0.0)
            RD.world(0.02)
            final.append(RD.render(out / f"black_{state}_{name}{tag}.jpg", "final", f"{name}  {state}"))
    sheets["persp_clay"] = RD.sheet(clay, out / f"G1_three_quarter_clay{tag}.jpg", cols=4)
    sheets["persp_black"] = RD.sheet(final, out / f"G1_three_quarter_black{tag}.jpg", cols=4)

    # front view against the concept art, at matched figure height
    poses.set_mount("deployed")
    RD.setup(samples * 2, 1000, 1500)
    RD.camera((0, -9000, 900), (0, 0, 900), ortho=1950.0)
    RD.studio((0, 0, 1000), 2200.0, power=1.0, front=(0, -1, 0))
    RD.floor(0.0)
    RD.world(0.02)
    blk = RD.render(out / f"black_deployed_front{tag}.jpg", "final", "RJ-28 blockout, front, deployed")
    ref = RD.ROOT / "reference" / "01_concept_front.png"
    if ref.exists():
        sheets["ref"] = RD.sheet([ref, blk], out / f"G1_vs_reference{tag}.jpg", height=1500)
    return sheets


def render_quick(tag="", samples=32):
    """Four clay views for fast iteration."""
    out = RD.REVIEW / "phase2" / "wip"
    paths = []
    for state, view in (("deployed", "front"), ("deployed", "left"), ("stowed", "back"), ("stowed", "right")):
        poses.set_mount(state)
        RD.setup(samples, 760, 1380)
        _clay_light(_ortho(view))
        paths.append(RD.render(out / f"q_{state}_{view}{tag}.jpg", "clay", f"{view.upper()} {state}"))
    return RD.sheet(paths, out / f"quick{tag}.jpg")


def render_variant(tag, label):
    """Side and front silhouettes of one barrel-length variant, both states."""
    out = RD.REVIEW / "phase2" / "wip"
    paths = []
    for state, view in (("stowed", "right"), ("deployed", "right"), ("stowed", "front")):
        poses.set_mount(state)
        RD.setup(32, 620, 1130)
        _clay_light(_ortho(view))
        paths.append(RD.render(out / f"var_{tag}_{state}_{view}.jpg", "clay", f"{label}  {state} {view}"))
    return paths


def run(opts):
    out = RD.ROOT / "blender" / "out"
    arg = {o.split("=")[0]: o.split("=")[1] for o in opts if "=" in o}
    tag = arg.get("tag", "")
    if "variants" in opts:
        paths = []
        for L in (400, 455, 520):
            build(float(L))
            m = measure()
            print("VARIANT", L, json.dumps(dict(stowed_height=m["stowed"]["height"],
                                                muzzle_y=m["deployed"]["min"][1])))
            paths += render_variant(str(L), f"barrel {L} mm  overall {m['stowed']['height']:.0f} mm")
        RD.sheet(paths, RD.REVIEW / "phase2" / "wip" / "barrel_variants_post_g1.jpg", cols=3)
        return
    build(float(arg["barrel"]) if "barrel" in arg else None)
    m = measure()
    print("MEASURE", json.dumps(m))
    (out / f"blockout_measure{tag}.json").write_text(json.dumps(m, indent=2))
    if "nosweep" not in opts:
        res = poses.sweep_check(report=out / f"mount_sweep{tag}.json")
        print("SWEEP", "PASS" if res["passed"] else "FAIL", res["min_clearance_mm"])
        for zline in res["zones"][:12]:
            print("  ", zline)
    poses.set_mount("stowed")
    bpy.ops.wm.save_as_mainfile(filepath=str(out / f"blockout{tag}.blend"))
    if "quick" in opts:
        render_quick(tag)
    elif "norender" not in opts:
        render_g1(tag)
