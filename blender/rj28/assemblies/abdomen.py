"""Assembly 04: abdomen and spine. The one narrow part of the figure, and all mechanism.

From the pelvis up: waist slewing ring (yaw), turntable, spine column, pitch
pivot at the column head, two short roller-screw actuators that run up into
the thorax floor, the yaw drive standing on the turntable, a conduit and two
coolant hoses crossing the joint, four overlapping lames hung off the spine on
guide links, and a rubber bellows from the top lame up to a flange on the
thorax.

The lames are thin tapered bands, each lapping 14 mm over the outside of the
one below and tied to it by shoulder screws that ride in slots. Every lame
hangs from its own clamp ring on the spine by two ball-jointed links a side,
so the stack can follow the thorax as it pitches.

Body coordinates (before the torso offset). The yaw axis is x = y = 0.
"""
import math

import bmesh
from mathutils import Vector

from .. import frames as FR, params as PR
from ..lib import armour as A, core as C, detail as D, harness as H, mech, prims as P
from ..lib.core import T, R, frame
from ..parts import Asm, raw
from . import thorax as TH

RING_Z = 1054.0                 # underside of the waist slewing ring (the 1,060 landmark lies inside it)
RING_OD, RING_ID, RING_H = 200.0, 132.0, 24.0
DECK_Z = RING_Z + RING_H        # turntable underside
DECK_T = 12.0
SPINE_Y = 26.0                  # spine column stands behind the yaw axis
PIVOT_Z = 1174.0                # waist pitch axis (parallel to X, through the spine head)
HEAD_Z = 1136.0                 # top of the spine column, underside of the fork head
RING_H = 11.0
RING_ZS = (1107.5, 1118.5, 1129.5, HEAD_Z + 7.0)   # stacked clamp rings, one per lame
ACT_TOP_Z = 1272.0              # upper pivots of the pitch actuators, inside the thorax
ACT_BOT = (78.0, 64.0, 1124.0)  # lower pivots, on the turntable pads (+/-x)
MOTOR = (20.0, 113.2)           # yaw drive: 115 mm from the yaw axis, where its pinion meets the ring gear
CONDUIT_FOOT = (-40.0, 116.0)   # where the conduit and hoses leave the pelvis top plate
HOSE_FEET = ((-78.0, 112.0), (-100.0, 104.0))
HOSE_TOPS = ((-52.0, 128.0), (-76.0, 128.0))       # bulkhead unions on the bracket under the thorax
HOSE_R = 5.0
SHELF_Z = 1222.0                # underside of that bracket's shelf

# lames: thin tapered bands, widest at the top of the stack
LAME_T, LAME_H, LAME_LAP = 4.5, 45.5, 14.0
LAME_PITCH = LAME_H - LAME_LAP
LAME_Z0 = 1076.0                                    # bottom edge of the lowest lame
LAME_W0, LAME_W1, LAME_DW = 226.0, 304.0, 64.0      # outer width at the bottom and top of the stack; width minus depth
LAME_STEP = 2 * (LAME_T + 1.5)                      # each lame clears the one inside it by 1.5 mm
LAME_FLARE = (LAME_W1 - LAME_W0 - 3 * LAME_STEP) / (1 + 3 * LAME_PITCH / LAME_H)    # widening over one lame's height
LAME_Y, LAME_REAR = -22.0, 8.0
# section of a lame, (offset from its outer line, height above its bottom edge): rolled lip at the bottom
LAME_PROF = [(0.0, 6.5), (0.0, LAME_H), (-LAME_T, LAME_H), (-LAME_T, 1.5), (-LAME_T + 1.5, 0.0), (1.2, 0.0), (2.2, 1.2),
             (2.2, 4.5)]
BELLOWS_Z = (1238.5, 1246.0)    # seat of the bellows cuff on the thorax flange


def lame_dims(i, z):
    """(width, depth, corner radius) of the outer surface of lame i (0 = lowest) at height z."""
    zb = LAME_Z0 + i * LAME_PITCH
    w = LAME_W0 + i * (LAME_FLARE * LAME_PITCH / LAME_H + LAME_STEP) + LAME_FLARE * (z - zb) / LAME_H
    return w, w - LAME_DW, 52.0 + 4.0 * i


