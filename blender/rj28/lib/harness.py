"""Cables, hoses, clips, connectors. Dimensions mm.

Runs are swept meshes (not curve objects) so the result is deterministic and
carries length-true UVs for the braid texture.
"""
import math

import bmesh
from mathutils import Vector

from .. import materials as M
from . import prims as P
from .core import T, R, frame, obj_from_bm


def connector_bm(d=14.0):
    """Circular connector along Z: flange receptacle at z=0, plug, knurled
    coupling ring, backshell. Slot 0 metal, slot 1 rubber boot. Cable exits at
    z = connector_len(d)."""
    r = d / 2
    bm = P.prism(P.rrect(d * 1.5, d * 1.5, d * 0.22, 3), 0.0, 2.0)
    prof = [(0, 2.0), (r, 2.0), (r, d * 0.45), (r * 1.22, d * 0.47)]
    z0, z1 = d * 0.47, d * 1.05
    n = 5
    for i in range(n):                                   # knurl grooves on the coupling ring
        z = z0 + (z1 - z0) * i / n
        p = (z1 - z0) / n
        prof += [(r * 1.22, z + p * 0.7), (r * 1.14, z + p * 0.75), (r * 1.14, z + p * 0.95),
                 (r * 1.22, z + p)]
    prof += [(r * 1.0, z1 + 0.6), (r * 1.0, d * 1.45), (r * 0.72, d * 1.7), (0, d * 1.7)]
    P.merge(bm, P.revolve(prof, P.auto_segs(d * 1.3)))
    boot = [(0, d * 1.7), (r * 0.74, d * 1.7), (r * 0.74, d * 1.8), (r * 0.62, d * 1.85),
            (r * 0.62, d * 2.25), (r * 0.5, d * 2.3), (0, d * 2.3)]
    P.merge(bm, P.revolve(boot, P.auto_segs(d)), mat_index=1)
    return bm


def connector_len(d=14.0):
    return d * 2.3


def connector(name, point, direction, d=14.0, collection=None):
    """Connector with its flange at `point`, pointing along `direction`.
    Returns (object, cable exit point)."""
    F = frame(point, direction)
    ob = obj_from_bm(name, connector_bm(d), F, collection,
                     [M.get("fastener"), M.get("rubber")], bevel=0.0)
    return ob, Vector(point) + Vector(direction).normalized() * (connector_len(d) - 1.0)


def cable(name, points, radius=4.0, sag=0.0, sleeve=True, collection=None, sides=10):
    """Braided cable through `points` (mm). sag in mm per span (scalar or list)."""
    path = P.catmull(points, step=max(4.0, radius * 1.4), sag=sag)
    bm = P.sweep(path, radius, sides)
    return obj_from_bm(name, bm, None, collection, M.get("braid" if sleeve else "rubber"),
                       bevel=0.0)


def loom_radius(strands, radius):
    """Outer radius of a bundle of `strands` round cables of `radius`."""
    return radius * 2 if strands == 2 else radius * (1 + 1 / math.sin(math.pi / strands))


def loom(name, points, strands=4, radius=2.1, sag=0.0, tie_every=55.0, lay=500.0, collection=None):
    """Bundle of braided cables laid side by side with a slow twist (one turn per `lay` mm) and
    bound by cable ties every `tie_every` mm. Slot 0 braid, slot 1 ties."""
    path = P.catmull(points, step=4.0, sag=sag)
    n = len(path)
    tang = [(path[min(i + 1, n - 1)] - path[max(i - 1, 0)]).normalized() for i in range(n)]
    nrm, d, fr = tang[0].orthogonal().normalized(), 0.0, []
    for i in range(n):                                   # rotation-minimising frame, as in P.sweep
        if i:
            d += (path[i] - path[i - 1]).length
            nrm = (nrm - tang[i] * nrm.dot(tang[i])).normalized()
        fr.append((nrm.copy(), tang[i].cross(nrm), d))
    rho = loom_radius(strands, radius) - radius
    bm = bmesh.new()
    for k in range(strands):
        ph = 2 * math.pi * k / strands
        P.merge(bm, P.sweep([p + (a * math.cos(ph + 2 * math.pi * s / lay) + b * math.sin(ph + 2 * math.pi * s / lay)) * rho
                             for p, (a, b, s) in zip(path, fr)], radius, 8))
    ro = rho + radius
    ties = max(1, round(d / tie_every))
    for j in range(ties):
        s = (j + 0.5) / ties * d
        i = min(range(n), key=lambda q: abs(fr[q][2] - s))
        F = frame(path[i], tang[i], fr[i][0])
        band = P.revolve(P.ring_profile(ro - 0.5, ro + 0.5, -1.8, 1.8, 0.2), 16)
        P.merge(band, P.box(4.6, 3.0, 5.0), T(0, ro + 1.2, 0))       # the tie's ratchet head
        P.merge(bm, band, F, mat_index=1)
    ob = obj_from_bm(name, bm, None, collection, [M.get("braid"), M.get("rubber")], bevel=0.0)
    ob["rj28_count"] = strands
    return ob


