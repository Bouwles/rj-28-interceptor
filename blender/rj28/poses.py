"""Mount poses and the swept-volume clearance check.

The cannon has one main axis. Both states are exact rotations of the same
parts: objects tagged mount_group="elev" turn about the trunnion (and ride the
traverse), objects tagged "trav" turn about the slewing ring only.
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import params as PR
from .lib.core import MM, evaluated_mesh

STATES = {"deployed": (0.0, 0.0), "stowed": (90.0, 0.0)}


def trunnion():
    return Vector((PR.BORE_X, PR.TRUNNION_Y, PR.TRUNNION_Z))


def elev_matrix(deg):
    """mm-space rotation about the trunnion: 0 = level (-Y), 90 = muzzle up."""
    p = trunnion()
    return Matrix.Translation(p) @ Matrix.Rotation(math.radians(-deg), 4, "X") @ Matrix.Translation(-p)


def trav_matrix(deg):
    """mm-space rotation about the slewing ring; positive swings the muzzle inboard (+X)."""
    p = Vector((PR.BORE_X, PR.TRUNNION_Y, 0.0))
    return Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, "Z") @ Matrix.Translation(-p)


def _m(mat):
    out = mat.copy()
    out.translation = out.translation * MM
    return out


def pose_matrices(elev, trav):
    t = trav_matrix(trav)
    return {"elev": t @ elev_matrix(elev), "trav": t}


def set_mount(state="deployed", elev=None, trav=None):
    e, t = STATES.get(state, (0.0, 0.0))
    e = e if elev is None else elev
    t = t if trav is None else trav
    mats = pose_matrices(e, t)
    for ob in bpy.data.objects:
        g = ob.get("mount_group")
        if g in mats:
            ob.matrix_world = _m(mats[g])
    bpy.context.scene["rj28_mount"] = [e, t]
    bpy.context.view_layer.update()
    return e, t


# ── swept-volume check ───────────────────────────────────────────────────────
def _tris(ob):
    """World-space triangles (metres) of an evaluated object at rest pose."""
    me = evaluated_mesh(ob)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    verts = [v.co.copy() for v in bm.verts]
    tris = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    bpy.data.meshes.remove(me)
    return verts, tris


def _samples(verts, tris, spacing):
    pts = []
    for a, b, c in tris:
        A, B, Cc = verts[a], verts[b], verts[c]
        n = max(1, math.ceil(max((B - A).length, (Cc - A).length, (Cc - B).length) / spacing))
        for i in range(n + 1):
            for j in range(n + 1 - i):
                u, v = i / n, j / n
                pts.append(A * (1 - u - v) + B * u + Cc * v)
    return pts


class _Set:
    def __init__(self, objs, spacing):
        self.verts, self.tris, self.zone = [], [], []
        for ob in objs:
            v, t = _tris(ob)
            off = len(self.verts)
            self.verts += v
            self.tris += [(a + off, b + off, c + off) for a, b, c in t]
            self.zone += [ob.get("zone", "?")] * len(t)
        self.bvh = BVHTree.FromPolygons(self.verts, self.tris) if self.tris else None
        self.pts = _samples(self.verts, self.tris, spacing)


def sweep_check(spacing=10.0, step=2.5, report=None):
    """Sweep the mount through its whole travel and return the minimum
    clearance (mm) to every static zone, with the pose where it occurs.

    Checked: elevation -5..90 at zero traverse, then traverse +/-25 at 0 deg and
    at the depression limit. Sampling is two-way (moving points against the
    static mesh and static points against the moving mesh).
    """
    set_mount("deployed")
    objs = [o for o in bpy.data.objects if o.type == "MESH" and "zone" in o]
    static_zones = {"head", "cap", "neck", "thorax", "backpack", "pauldron_R", "arm_R", "hand_R",
                    "mount_fix", "abdomen", "pelvis", "leg_R"}
    groups = {
        "elev": _Set([o for o in objs if o.get("mount_group") == "elev" and o["zone"] != "mount_pin"],
                     spacing * MM),
        "trav": _Set([o for o in objs if o.get("mount_group") == "trav"], spacing * MM),
    }
    static = _Set([o for o in objs if o["zone"] in static_zones and not o.get("mount_group")], spacing * MM)
    # only static points near the mount matter for the reverse query
    near = [p for p in static.pts if p.x < -0.04 and p.z > 1.25]
    poses = [(e, 0.0) for e in np.arange(PR.ELEV_MIN, PR.ELEV_MAX + 0.01, step)]
    for e in (0.0, PR.ELEV_MIN):
        poses += [(e, t) for t in np.arange(-PR.TRAVERSE, PR.TRAVERSE + 0.01, step) if abs(t) > 1e-6]
    lim = 0.08
    best = {}

    def note(zone, group, dist, pose, where):
        key = (zone, group)
        if key not in best or dist < best[key][0]:
            best[key] = (dist, pose, where)

    for e, t in poses:
        mats = pose_matrices(float(e), float(t))
        for gname, g in groups.items():
            if not g.tris:
                continue
            Mw = _m(mats[gname])
            Mi = Mw.inverted()
            for p in g.pts:                                  # moving -> static
                q = Mw @ p
                hit = static.bvh.find_nearest(q, lim)
                if hit[0] is not None:
                    z = static.zone[hit[2]]
                    if gname == "trav" and z == "mount_fix":
                        continue                             # the yoke sits on its own ring
                    note(z, gname, hit[3], (float(e), float(t)), tuple(round(c / MM) for c in q))
            for p in near:                                   # static -> moving
                hit = g.bvh.find_nearest(Mi @ p, lim)
                if hit[0] is not None:
                    fi = static.bvh.find_nearest(p, 0.001)
                    z = static.zone[fi[2]] if fi[0] is not None else "?"
                    if gname == "trav" and z == "mount_fix":
                        continue
                    note(z, gname, hit[3], (float(e), float(t)), tuple(round(c / MM) for c in p))
    # elevating mass against its own yoke (same traverse, so only elevation matters)
    if groups["trav"].tris:
        for e in np.arange(PR.ELEV_MIN, PR.ELEV_MAX + 0.01, step):
            Mw = _m(elev_matrix(float(e)))
            for p in groups["elev"].pts:
                hit = groups["trav"].bvh.find_nearest(Mw @ p, lim)
                if hit[0] is not None:
                    note("yoke", "elev", hit[3], (float(e), 0.0), tuple(round(c / MM) for c in (Mw @ p)))
    out = []
    for (zone, group), (d, pose, where) in sorted(best.items(), key=lambda kv: kv[1][0]):
        out.append(dict(zone=zone, group=group, clearance_mm=round(d / MM, 1), elev=pose[0], trav=pose[1],
                        at_mm=where))
    worst = min((r["clearance_mm"] for r in out if r["zone"] != "yoke"), default=None)
    result = dict(required_mm=PR.CLEARANCE_MIN, min_clearance_mm=worst,
                  passed=worst is None or worst >= PR.CLEARANCE_MIN, poses=len(poses),
                  sample_spacing_mm=spacing, zones=out,
                  note="zones not listed never came within 80 mm of the mount")
    if report:
        import json
        from pathlib import Path
        Path(report).parent.mkdir(parents=True, exist_ok=True)
        Path(report).write_text(json.dumps(result, indent=2))
    return result