LAMES = [(LAME_Z0 + i * LAME_PITCH + LAME_H / 2,) + lame_dims(i, LAME_Z0 + i * LAME_PITCH + LAME_H / 2)[:2]
         for i in range(4)]     # (centre z, width, depth)


def _lame_ring(i, z, u=0.0):
    w, d, r = lame_dims(i, z)
    return A.rsec(z, w + 2 * u, d + 2 * u, 0, LAME_Y, r + u, 8)


def _radial(outline, c, n):
    """Resample a convex outline as n points on evenly spaced rays from c: (x, y, ray x, ray y)."""
    pts = [(p[0] - c[0], p[1] - c[1]) for p in outline]
    out = []
    for k in range(n):
        ang = 2 * math.pi * k / n
        dx, dy = math.cos(ang), math.sin(ang)
        best = 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            ex, ey = x1 - x0, y1 - y0
            den = dx * ey - dy * ex
            if abs(den) < 1e-9:
                continue
            t = (x0 * ey - y0 * ex) / den
            u = (x0 * dy - y0 * dx) / den
            if t > 0 and -1e-6 <= u <= 1 + 1e-6:
                best = max(best, t)
        out.append((c[0] + dx * best, c[1] + dy * best, dx, dy))
    return out


def _front_arc(z, grow, y_cut):
    """Tub outline at z from the right flank round the front to the left flank, stopping at y = y_cut."""
    p = TH.tub_at(z, grow)                           # starts at the front right corner, runs counter-clockwise
    return [(p[1][0], y_cut, z), p[1], p[0], p[7], p[6], (p[6][0], y_cut, z)]


def _tub_sweep(prof, y_cut):
    """Sweep a closed (grow, z) profile round the front of the thorax tub; capped at both ends."""
    arcs = [_front_arc(z, g, y_cut) for g, z in prof]
    return P.loft([[arc[k] for arc in arcs] for k in range(6)], cap=True)


def _bezier(p0, p1, k0, k1, n):
    """S-curve from p0 to p1 leaving and arriving vertically (handles k0, k1 mm long)."""
    p0, p1 = Vector(p0), Vector(p1)
    c0, c1 = p0 + Vector((0, 0, k0)), p1 - Vector((0, 0, k1))
    return [p0 * (1 - t) ** 3 + c0 * 3 * t * (1 - t) ** 2 + c1 * 3 * t * t * (1 - t) + p1 * t ** 3
            for t in (i / n for i in range(n + 1))]


def _tie_rod(p0, p1, axis):
    """Adjustable link between two pivots: a rod-end eye at each end (turning about `axis`),
    jam nuts, and a hex adjuster in the middle of the rod."""
    p0, p1 = Vector(p0), Vector(p1)
    d = (p1 - p0).normalized()
    length = (p1 - p0).length
    bm = bmesh.new()
    for p, away in ((p0, -d), (p1, d)):
        P.merge(bm, P.lug(5.2, 2.0, 9.0, 4.5, 20), frame(p, axis, away))
        P.merge(bm, P.cyl(8.6, 3.0, 6), frame(p - away * 10.5, d))
    P.merge(bm, P.cyl(6.0, length - 16.0, 12), frame((p0 + p1) / 2, d))
    P.merge(bm, P.cyl(9.6, 14.0, 6), frame((p0 + p1) / 2, d))
    return bm


def _back_y(z):
    return max(p[1] for p in TH.tub_at(z))