def ferrule_bm(radius):
    """Crimped hose ferrule + swivel nut along Z, hose enters at z=0 going -Z."""
    r = radius
    prof = [(0, -r * 4.2), (r + 1.8, -r * 4.2)]
    for i in range(3):                                   # crimp rings
        z = -r * 4.0 + i * r * 1.1
        prof += [(r + 1.8, z + r * 0.25), (r + 1.0, z + r * 0.4), (r + 1.0, z + r * 0.7),
                 (r + 1.8, z + r * 0.85)]
    prof += [(r + 1.8, -r * 0.6), (r + 0.4, -r * 0.4), (r + 0.4, 0), (0, 0)]
    bm = P.revolve(prof, P.auto_segs(r * 3))
    nut = P.cyl((r + 3.4) * 2, r * 1.3, 6)
    P.merge(bm, nut, T(0, 0, r * 0.65))
    return bm


def hose(name, points, radius=6.5, sag=0.0, collection=None, sides=12):
    """Coolant hose with crimped ferrules at both ends.
    Returns dict(hose=..., ferrules=...)."""
    path = P.catmull(points, step=max(5.0, radius * 1.4), sag=sag)
    hb = obj_from_bm(name, P.sweep(path, radius, sides), None, collection, M.get("rubber"),
                     bevel=0.0)
    fb = bmesh.new()
    P.merge(fb, ferrule_bm(radius), frame(path[0], path[0] - path[1]))
    P.merge(fb, ferrule_bm(radius), frame(path[-1], path[-1] - path[-2]))
    fo = obj_from_bm(name + "_Ferrules", fb, None, collection, M.get("steel"), bevel=0.0)
    return dict(hose=hb, ferrules=fo)


def p_clip_bm(radius, width=10.0):
    """P-clip around a run along local Z. Mounting surface is the plane
    y = -(radius + 1.4); the tab runs out along +X with one M4 screw."""
    from .mech import screw_bm
    t = 1.4
    bm = P.revolve(P.ring_profile(radius + 0.1, radius + t, -width / 2, width / 2, 0.3),
                   P.auto_segs(radius * 3))
    tab_len = radius + 13.0
    tab = P.box(tab_len, 2 * t, width)
    P.merge(bm, tab, T(tab_len / 2, -(radius + t) + t, 0))
    P.merge(bm, screw_bm("M4", "shcs", washer=True),
            T(radius + 7.5, -(radius + t) + 2 * t, 0) @ R("X", -90))
    return bm


def p_clips(name, run_points, radius, base_dir, spacing=100.0, collection=None,
            sag=0.0, at=None, flip=False):
    """One part holding the P-clips for a run. Clips are spaced every `spacing`
    mm along the path (or at explicit path fractions `at`); base_dir points
    from the cable towards the structure the clips screw into."""
    path = P.catmull(run_points, step=4.0, sag=sag)
    d = [0.0]
    for a, b in zip(path, path[1:]):
        d.append(d[-1] + (b - a).length)
    total = d[-1]
    if at is None:
        n = max(1, round(total / spacing))
        at = [(i + 0.5) / n for i in range(n)]
    bm = bmesh.new()
    for f in at:
        s = f * total
        i = max(1, min(len(path) - 1, next(k for k, v in enumerate(d) if v >= s)))
        pos = path[i]
        tan = (path[i] - path[i - 1]).normalized()
        up = -Vector(base_dir)
        up = (up - tan * up.dot(tan)).normalized()
        side = up.cross(tan)
        if flip:                                         # tab on the other side of the run
            side, tan = -side, -tan
        from mathutils import Matrix
        F = Matrix((side, up, tan)).transposed().to_4x4()
        F.translation = pos
        P.merge(bm, p_clip_bm(radius), F)
    ob = obj_from_bm(name, bm, None, collection, M.get("fastener"), bevel=0.0)
    ob["rj28_count"] = len(at)
    return ob
