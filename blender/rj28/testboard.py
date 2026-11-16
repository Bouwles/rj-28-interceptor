"""Phase 0 test board: one of every toolkit primitive on a labelled board,
rendered in clay and in final materials. Shading problems get fixed here once.
"""
import math

import bmesh
from mathutils import Vector

from . import markings, materials as M, render as RD
from .lib import core as C, fittings as F, harness as H, mech, prims as P
from .lib.core import T, R

CELL = 165.0
COLS, ROWS = 6, 4


def cell(c, r, z=0.0):
    return T(-CELL * (COLS - 1) / 2 + CELL * c, -CELL * (ROWS - 1) / 2 + CELL * r, z)


def cap(c, r, text, co):
    F.label(f"TB_Label_{c}{r}", text, 5.0, cell(c, r) @ T(0, -CELL / 2 + 9, 0), collection=co)


def build():
    C.reset_scene()
    M.reset()
    F.DECALS.clear()
    co = C.coll("TestBoard")
    arm, alu, ti, steel = M.get("armour"), M.get("alu"), M.get("ti"), M.get("steel")

    base = C.obj_from_bm("TB_Board", P.prism(P.rrect(CELL * COLS + 30, CELL * ROWS + 30, 12), -14.0, 0.0),
                         None, co, M.get("cfrp"), bevel=1.5)

    # ── row 0: plates and panel fittings ────────────────────────────────────
    outline = P.chamfer_poly(P.rrect(130, 110), [18, 6, 30, 6])
    C.obj_from_bm("TB_Plate_Flat", P.plate(outline, 10.0), cell(0, 0), co, arm, bevel=1.2, segments=3)
    cap(0, 0, "PLATE", co)

    pl = C.obj_from_bm("TB_Plate_Crowned", P.plate(P.round_poly(P.rrect(130, 110), 10), 10.0, crown=7.0,
                                                  crown2=2.0, slices=14),
                       cell(1, 0), co, arm, bevel=1.2, segments=3)
    o = cell(1, 0).translation
    F.panel_cut(pl, [o + Vector((x, 12 + 6 * math.sin(x / 30.0), 30)) for x in range(-70, 71, 5)],
                width=1.5, depth=2.0)
    seats = [C.frame(o + Vector((x, -32, 0)), (0, 0, 1)) for x in (-45, -15, 15, 45)]
    bvh = F._bvh(pl)
    for m in seats:                                       # sit each screw on the crowned surface
        hit = bvh.ray_cast((m.translation + Vector((0, 0, 50))) * C.MM, (0, 0, -1))
        m.translation = hit[0] / C.MM
        m.col[2].xyz = hit[1].normalized()
        m.col[0].xyz = Vector((0, 1, 0)).cross(m.col[2].xyz).normalized()
        m.col[1].xyz = m.col[2].xyz.cross(m.col[0].xyz)
    mech.fasteners("TB_Plate_Screws", seats, "M6", target=pl, collection=co)
    cap(1, 0, "CROWN + PANEL CUT", co)

    hp = C.obj_from_bm("TB_Hatch_Plate", P.plate(P.rrect(140, 116, 6), 10.0), cell(2, 0), co, arm, bevel=1.2)
    F.hatch("TB_Hatch", 96, 74, cell(2, 0, 10.0), target=hp, collection=co)
    cap(2, 0, "HATCH", co)

    vp = C.obj_from_bm("TB_Vent_Plate_A", P.plate(P.rrect(140, 116, 6), 10.0), cell(3, 0), co, arm, bevel=1.2)
    F.vent("TB_Vent_Slat", 96, 60, cell(3, 0, 10.0), "slats", target=vp, depth=9.0, collection=co)
    cap(3, 0, "VENT SLATS", co)

    vq = C.obj_from_bm("TB_Vent_Plate_B", P.plate(P.rrect(140, 116, 6), 10.0), cell(4, 0), co, arm, bevel=1.2)
    F.vent("TB_Vent_Mesh", 96, 60, cell(4, 0, 10.0), "mesh", target=vq, depth=9.0, collection=co)
    cap(4, 0, "VENT MESH", co)

    lp = C.obj_from_bm("TB_Label_Plate", P.plate(P.rrect(140, 116, 6), 10.0, crown=5.0), cell(5, 0), co, arm,
                       bevel=1.2)
    F.label("TB_Decal_A", "RJ-28", 22.0, cell(5, 0, 20) @ T(0, 26, 0), target=lp, collection=co)
    F.label("TB_Decal_B", "INTERCEPTOR", 7.0, cell(5, 0, 20) @ T(0, 2, 0), "cyan", target=lp, collection=co)
    F.label("TB_Decal_C", "NO STEP", 8.0, cell(5, 0, 20) @ T(-28, -22, 0), target=lp, collection=co)
    F.label("TB_Decal_D", "HV 96 V", 8.0, cell(5, 0, 20) @ T(32, -22, 0), target=lp, collection=co)
    cap(5, 0, "LABEL", co)

    # ── row 1: fasteners, bearings, gears ───────────────────────────────────
    blk = C.obj_from_bm("TB_Screw_Block", P.prism(P.rrect(130, 90, 4), 0.0, 16.0), cell(0, 1), co, alu, bevel=0.8)
    for i, (size, x) in enumerate((("M4", -45), ("M6", -15), ("M10", 22))):
        mech.fasteners(f"TB_Screw_{size}", [cell(0, 1, 16.0) @ T(x, 22, 0)], size, target=blk, collection=co)
        mech.fasteners(f"TB_Screw_{size}_Washer", [cell(0, 1, 16.0) @ T(x, -18, 0)], size, washer=True,
                       collection=co)
    mech.fasteners("TB_Screw_Csk", [cell(0, 1, 16.0) @ T(52, 22, 0)], "M6", "csk", target=blk, collection=co)
    mech.fasteners("TB_Screw_Quarter", [cell(0, 1, 16.0) @ T(52, -18, 0)], "M6", "quarter", collection=co)
    cap(0, 1, "FASTENERS", co)

    mech.bearing("TB_Bearing", 100, 55, 22, cell(1, 1, 11.0), co)
    cap(1, 1, "BEARING", co)

    mech.slewing_ring("TB_Slew", 150, 80, 24, 16, matrix=cell(2, 1), collection=co, geared=True)
    cap(2, 1, "SLEWING RING", co)

    mech.gear("TB_Gear", 3.0, 28, 16, 30, cell(3, 1, 8.0), co)
    cap(3, 1, "GEAR", co)

    mech.sector_gear("TB_Sector", 3.0, 60, 100, 16, 52, cell(4, 1, 8.0) @ T(-60, 0, 0), co)
    cap(4, 1, "SECTOR GEAR", co)

    F.lifting_eye("TB_Lift_Eye", cell(5, 1) @ T(-35, 15, 0), collection=co)
    F.hinge("TB_Hinge", 4.0, 80, 5, 18.0, cell(5, 1, 5.0) @ T(30, 5, 0), co)
    cap(5, 1, "LIFT EYE / HINGE", co)

    # ── row 2: actuators, harness ───────────────────────────────────────────
    mech.rotary_actuator("TB_Rotary", 140, 84, cell(0, 2), co)
    cap(0, 2, "ROTARY ACTUATOR", co)

    a = cell(1, 2).translation + Vector((-45, 0, 34))
    b = cell(2, 2).translation + Vector((55, 0, 34))
    mech.linear_actuator("TB_Linear", a, b, 44, 30, 80, pin_axis=(0, 0, 1), collection=co)
    cap(1, 2, "LINEAR ACTUATOR", co)
    cap(2, 2, "CLEVIS / BELLOWS", co)

    o = cell(3, 2).translation
    conn, exit_a = H.connector("TB_Conn_A", o + Vector((-55, 30, 16)), (1, 0, 0), 16.0, co)
    conn2, exit_b = H.connector("TB_Conn_B", o + Vector((300, 40, 16)), (-1, 0, 0), 16.0, co)
    C.obj_from_bm("TB_Conn_Block_A", P.box(18, 36, 32), T(*(o + Vector((-64, 30, 16)))), co, alu, bevel=0.8)
    C.obj_from_bm("TB_Conn_Block_B", P.box(18, 36, 32), T(*(o + Vector((309, 40, 16)))), co, alu, bevel=0.8)
    run = [exit_a, o + Vector((20, 30, 7.4)), o + Vector((110, 10, 7.4)), o + Vector((200, 44, 7.4)), exit_b]
    H.cable("TB_Cable", run, 6.0, sag=0.0, collection=co)
    H.p_clips("TB_Cable_Clips", run[1:4], 6.0, (0, 0, -1), spacing=95.0, collection=co)
    hrun = [o + Vector((-50, -30, 30)), o + Vector((40, -44, 9.4)), o + Vector((150, -20, 9.4)),
            o + Vector((250, -40, 9.4)), o + Vector((300, -30, 30))]
    H.hose("TB_Hose", hrun, 8.0, collection=co)
    H.p_clips("TB_Hose_Clips", hrun[1:4], 8.0, (0, 0, -1), spacing=100.0, collection=co)
    C.obj_from_bm("TB_Hose_Port_A", P.cyl(26, 30), T(*(o + Vector((-50, -30, 15)))), co, alu, bevel=0.8)
    C.obj_from_bm("TB_Hose_Port_B", P.cyl(26, 30), T(*(o + Vector((300, -30, 15)))), co, alu, bevel=0.8)
    cap(3, 2, "CONNECTOR", co)
    cap(4, 2, "CABLE / HOSE", co)
    cap(5, 2, "P-CLIP", co)

    # ── row 3: shells and booleans ──────────────────────────────────────────
    dm = P.thicken(P.dome(120, 132, 64, 48, 10), 4.0)
    dome = C.obj_from_bm("TB_Dome_Shell", dm, cell(0, 3), co, M.get("cap"), bevel=0.8)
    o = cell(0, 3).translation
    for k in range(3):
        ang = math.radians(60 * k)
        path = []
        for i in range(-18, 19):
            t = math.radians(i * 4.4)
            path.append(o + Vector((math.cos(ang) * 62 * math.sin(t), math.sin(ang) * 68 * math.sin(t),
                                    66 * math.cos(t) + 2)))
        F.panel_cut(dome, path, 1.5, 2.0)
    cap(0, 3, "SHELL + SEAMS", co)

    bb = C.obj_from_bm("TB_Bool_Block", P.prism(P.rrect(120, 100, 8), 0.0, 40.0), cell(1, 3), co, alu, bevel=1.0)
    C.boolean_cut(bb, C.cutter(P.cyl(46, 60), cell(1, 3, 40.0) @ T(-22, 0, 0)), lip=0.6)
    C.boolean_cut(bb, C.cutter(P.box(60, 26, 24), cell(1, 3, 40.0) @ T(40, 30, 0)), lip=0.6)
    C.boolean_join(bb, C.cutter(P.cyl(30, 24), cell(1, 3, 46.0) @ T(34, -22, 0)), lip=0.6)
    cap(1, 3, "BOOLEAN", co)

    sec = P.superellipse(1, 1, 3.0, 40)
    lf = P.loft([P.at_z(sec, 0, 110, 90), P.at_z(sec, 40, 126, 104), P.at_z(sec, 90, 96, 84, 0, -8),
                 P.at_z(sec, 120, 70, 66, 0, -10)])
    C.obj_from_bm("TB_Loft", lf, cell(2, 3), co, arm, bevel=1.5, segments=3)
    cap(2, 3, "LOFT", co)

    C.obj_from_bm("TB_Bellows", mech.bellows_bm(15, 24, 110), cell(3, 3) @ T(-40, 0, 26) @ R("Y", 90) @ T(0, 0, -15),
                  co, M.get("rubber"), bevel=0.0)
    C.obj_from_bm("TB_Torus", P.torus(70, 14), cell(3, 3) @ T(0, 45, 7), co, steel, bevel=0.0)
    C.obj_from_bm("TB_Tube", P.tube(60, 44, 30, 1.0), cell(3, 3) @ T(0, -35, 15), co, ti, bevel=0.0)
    cap(3, 3, "BELLOWS / RINGS", co)

    cl = C.obj_from_bm("TB_Clevis", mech.clevis_bm(26, 9, 28, 10, 38), cell(4, 3, 30.0) @ T(10, 0, 0), co, ti,
                       bevel=0.8)
    C.obj_from_bm("TB_Clevis_Pin", mech.pin_bm(18, 54), cell(4, 3, 30.0) @ T(10, 0, 0), co, steel, bevel=0.0)
    cap(4, 3, "CLEVIS + PIN", co)

    em = C.obj_from_bm("TB_Emitter", P.prism(P.rrect(110, 8, 2), 0.0, 3.0), cell(5, 3, 8.0), co, M.get("emissive"),
                       bevel=0.0)
    C.obj_from_bm("TB_Glass", P.prism(P.rrect(124, 22, 4), 0.0, 3.0), cell(5, 3, 12.0), co, M.get("glass"),
                  bevel=0.5)
    C.obj_from_bm("TB_Emitter_Housing", P.ring_solid(P.rrect(140, 38, 8), P.rrect(120, 18, 3), 0.0, 16.0),
                  cell(5, 3), co, arm, bevel=1.0)
    C.obj_from_bm("TB_Emitter_Back", P.prism(P.rrect(130, 30, 4), 0.0, 6.0), cell(5, 3), co, M.get("cavity"),
                  bevel=0.0)
    cap(5, 3, "GLASS + EMITTER", co)

    markings.build_atlas(RD.ROOT / "blender" / "out" / "testboard_decals.png", 2048)
    return co


def render_all(samples=96):
    out = RD.REVIEW / "phase0"
    RD.setup(samples, 1800, 1200)
    W, Hh = CELL * COLS, CELL * ROWS
    views = {"overview": ((0, -1500, 1450), (0, -20, 0), 50)}
    for c in range(3):
        for r in range(2):
            cx = -W / 2 + W * (c + 0.5) / 3
            cy = -Hh / 2 + Hh * (r + 0.5) / 2
            views[f"zone_{r}{c}"] = ((cx + 40, cy - 560, 520), (cx, cy, 12), 62)
    paths = {"clay": [], "final": []}
    for mode in ("clay", "final"):
        RD.studio((0, 0, 0), 1100.0, power=0.6 if mode == "final" else 0.4, front=(0, -1, 0))
        RD.floor(-14.0)
        RD.world(0.30 if mode == "clay" else 0.03)
        for name, (loc, tgt, lens) in views.items():
            RD.camera(loc, tgt, lens)
            paths[mode].append(RD.render(out / f"testboard_{mode}_{name}.jpg", mode,
                                         f"TEST BOARD  {mode.upper()}  {name}"))
    return paths