def build():
    a = Asm("04")
    W = FR.torso()

    # ── waist yaw: slewing ring, turntable, drive ───────────────────────────
    d = mech.slewing_ring("_ws", RING_OD, RING_ID, RING_H, bolts=16, matrix=W @ T(0, 0, RING_Z), geared=True)
    a.take_slew(d, "Waist", "waist yaw")
    bm = P.revolve([(34, 0), (82, 0), (82, DECK_T - 3), (79, DECK_T), (34, DECK_T)], 64)
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(236, 60), 10), 0, DECK_T), T(0, ACT_BOT[1], 0))
    P.merge(bm, P.cyl(84, DECK_T, 48), T(MOTOR[0], MOTOR[1], DECK_T / 2))
    deck = a.add("Waist_Turntable", bm,
                 "Turntable on the rotating race: carries the spine, the pitch actuators and the yaw drive.", "alu",
                 W @ T(0, 0, DECK_Z), bevel=0.8)
    C.boolean_cut(deck, C.cutter(P.cyl(17, 40, 16), W @ T(MOTOR[0], MOTOR[1], DECK_Z)), lip=0.3)
    zm = DECK_Z + DECK_T + 64.0
    d = mech.rotary_actuator("_wy", 60, 60, W @ T(MOTOR[0], MOTOR[1], zm) @ R("X", 180), bolts=6, connector_angle=0)
    a.take_rotary(d, "Waist_Yaw_Drive", "waist yaw drive")
    pin = mech.gear_bm(2.5, 14, 16, 8)
    P.merge(pin, P.cyl(12, 36, 16), T(0, 0, 14))
    a.add("Waist_Yaw_Pinion", pin, "Pinion on the yaw drive shaft, walking round the fixed ring gear.", "steel",
          W @ T(MOTOR[0], MOTOR[1], RING_Z + 11), bevel=0.25, seg=1)

    # ── spine column and the pitch pivot at its head ────────────────────────
    z0 = DECK_Z + DECK_T
    col = a.add("Spine_Column", P.revolve([(30, 0), (56, 0), (56, 8), (45.5, 8), (44, 12), (43, 12), (43, HEAD_Z - z0),
                                           (30, HEAD_Z - z0)], 48),
                "Hollow spine column carrying torso loads; the harness runs up its bore.", "alu",
                W @ T(0, SPINE_Y, z0), bevel=0.6)
    a.take(mech.fasteners("_sb", mech.ring((0, SPINE_Y, z0 + 8), (0, 0, 1), 50.6, 10), "M4", target=col, matrix=W),
           "Spine_Base_Screws", "Screws fixing the spine column to the turntable.")
    bm = P.cyl(86, 14, 48)
    bm.transform(T(0, SPINE_Y, HEAD_Z + 7))
    for o in (1, -1):
        P.merge(bm, P.lug(22, 10, 32, 12, 32), frame((o * 31, SPINE_Y, PIVOT_Z), (1, 0, 0), (0, 0, 1)))
    a.add("Spine_Head_Fork", bm, "Fork at the head of the spine; the thorax pitches about the pin through it.", "ti", W,
          bevel=0.8)
    a.add("Waist_Pitch_Pin", mech.pin_bm(20, 80), "Pivot pin of the waist pitch joint.", "steel",
          W @ T(0, SPINE_Y, PIVOT_Z) @ R("Y", 90), bevel=0)
    bm = P.lug(22, 10, 26, 48, 32)
    bm.transform(frame((0, SPINE_Y, PIVOT_Z), (1, 0, 0), (0, 0, -1)))
    # the foot runs forward of the fork cheeks so it clears them as the thorax pitches
    P.merge(bm, P.prism(P.rrect(48, 46, 4, 3), TH.FLOOR_Z - 8, TH.FLOOR_Z), T(0, SPINE_Y, 0))
    P.merge(bm, P.prism(P.chamfer_poly(P.rrect(96, 20), 5), TH.FLOOR_Z - 8, TH.FLOOR_Z), T(0, -6, 0))
    tang = a.add("Thorax_Pitch_Tang", bm, "Tang bolted under the thorax floor, riding on the waist pitch pin.", "alu", W,
                 bevel=0.8)
    seats = [W @ T(x, -6, TH.FLOOR_Z - 8) @ R("X", 180) for x in (-37, -13, 13, 37)]
    a.take(mech.fasteners("_tt", seats, "M6", target=tang), "Thorax_Tang_Screws",
           "Screws fixing the pitch tang to the thorax floor.")
    a.add("Waist_Pitch_Encoder", D.encoder_bm(38), "Absolute encoder reading waist pitch at the pin end.",
          ["alu", "fastener"], W @ T(-40.5, SPINE_Y, PIVOT_Z) @ R("Y", -90) @ R("Z", 90), bevel=0.3)

    # ── waist pitch actuators: rod ends on the turntable, bodies up inside the thorax ──
    for s, tag in ((1, "L"), (-1, "R")):
        p0 = W @ Vector((s * TH.WELL[0], TH.WELL[1], ACT_TOP_Z))
        p1 = W @ Vector((s * ACT_BOT[0], ACT_BOT[1], ACT_BOT[2]))
        d = mech.linear_actuator("_wp", p0, p1, 38, 22, 30, pin_axis=(1, 0, 0), body_len=58,
                                 base_dir0=(0, 0, 1), base_dir1=(0, 0, -1))
        a.take_actuator(d, f"Waist_Pitch_{tag}", "waist pitch")

    # ── conduit across the joint: one smooth S between two threaded glands ──
    # the long lower handle keeps the conduit out by the pelvis rim until it is above the clamp rings
    ends = (CONDUIT_FOOT[0], CONDUIT_FOOT[1], RING_Z + 0.5), (TH.CONDUIT[0], TH.CONDUIT[1], TH.FLOOR_Z + 8)
    path = _bezier(*ends, 100.0, 40.0, 40)
    waves = round(sum((q - p).length for p, q in zip(path, path[1:])) / 6.5)
    path = [W @ p for p in _bezier(*ends, 100.0, 40.0, waves * 6)]

    def corrugated(t):                               # plain cuffs inside the glands, convolutions between
        return 15.0 if t < 0.1 or t > 0.84 else 14.4 + 1.6 * math.sin(t * waves * 2 * math.pi)

    a.add("Waist_Conduit", P.sweep(path, corrugated, 20),
          "Corrugated conduit carrying power and data across the waist joint.", "rubber", None, bevel=0)
    gland = [(15.1, 0), (21, 0), (21, 5), (19.5, 6), (19.5, 8.5), (21, 9.5), (21, 13), (19.5, 14.5), (15.1, 14.5)]
    bm = P.revolve(gland, 32)
    bm.transform(T(CONDUIT_FOOT[0], CONDUIT_FOOT[1], RING_Z))
    upper = P.revolve([(15.1, -18), (19, -18), (19.6, -17), (19.6, -7), (22, -6), (22, 0), (15.1, 0)], 32)
    P.merge(bm, upper, T(TH.CONDUIT[0], TH.CONDUIT[1], TH.FLOOR_Z))
    a.add("Waist_Conduit_Glands", bm,
          "Threaded glands gripping the conduit: one in the pelvis top plate, one under the thorax floor.", "alu", W,
          bevel=0)

    # ── coolant hoses: unions in the pelvis top plate up to a bulkhead bracket on the thorax ──
    nut = HOSE_R * 1.3                               # height of the swivel nut on a hose ferrule
    union = bmesh.new()
    for fx, fy in HOSE_FEET:
        P.merge(union, P.revolve([(0, 0), (9.5, 0), (9.5, 1.6), (8.5, 2.4), (0, 2.4)], 20), T(fx, fy, RING_Z))
        P.merge(union, P.cyl(15, 5.6, 6), T(fx, fy, RING_Z + 5.2))
    a.add("Waist_Coolant_Unions_Lower", union, "Threaded unions in the pelvis top plate that the waist coolant hoses screw onto.",
          "steel", W, bevel=0.3, seg=1)
    wall = lambda z: _back_y(z)                      # the tub's sloping back wall
    x0, x1 = HOSE_TOPS[1][0] - 12, HOSE_TOPS[0][0] + 12
    prof = [(wall(SHELF_Z - 14) - 1, SHELF_Z - 14), (wall(SHELF_Z - 14) + 6.6, SHELF_Z - 14),
            (wall(SHELF_Z) + 6.6, SHELF_Z), (HOSE_TOPS[0][1] + 10, SHELF_Z), (HOSE_TOPS[0][1] + 10, SHELF_Z + 6),
            (wall(SHELF_Z + 6) - 1, SHELF_Z + 6)]
    bm = P.prism(prof, x0, x1)
    gus = P.prism([(wall(SHELF_Z - 13) + 6, SHELF_Z - 13), (HOSE_TOPS[0][1] - 11, SHELF_Z + 1), (wall(SHELF_Z) + 6, SHELF_Z + 1)],
                  (x0 + x1) / 2 - 2.5, (x0 + x1) / 2 + 2.5)
    P.merge(bm, gus)
    bm.transform(TH.YZ)
    brk = a.add("Waist_Coolant_Bracket", bm,
                "Bulkhead bracket on the back of the thorax tub where the waist coolant hoses hand over to the chest loop.",
                "alu", W, bevel=0.5)
    n_wall = Vector((0.0, 86.0, -41.0)).normalized()
    seats = [W @ frame((x, wall(SHELF_Z - 7) + 6.6, SHELF_Z - 7), n_wall, (1, 0, 0)) for x in (x0 + 7, x1 - 7)]
    a.take(mech.fasteners("_cb", seats, "M4", washer=True), "Waist_Coolant_Bracket_Screws",
           "Screws fixing the coolant bulkhead bracket to the thorax tub.")
    union = bmesh.new()
    ball = [(5.6 * math.cos(math.radians(t)), 5.6 * math.sin(math.radians(t))) for t in range(-90, 91, 15)]
    for tx, ty in HOSE_TOPS:
        ze = SHELF_Z + 19.0                                                # elbow above the shelf
        reach = (ty - wall(ze)) * n_wall.y                                 # from the elbow square on to the wall
        P.merge(union, P.cyl(15, 6, 6), T(tx, ty, SHELF_Z - 3))
        P.merge(union, P.cyl(15, 4.5, 6), T(tx, ty, SHELF_Z + 8.25))
        P.merge(union, P.cyl(9, ze - SHELF_Z, 16), T(tx, ty, (ze + SHELF_Z) / 2))
        P.merge(union, P.revolve(ball, 16), T(tx, ty, ze))
        P.merge(union, P.cyl(9, reach, 16), frame(Vector((tx, ty, ze)) - n_wall * (reach / 2), n_wall))
        P.merge(union, P.revolve([(0, 0), (10, 0), (10, 2.4), (8.5, 3.4), (0, 3.4)], 20),
                frame(Vector((tx, ty, ze)) - n_wall * reach, n_wall))
    a.add("Waist_Coolant_Unions_Upper", union,
          "Bulkhead unions through the bracket, elbowed into flanged ports on the thorax tub.", "steel", W,
          bevel=0.3, seg=1)
    for k, ((fx, fy), (tx, ty)) in enumerate(zip(HOSE_FEET, HOSE_TOPS)):
        pa = Vector((fx, fy, RING_Z + 8.0 + nut))
        pb = Vector((tx, ty, SHELF_Z - 6.0 - nut))
        run = [W @ p for p in _bezier(pa, pb, 52.0, 52.0, 36)]
        nm = ("Supply", "Return")[k]
        a.add(f"Waist_Coolant_Hose_{nm}", P.sweep(run, HOSE_R, 14),
              f"Coolant {nm.lower()} hose from the chest loop down to the hip and leg actuators.", "rubber", None, bevel=0)
        fb = bmesh.new()
        P.merge(fb, H.ferrule_bm(HOSE_R), frame(run[0], run[0] - run[1]))
        P.merge(fb, H.ferrule_bm(HOSE_R), frame(run[-1], run[-1] - run[-2]))
        a.add(f"Waist_Coolant_Ferrules_{nm}", fb, f"Crimped end fittings of the coolant {nm.lower()} hose.", "steel", None,
              bevel=0)

    # ── lames: four tapered bands, each lapping over the one below, open at the rear ──
    lames = []
    for i in range(4):
        zb = LAME_Z0 + i * LAME_PITCH
        lame = raw(P.loft([_lame_ring(i, zb + dz, u) for u, dz in LAME_PROF], cap=False, wrap=True), W, "armour", 0.8, 2)
        w = lame_dims(i, zb + LAME_H)[0]
        C.boolean_cut(lame, C.cutter(P.box(w + 80, 300, LAME_H + 30), W @ T(0, LAME_REAR + 150, zb + LAME_H / 2)),
                      lip=0.6)
        lames.append(lame)

        if i:                                        # shoulder screws in the lame below ride in slots in this one
            zs = zb + 9.0
            pts = [W @ Vector((o * 0.27 * w, -300, zs)) for o in (1, -1)]
            seats = D.seats_on(lame, pts, (0, -1, 0))
            for o in (1, -1):
                seats += D.seats_on(lame, [W @ Vector((o * 300, -22, zs))], (o, 0, 0))
            slots = bmesh.new()
            for m in seats:
                P.merge(slots, P.prism(P.rrect(5.0, 14.0, 2.49, 4), -(LAME_T + 0.9), 5.0), m)
            C.boolean_cut(lame, C.cutter(slots), lip=0.4)
            slide = mech.fasteners("_sl", seats, "M4", washer=True)
        a.take(lame, f"Lame_{i + 1}",
               f"Abdominal lame {i + 1} of 4: a tapered armour band that slides over its neighbour as the waist moves.")
        if i:
            a.take(slide, f"Lame_{i + 1}_Slide_Screws",
                   f"Shoulder screws in lame {i}, riding in the slots of lame {i + 1} so the two can slide.")

        # clamp ring on the spine, and two ball-jointed links a side out to brackets inside the lame
        zr, zl = RING_ZS[i], zb + 29.0
        a_in = lame_dims(i, zl)[0] / 2 - LAME_T
        car = P.tube(112, 87, RING_H, 1.0)
        car.transform(T(0, SPINE_Y, zr))
        P.merge(car, P.box(13, 9, RING_H - 1), T(0, SPINE_Y, zr) @ R("Z", 135) @ T(60, 0, 0))     # pinch lug
        P.merge(car, mech.screw_bm("M4", "shcs"), T(0, SPINE_Y, zr) @ R("Z", 135) @ T(61, 4.5, 0) @ R("X", -90),
                mat_index=1)
        links, brk, pts = bmesh.new(), bmesh.new(), []
        for o in (1, -1):
            for (ux, uy), yv in (((0.90, -0.436), -38.0), ((0.995, -0.10), -6.0)):
                q0 = Vector((o * 62 * ux, SPINE_Y + 62 * uy, zr))
                q1 = Vector((o * (a_in - 11), yv, zl))
                dq = q1 - q0
                ax = Vector((-dq.y, dq.x, 0.0)).normalized()
                P.merge(links, _tie_rod(q0, q1, ax))
                P.merge(car, P.lug(5.2, 2.0, 8.0, 4.5, 20), frame(q0 + ax * 4.75, ax, (o * ux, uy, 0)))
                P.merge(car, P.cyl(4.0, 12.5, 12), frame(q0 + ax * 2.4, ax), mat_index=1)
                P.merge(brk, P.lug(5.2, 2.0, 11.5, 4.5, 20), frame(q1 + ax * 4.75, ax, (-o, 0, 0)))
                P.merge(brk, P.box(4, 26, 16), T(o * (a_in - 1.2), yv, zl))
                P.merge(brk, P.cyl(4.0, 12.5, 12), frame(q1 + ax * 2.4, ax), mat_index=1)
                pts += [(o, yv - 8), (o, yv + 8)]
        a.add(f"Lame_{i + 1}_Carrier", car, f"Clamp ring on the spine with the lugs that lame {i + 1} hangs from.",
              ["ti", "steel"], W, bevel=0.5, seg=1)
        a.add(f"Lame_{i + 1}_Guide_Links", links,
              f"Ball-jointed guide links hanging lame {i + 1} from its clamp ring, two a side.", "ti", W, bevel=0.4,
              seg=1)
        a.add(f"Lame_{i + 1}_Brackets", brk, f"Link brackets screwed to the inside of lame {i + 1}.", ["ti", "steel"], W,
              bevel=0.4, seg=1)
        seats = []
        for o, y in pts:
            seats += D.seats_on(lame, [W @ Vector((o * 300, y, zl))], (o, 0, 0))
        a.take(mech.fasteners("_lb", seats, "M4", washer=True), f"Lame_{i + 1}_Bracket_Screws",
               f"Screws fixing the link brackets to lame {i + 1}.")

    # ── bellows: from inside the top lame up to a flange on the thorax tub ──
    zt = LAME_Z0 + 3 * LAME_PITCH + LAME_H                    # top edge of the top lame
    zc0, zc1 = zt - 11.0, zt - 2.0                            # lower cuff, inside the lame
    zf0, zf1 = BELLOWS_Z
    flange = [(-0.5, zf0 - 2.5), (4.2, zf0 - 2.5), (4.2, zf0 - 1.0), (3.0, zf0), (3.0, zf1), (7.5, zf1), (7.5, zf1 + 10),
              (-0.5, zf1 + 10)]
    fl = a.add("Waist_Bellows_Flange", _tub_sweep(flange, LAME_REAR + 6),
               "Flange rail screwed round the front of the thorax tub; the bellows cuff clamps onto it.", "alu", W,
               bevel=0.5)
    zs = zf1 + 5.0
    seats = D.seats_on(fl, [W @ Vector((x, -300, zs)) for x in (-90, -45, 0, 45, 90)], (0, -1, 0))
    for o in (1, -1):
        seats += D.seats_on(fl, [W @ Vector((o * 300, y, zs)) for y in (-64, -22)], (o, 0, 0))
    a.take(mech.fasteners("_bf", seats, "M4", target=fl), "Waist_Bellows_Flange_Screws",
           "Screws fixing the bellows flange to the thorax tub.")

    n, c = 120, (0.0, -12.0)
    lo = lambda z: _radial([p[:2] for p in _lame_ring(3, min(z, zc1), -LAME_T)], c, n)
    hi = lambda z: _radial([p[:2] for p in TH.tub_at(max(z, zf0), 5.0)], c, n)
    span = zf0 - zc1
    spec = [(zc0, 0.0, 0.0), (zc1, 0.0, 0.0)]
    spec += [(zc1 + span * f, f, u) for f, u in ((0.10, 1.2), (0.25, 6.0), (0.40, 0.0), (0.55, 6.0), (0.70, 0.0),
                                                 (0.85, 5.0), (0.95, 0.8))]
    spec += [(zf0, 1.0, 0.0), (zf1, 1.0, 0.0)]
    rings = []
    for z, f, u in spec:
        rings.append([(xa * (1 - f) + xb * f + dx * u, ya * (1 - f) + yb * f + dy * u, z)
                      for (xa, ya, dx, dy), (xb, yb, _, _) in zip(lo(z), hi(z))])
    bel = raw(P.thicken(P.loft(rings, cap=False), 2.0), W, "rubber", 0)
    C.boolean_cut(bel, C.cutter(P.box(500, 300, 120), W @ T(0, LAME_REAR + 150, (zc0 + zf1) / 2)))
    a.take(bel, "Waist_Bellows", "Rubber bellows sealing the gap between the top lame and the chest while the waist pitches.")
    band = _tub_sweep([(5.0, zf0 + 1.0), (6.2, zf0 + 1.0), (6.2, zf1 - 1.0), (5.0, zf1 - 1.0)], LAME_REAR + 3)
    zb_ = (zf0 + zf1) / 2
    xs = TH.tub_at(zb_, 6.2)[1][0]                                         # worm-drive housing, on the left flank
    P.merge(band, P.box(9, 14, 8), T(xs + 3.5, -40, zb_))
    P.merge(band, P.cyl(5, 20, 6), T(xs + 4.5, -40, zb_) @ R("X", 90))
    a.add("Waist_Bellows_Clamp", band, "Worm-drive band clamping the bellows cuff onto its flange.", "steel", W,
          bevel=0.3, seg=1)
    ret = raw(P.loft([_lame_ring(3, z, u) for u, z in ((-LAME_T - 2.0, zc0 + 1), (-LAME_T - 2.0, zc1 - 1),
                                                         (-LAME_T - 3.5, zc1 - 1), (-LAME_T - 3.5, zc0 + 1))],
                     cap=False, wrap=True), W, "steel", 0.3, 1)
    C.boolean_cut(ret, C.cutter(P.box(500, 300, 60), W @ T(0, LAME_REAR + 3 + 150, zc0)))
    a.take(ret, "Waist_Bellows_Retainer", "Retaining band pinching the bellows' lower cuff against the inside of the top lame.")
    zs = (zc0 + zc1) / 2
    seats = D.seats_on(lames[3], [W @ Vector((x, -300, zs)) for x in (-80, -28, 28, 80)], (0, -1, 0))
    for o in (1, -1):
        seats += D.seats_on(lames[3], [W @ Vector((o * 300, -22, zs))], (o, 0, 0))
    a.take(mech.fasteners("_br", seats, "M4", washer=True), "Waist_Bellows_Retainer_Screws",
           "Screws through the top lame into the bellows retaining band.")
    return a


def review(a, out, tag=""):
    from .. import review as RV
    objs = [o for o in a.parts if o.type == "MESH"]
    RV.closeup(objs, out / f"04_abdomen_front_clay{tag}.jpg", "04 abdomen, front three-quarter", (-0.6, -0.78, 0.12), "clay",
               res=(1300, 1100), isolate=True, dist=3.0)
    RV.closeup(objs, out / f"04_abdomen_rear_clay{tag}.jpg", "04 abdomen, rear three-quarter", (0.6, 0.78, 0.22), "clay",
               res=(1300, 1100), isolate=True, dist=3.0)
    RV.closeup(objs, out / f"04_abdomen_rear_final{tag}.jpg", "04 abdomen, rear three-quarter", (-0.55, 0.8, 0.2),
               "final", res=(1300, 1100), isolate=True, dist=3.0)
