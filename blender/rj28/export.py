"""Phase 8 export: the web model, its feature edges, the studio HDRI and the
data the site animates from.

Regenerate everything, from the repository root:

    blender --background --python blender/build.py -- export all
    npm --prefix tools/gltf ci
    node tools/gltf/optimize.mjs
    node tools/gltf/verify.mjs
    blender --background --python blender/build.py -- export check

Step 1 builds the model and writes
    blender/out/export/rj28_lod0.raw.glb, rj28_lod1.raw.glb, rj28_edges.raw.glb, stats.json
    site/src/data/mount.json, site/src/data/stations.json
    site/public/hdri/studio.hdr
    docs/review/phase8/station_*.jpg
Step 3 compresses the raw files into site/public/models/ and writes
site/src/data/model.json. Step 4 checks the compressed files against
parts.json. Step 5 re-imports them into an empty scene and renders
docs/review/phase8/check_*.jpg.

Options of the export target: lod0 lod1 edges stations hdri all, plus
    cache            reuse blender/out/export/model.blend instead of rebuilding (it is written on every build)
    stations=02,05   render only these station proofs
    noproof          write stations.json without rendering
    check            step 5

What is in the files
--------------------
Axes are glTF's: +Y up, the robot faces +Z, its left is +X; metres. A robot
vector (x, y, z) in mm is (x, z, -y) / 1000 there.

No texture bake. Bevels are real geometry, materials are fourteen shared
constant-factor stand-ins that carry the names RJ28_<key>, and the site
rebuilds its shaders from those names. Only the decal atlas is a texture.

COLOR_0 is data, not colour:
    R  1 on the faces of a convex bevel or chamfer, 0 elsewhere. It is set per
       face corner, so it steps at the edge of the strip and never bleeds
       across a flat. LOD1 has no bevels, so R is 0 there.
    G  0
    B  cavity: short-range occlusion (40 mm, weighted to the first few), 0 open,
       1 buried, measured on the assembled robot with the mount stowed. Taken
       about the shading normal, so the top of a panel stays clean beside a
       dark gap, and faded out on faces too wide for corner values to mean
       anything. It marks crevices and packed mechanism; it is not a full
       ambient-occlusion bake.

Part nodes keep an identity transform; the only nodes that carry one are the
mount parts (posed by exact rotation, see mount.json) and the AXIS_ empties,
whose local +Z is the joint axis. Positions therefore stay 32-bit floats,
snapped to a 1/32768 m grid so they still compress (optimize.mjs).
"""
import json
import math
import struct
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import axes, explode, materials as M, measure, model, params as PR, parts, poses
from .lib.core import MM, frame

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "blender" / "out" / "export"
DATA = ROOT / "site" / "src" / "data"
MODELS = ROOT / "site" / "public" / "models"
REVIEW = ROOT / "docs" / "review" / "phase8"

POSE = "stowed"                    # the pose the GLBs are exported in
DISSOLVE_DEG = 0.2                 # LOD0: merge faces that are coplanar to within this (exact for the eye)
LOD0_MIN_BEVEL = 0.35              # mm; narrower bevels are dropped from LOD0 (they never reach a pixel)
SHARP_DEG = 35.0                   # hard-edge angle where no bevel is exported (same as core.shade)
FEATURE_DEG = 30.5                 # feature-edge angle for the line model (bevel weights are set at 30)
CHAMFER_MAX = 1.6                  # mm; modelled chamfers up to this width count as edge strips
CAVITY_MM = 40.0                   # reach of the cavity estimate
CAVITY_FACE_MIN, CAVITY_FACE_MAX = 30.0, 70.0   # mm; faces wider than this (root of area) fade out of the cavity mask
CAVITY_GAIN = 1.25                 # full scale is reached before every ray is blocked at zero distance
CAVITY_STEPS = 31                  # levels it is stored in (it is a soft mask; fewer levels compress better)
ATLAS_PX = 2048                    # decal atlas edge in the raw files (optimize.mjs halves it for LOD1)
FW_ATTR = "__mod_weightednormals_faceweight"
FW_FLAT = 16384                    # bevel modifier: face strength of an original face
KEEP_UV = {"decal", "mesh", "braid"}   # materials whose shaders read the UV map
NO_OCCLUDER = {"decal", "glass", "mesh"}

# LOD1: share of the un-bevelled triangles kept, by material; floors keep small parts from vanishing.
# Armour is not decimated at all: it is the silhouette, its 2 mm gaps are the panel lines, and plates and
# markings sit within a millimetre of it. The triangles come out of mechanism and fasteners instead.
LOD1_DISSOLVE_DEG = 1.0
LOD1_RATIO = {"armour": 1.0, "cap": 0.26, "cfrp": 0.40, "alu": 0.14, "ti": 0.14, "steel": 0.14, "rubber": 0.11,
              "braid": 0.16, "fastener": 0.0, "glass": 1.0, "mesh": 1.0, "emissive": 1.0, "cavity": 1.0}
LOD1_FLOOR = {"fastener": 8}       # triangles per loose piece
LOD1_FLOOR_PIECE = 36
LOD1_FLOOR_PART = 120              # small and thin parts are left alone: collapsing a plate tilts its face
DECAL_LIFT = 0.15                  # mm; markings are re-seated this far above a decimated host

_CONV = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))     # robot axes -> glTF axes


# ── axes and small helpers ───────────────────────────────────────────────────
def gl(v, nd=5):
    """Vector in robot axes -> glTF axes (same unit)."""
    return [round(float(v[0]), nd) + 0.0, round(float(v[2]), nd) + 0.0, round(-float(v[1]), nd) + 0.0]


def gl_matrix(m, nd=9):
    """4x4 in robot axes (metres) -> glTF axes, column-major list."""
    g = _CONV @ m @ _CONV.inverted()
    return [round(g[r][c], nd) for c in range(4) for r in range(4)]


def _metres(m):
    out = m.copy()
    out.translation = out.translation * MM
    return out


def part_objects():
    obs = sorted(parts.all_parts(), key=lambda o: o.name)
    assert all(o.type == "MESH" for o in obs)
    return obs


def roots():
    return sorted((o for o in bpy.data.objects if o.type == "EMPTY" and "explode_stage" in o and "rj28_assembly" in o),
                  key=lambda o: o.name)


def _tris(me):
    n = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_total", n)
    return int((n - 2).sum())


def _key(ob):
    return ob.get("rj28_material", "")


# ── scene ────────────────────────────────────────────────────────────────────
def scene(cache=False):
    """Build the model (or reopen the last build), with joint axes and explode data, mount stowed."""
    blend = RAW / "model.blend"
    if cache and blend.exists():
        bpy.ops.wm.open_mainfile(filepath=str(blend))
        print("EXPORT scene from", blend)
    else:
        model.build()
        axes.build()
        RAW.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    # explode.apply() measures every part where it stands, against a cannon spine drawn level. So the
    # offsets of the mount parts only mean something if they are taken with the mount level: they are
    # vectors in the cannon's own frame, and parts.json holds them that way.
    poses.set_mount("deployed")
    explode.apply()
    poses.set_mount(POSE)
    obs = part_objects()
    for ob in obs:
        assert ob.parent is not None and ob.parent.type == "EMPTY", f"{ob.name} has no assembly node"
        host = bpy.data.objects.get(ob.get("rj28_host", ""))
        if host is not None:
            assert ob.get("mount_group", "") == host.get("mount_group", ""), f"{ob.name} would not follow {host.name}"
    return obs


# ── mesh arrays ──────────────────────────────────────────────────────────────
class Faces:
    """Face and edge tables of a mesh as numpy arrays."""

    def __init__(self, me):
        nf, nl, ne, nv = len(me.polygons), len(me.loops), len(me.edges), len(me.vertices)
        self.nf, self.nl, self.ne, self.nv = nf, nl, ne, nv
        self.normal = np.zeros(nf * 3, np.float32)
        self.center = np.zeros(nf * 3, np.float32)
        self.area = np.zeros(nf, np.float32)
        self.start = np.zeros(nf, np.int32)
        self.total = np.zeros(nf, np.int32)
        self.lvert = np.zeros(nl, np.int32)
        self.ledge = np.zeros(nl, np.int32)
        self.co = np.zeros(nv * 3, np.float32)
        me.polygons.foreach_get("normal", self.normal)
        me.polygons.foreach_get("center", self.center)
        me.polygons.foreach_get("area", self.area)
        me.polygons.foreach_get("loop_start", self.start)
        me.polygons.foreach_get("loop_total", self.total)
        me.loops.foreach_get("vertex_index", self.lvert)
        me.loops.foreach_get("edge_index", self.ledge)
        me.vertices.foreach_get("co", self.co)
        self.normal.shape = self.center.shape = (nf, 3)
        self.co.shape = (nv, 3)
        self.lface = np.repeat(np.arange(nf, dtype=np.int32), self.total)
        # edges with exactly two faces
        self.count = np.bincount(self.ledge, minlength=ne)
        order = np.argsort(self.ledge, kind="stable")
        first = np.cumsum(self.count) - self.count
        self.two = np.nonzero(self.count == 2)[0]
        self.f1 = self.lface[order[first[self.two]]]
        self.f2 = self.lface[order[first[self.two] + 1]]
        n1, n2 = self.normal[self.f1], self.normal[self.f2]
        self.angle = np.arccos(np.clip((n1 * n2).sum(1), -1.0, 1.0))
        d = self.center[self.f2] - self.center[self.f1]
        self.fold = (d * n1).sum(1) - (d * n2).sum(1)          # negative where the edge is convex

    def width(self):
        """Mean width of each face: 2 x area / perimeter."""
        nxt = np.arange(self.nl, dtype=np.int32) + 1
        nxt[self.start + self.total - 1] = self.start
        seg = np.linalg.norm(self.co[self.lvert[nxt]] - self.co[self.lvert], axis=1)
        per = np.bincount(self.lface, weights=seg, minlength=self.nf)
        return 2.0 * self.area / np.maximum(per, 1e-12)


def edge_strips(me):
    """Per face: True on the faces of a convex bevel strip or chamfer."""
    F = Faces(me)
    if F.nf == 0:
        return np.zeros(0, bool), F
    convex = F.fold < -1e-7
    turn = np.where(F.angle > math.radians(3.0), F.angle, 0.0) * np.where(convex, 1.0, -1.0)
    if FW_ATTR in me.attributes:
        fw = np.zeros(F.nf, np.int32)
        me.attributes[FW_ATTR].data.foreach_get("value", fw)
        vote = np.bincount(F.f1, weights=turn, minlength=F.nf) + np.bincount(F.f2, weights=turn, minlength=F.nf)
        return (fw != FW_FLAT) & (vote > 0), F
    # no bevel modifier: a modelled chamfer is a narrow face with a convex fold to a wider face on two sides
    w = F.width()
    ok = convex & (F.angle > math.radians(20.0)) & (F.angle < math.radians(80.0))
    n = (np.bincount(F.f1[ok & (w[F.f2] >= 2.0 * w[F.f1])], minlength=F.nf)
         + np.bincount(F.f2[ok & (w[F.f1] >= 2.0 * w[F.f2])], minlength=F.nf))
    return (w < CHAMFER_MAX * MM) & (n >= 2), F


def paint(me, strip, F, cavity=None):
    """Write COLOR_0: R = edge strip, B = cavity, both per face corner."""
    col = np.zeros((F.nl, 4), np.float32)
    col[:, 3] = 1.0
    if strip is not None and len(strip):
        col[:, 0] = strip[F.lface]
    if cavity is not None:
        col[:, 2] = cavity
    for a in list(me.color_attributes):
        me.color_attributes.remove(a)
    ca = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
    ca.data.foreach_set("color", col.ravel())
    me.color_attributes.active_color = ca
    me.color_attributes.render_color_index = 0


# ── cavity ───────────────────────────────────────────────────────────────────
def _hemisphere():
    """Fixed directions about +Z with their cosine weights: the axis, a ring at 38 degrees, a ring at 68."""
    out = [(0.0, 0.0, 1.0)]
    for tilt, n, phase in ((38.0, 5, 0.0), (68.0, 7, 0.4)):
        t = math.radians(tilt)
        out += [(math.sin(t) * math.cos(phase + 2 * math.pi * i / n), math.sin(t) * math.sin(phase + 2 * math.pi * i / n),
                 math.cos(t)) for i in range(n)]
    d = np.array(out, np.float64)
    return d, d[:, 2] / d[:, 2].sum()


def cavity(finals, obs):
    """Short-range occlusion on every part: {name: one value per face corner}.

    Rays leave from just above the surface, in a fixed pattern about the corner's shading normal, and
    are tested against the whole assembled robot. Using the corner normal rather than the vertex normal
    matters on a hard edge: the top of a panel then looks up and stays clean while its side wall looks
    into the gap. Corners that share a vertex and a normal share one value, so nothing is split that
    the normals had not split already."""
    t0 = time.time()
    verts, tris, off = [], [], 0
    world = {}
    for ob in obs:
        me = finals[ob.name]
        n = len(me.vertices)
        co = np.zeros(n * 3, np.float64)
        me.vertices.foreach_get("co", co)
        mw = np.array(ob.matrix_world, np.float64)
        co = co.reshape(n, 3) @ mw[:3, :3].T + mw[:3, 3]
        world[ob.name] = (co, mw[:3, :3])
        if _key(ob) in NO_OCCLUDER or me.shape_keys:
            continue
        me.calc_loop_triangles()
        t = np.zeros(len(me.loop_triangles) * 3, np.int32)
        me.loop_triangles.foreach_get("vertices", t)
        verts.append(co)
        tris.append(t.reshape(-1, 3) + off)
        off += n
    bvh = BVHTree.FromPolygons(np.concatenate(verts).tolist(), np.concatenate(tris).tolist(), all_triangles=True)
    dirs, wts = _hemisphere()
    reach, lift = CAVITY_MM * MM, 0.3 * MM
    wl = wts.tolist()
    cast = bvh.ray_cast
    out, rays = {}, 0
    for ob in obs:
        me = finals[ob.name]
        co, rot = world[ob.name]
        nl = len(me.loops)
        if me.shape_keys or nl == 0:
            out[ob.name] = np.zeros(nl, np.float32)
            continue
        lv = np.zeros(nl, np.int64)
        me.loops.foreach_get("vertex_index", lv)
        cn = np.zeros(nl * 3, np.float64)
        me.corner_normals.foreach_get("vector", cn)
        cn = cn.reshape(nl, 3)
        q = np.round(cn * 127.0).astype(np.int64) + 128
        _, first, inv = np.unique((lv << 24) | (q[:, 0] << 16) | (q[:, 1] << 8) | q[:, 2], return_index=True,
                                  return_inverse=True)
        no = cn[first] @ rot.T
        no /= np.maximum(np.linalg.norm(no, axis=1, keepdims=True), 1e-12)
        ref = np.where(np.abs(no[:, :1]) > 0.9, np.array([[0.0, 1.0, 0.0]]), np.array([[1.0, 0.0, 0.0]]))
        tx = np.cross(no, ref)
        tx /= np.maximum(np.linalg.norm(tx, axis=1, keepdims=True), 1e-12)
        ty = np.cross(no, tx)
        ray = (dirs[None, :, 0, None] * tx[:, None, :] + dirs[None, :, 1, None] * ty[:, None, :]
               + dirs[None, :, 2, None] * no[:, None, :]).tolist()
        org = (co[lv[first]] + no * lift).tolist()
        vals = [0.0] * len(org)
        for i, o in enumerate(org):
            acc = 0.0
            for d, w in zip(ray[i], wl):
                hit = cast(o, d, reach)
                if hit[0] is not None:
                    k = 1.0 - hit[3] / reach
                    acc += w * k * k                   # squared: a crevice counts, a neighbour 30 mm away barely
            vals[i] = acc
        rays += len(org) * len(wl)
        v = np.clip(np.array(vals, np.float32) * CAVITY_GAIN, 0.0, 1.0)
        # A value only exists at the corners. On a face much wider than the reach it would be stretched
        # right across (a panel lapped at two edges would come out dark all over), so wide faces are
        # faded out, and corners that share a value take the lowest.
        nf = len(me.polygons)
        area = np.zeros(nf, np.float32)
        total = np.zeros(nf, np.int32)
        me.polygons.foreach_get("area", area)
        me.polygons.foreach_get("loop_total", total)
        size = np.sqrt(area) / MM
        fade = np.clip((CAVITY_FACE_MAX - size) / (CAVITY_FACE_MAX - CAVITY_FACE_MIN), 0.0, 1.0)
        per_corner = v[inv] * np.repeat(fade, total)
        low = np.ones(len(v), np.float32)
        np.minimum.at(low, inv, per_corner)
        out[ob.name] = (np.round(low * CAVITY_STEPS) / CAVITY_STEPS)[inv]
    print(f"EXPORT cavity {rays} rays against {off} vertices, {time.time() - t0:.0f} s")
    return out


# ── part meshes for a level of detail ────────────────────────────────────────
def _pieces(bm):
    seen, n = set(), 0
    for v in bm.verts:
        if v.index in seen:
            continue
        n += 1
        stack = [v]
        seen.add(v.index)
        while stack:
            x = stack.pop()
            for e in x.link_edges:
                o = e.other_vert(x)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
    return n


def _lod1_ratio(key, tris, pieces):
    if key in LOD1_FLOOR:
        keep = max(LOD1_FLOOR[key] * pieces, 24)
    else:
        keep = max(LOD1_RATIO.get(key, 0.2) * tris, LOD1_FLOOR_PIECE * pieces, LOD1_FLOOR_PART)
    return min(1.0, keep / max(tris, 1))


def build_meshes(obs, lod):
    """Export mesh for every part: {name: Mesh}. The scene's own meshes and modifiers are left as they were.

    LOD0: coplanar faces merged, bevels at one segment (dropped under LOD0_MIN_BEVEL), weighted normals.
    LOD1: no bevels, collapse-decimated per part to LOD1_RATIO with floors, hard edges sharp by angle.
    """
    t0 = time.time()
    finals, undo, work = {}, [], []
    for ob in obs:
        src = ob.data
        if src.shape_keys or ob.get("rj28_decal"):
            finals[ob.name] = src.copy()               # the energy chain keeps its shape keys; decals are already quads
            continue
        bevel = ob.modifiers.get("Bevel")
        keep_bevel = lod == 0 and bevel is not None and bevel.width > LOD0_MIN_BEVEL * MM
        w = src.copy()
        bm = bmesh.new()
        bm.from_mesh(w)
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(DISSOLVE_DEG if lod == 0 else LOD1_DISSOLVE_DEG),
                                 use_dissolve_boundaries=False, verts=bm.verts[:], edges=bm.edges[:],
                                 delimit={"MATERIAL", "SHARP", "UV"})
        if not keep_bevel:                             # the bevel is not there to soften them: hard edges go sharp
            lim = math.radians(SHARP_DEG)
            for e in bm.edges:
                e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > lim)
        ratio = 1.0
        if lod == 1:
            ratio = _lod1_ratio(_key(ob), sum(len(f.verts) - 2 for f in bm.faces), _pieces(bm))
        bm.to_mesh(w)
        bm.free()
        work.append(w)
        undo.append((ob, src, [(m, m.show_viewport) for m in ob.modifiers],
                     (bevel.segments, bevel.face_strength_mode) if bevel else None))
        ob.data = w
        if bevel is not None:
            if keep_bevel:
                bevel.segments = 1
                bevel.face_strength_mode = "FSTR_ALL"   # tags strip and corner faces for the edge mask
            else:
                bevel.show_viewport = False
        if lod == 1:
            for m in ob.modifiers:
                m.show_viewport = False
            if ratio < 0.999:
                dec = ob.modifiers.new("_lod", "DECIMATE")
                dec.decimate_type = "COLLAPSE"
                dec.ratio = ratio
                dec.use_collapse_triangulate = True
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    for ob, *_ in undo:
        finals[ob.name] = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
    for ob, src, mods, bev in undo:
        if "_lod" in ob.modifiers:
            ob.modifiers.remove(ob.modifiers["_lod"])
        ob.data = src
        for m, vis in mods:
            m.show_viewport = vis
        if bev:
            ob.modifiers["Bevel"].segments, ob.modifiers["Bevel"].face_strength_mode = bev
    for w in work:
        bpy.data.meshes.remove(w)
    if lod == 1:
        # second pass: hard edges sharp by angle on the decimated mesh, then the build's own weighted
        # normals. Without them a big flat face shades towards every shallow fold it touches.
        fixed, undo = 0, []
        for ob in obs:
            me = finals[ob.name]
            wn = ob.modifiers.get("WeightedNormal")
            if me.shape_keys or ob.get("rj28_decal") or wn is None:
                continue
            fixed += bool(me.validate())               # collapse can leave a doubled or zero-area face behind
            if "custom_normal" in me.attributes:
                me.attributes.remove(me.attributes["custom_normal"])
            me.set_sharp_from_angle(angle=math.radians(SHARP_DEG))
            undo.append((ob, ob.data, me, [(m, m.show_viewport) for m in ob.modifiers]))
            ob.data = me
            for m in ob.modifiers:
                m.show_viewport = m == wn
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        for ob, *_ in undo:
            finals[ob.name] = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
        for ob, src, me, mods in undo:
            ob.data = src
            for m, vis in mods:
                m.show_viewport = vis
            bpy.data.meshes.remove(me)
        print(f"EXPORT lod1 meshes repaired after decimation: {fixed}, markings re-seated: {_reseat(obs, finals)}")
    print(f"EXPORT lod{lod} meshes {sum(_tris(m) for m in finals.values())} triangles, {time.time() - t0:.0f} s")
    return finals


def _reseat(obs, finals):
    """Put every marking back on the surface of its host as that host now is. A marking floats 0.12 mm
    above the part it was draped on; a decimated host moves further than that."""
    n = 0
    for ob in obs:
        host = bpy.data.objects.get(ob.get("rj28_host", ""))
        if not ob.get("rj28_decal") or host is None:
            continue
        hm = finals[host.name]
        hm.calc_loop_triangles()
        bvh = BVHTree.FromPolygons([v.co.copy() for v in hm.vertices], [tuple(t.vertices) for t in hm.loop_triangles],
                                   all_triangles=True)
        for v in finals[ob.name].vertices:
            nrm = v.normal.copy()
            hit = bvh.ray_cast(v.co + nrm * 6.0 * MM, -nrm, 14.0 * MM)
            if hit[0] is not None:
                v.co = hit[0] + nrm * DECAL_LIFT * MM
        n += 1
    return n


def finish_meshes(obs, finals, lod, mats):
    """Edge mask and cavity into COLOR_0, stand-in materials, no stray UV maps."""
    occ = cavity(finals, obs)
    strips = 0
    for ob in obs:
        me = finals[ob.name]
        if lod == 0 and not ob.get("rj28_decal"):
            strip, F = edge_strips(me)
        else:
            strip, F = None, Faces(me)
        strips += int(strip.sum()) if strip is not None else 0
        paint(me, strip, F, occ[ob.name])
        if FW_ATTR in me.attributes:
            me.attributes.remove(me.attributes[FW_ATTR])
        keys = {m.get("rj28_key", "") for m in me.materials if m is not None}
        if not keys & KEEP_UV:
            for uv in list(me.uv_layers):
                me.uv_layers.remove(uv)
        for i, m in enumerate(me.materials):
            me.materials[i] = mats[m["rj28_key"]]
    print(f"EXPORT lod{lod} edge-strip faces {strips}")


# ── materials ────────────────────────────────────────────────────────────────
def web_atlas():
    """The decal atlas at web size: halved with premultiplied alpha, colour bled into the transparent
    surround so filtering does not darken the edges of the letters."""
    src = next(i for i in bpy.data.images if i.name.startswith("decals"))
    w, h = src.size
    a = np.empty(w * h * 4, np.float32)
    src.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)
    while a.shape[0] > ATLAS_PX:
        pm = a.copy()
        pm[..., :3] *= pm[..., 3:]
        pm = (pm[0::2, 0::2] + pm[1::2, 0::2] + pm[0::2, 1::2] + pm[1::2, 1::2]) / 4.0
        pm[..., :3] /= np.maximum(pm[..., 3:], 1e-6)
        a = pm
    rgb, filled = a[..., :3].copy(), a[..., 3] > 0.0
    for _ in range(8):
        grown = filled.copy()
        for ax, sh in ((0, 1), (0, -1), (1, 1), (1, -1)):
            nb_f = np.roll(filled, sh, ax)
            take = nb_f & ~grown
            rgb[take] = np.roll(rgb, sh, ax)[take]
            grown |= take
        filled = grown
    a[..., :3] = np.where(filled[..., None], rgb, 0.0)
    out = bpy.data.images.new("rj28_decals", a.shape[1], a.shape[0], alpha=True)
    out.colorspace_settings.name = src.colorspace_settings.name
    out.alpha_mode = "STRAIGHT"
    out.pixels.foreach_set(a.ravel())
    out.file_format = "PNG"
    out.filepath_raw = str(RAW / "rj28_decals.png")
    out.save()
    return out


def standins(obs):
    """Plain Principled materials under the names of the procedural ones: {key: Material}. The exporter
    cannot read node trees; constants come from the inputs materials.py set on the originals."""
    used, open_keys = {}, set()
    for ob in obs:
        for m in ob.data.materials:
            used[m["rj28_key"]] = m
        if _key(ob) != "decal":
            F = Faces(ob.data)
            if (F.count == 1).any():
                open_keys.add(_key(ob))                 # not a closed solid: its inside can be seen
    atlas = web_atlas()
    out, renamed = {}, []
    for key, src in sorted(used.items()):
        b = src.node_tree.nodes["Principled BSDF"]
        name = src.name
        src.name = name + ".procedural"
        renamed.append((src, name))
        m = bpy.data.materials.new(name)
        assert m.name == name
        m.use_nodes = True
        nb = m.node_tree.nodes["Principled BSDF"]
        col = list(b.inputs["Base Color"].default_value)
        rough = b.inputs["Roughness"].default_value
        if key == "glass":                             # opaque stand-in: what is left after transmission
            k = 1.0 - b.inputs["Transmission Weight"].default_value
            col = [c * k for c in col[:3]] + [1.0]
        nb.inputs["Base Color"].default_value = col
        nb.inputs["Metallic"].default_value = b.inputs["Metallic"].default_value
        nb.inputs["Roughness"].default_value = rough
        if key == "emissive":
            nb.inputs["Emission Color"].default_value = b.inputs["Emission Color"].default_value
            nb.inputs["Emission Strength"].default_value = b.inputs["Emission Strength"].default_value
        if key == "decal":
            tex = m.node_tree.nodes.new("ShaderNodeTexImage")
            tex.image = atlas
            m.node_tree.links.new(tex.outputs["Color"], nb.inputs["Base Color"])
            m.node_tree.links.new(tex.outputs["Alpha"], nb.inputs["Alpha"])
            m.surface_render_method = "BLENDED"
        m.use_backface_culling = key not in open_keys
        m["rj28_key"] = key
        out[key] = m
    print("EXPORT materials", " ".join(m.name for m in out.values()), "| double-sided:", " ".join(sorted(open_keys)))
    return out, renamed


def restore_materials(mats, renamed):
    for m in mats.values():
        bpy.data.materials.remove(m)
    for src, name in renamed:
        src.name = name


# ── joint axes ───────────────────────────────────────────────────────────────
def axis_nodes():
    """Parent the AXIS_ empties under one empty named AXES and turn each so that, after the exporter's
    change to +Y up, the node's local +Z is the joint axis. Returns (holder, {name: extras}, tracker rest)."""
    holder = bpy.data.objects.get("AXES")
    if holder is None:
        holder = bpy.data.objects.new("AXES", None)
        bpy.data.collections["RJ28-AXES"].objects.link(holder)
    turn = Matrix.Rotation(math.radians(-90.0), 4, "X")
    elev = poses.pose_matrices(*poses.STATES[POSE])["elev"]
    extras, rest = {}, {}
    for j in axes.joints():
        e = bpy.data.objects["AXIS_" + j["name"]]
        m = frame(j["origin"], j["axis"])
        origin, axis = j["origin"], j["axis"]
        if e.get("rj28_rides") == "mount_elevation":
            rest[e.name] = gl_matrix(_metres(m) @ turn)
            m = elev @ m
            origin, axis = elev @ origin, elev.to_3x3() @ axis
        e.parent = holder
        e.matrix_world = _metres(m) @ turn
        x = dict(joint=j["name"], group=j["group"], range=[float(j["range"][0]), float(j["range"][1])],
                 drive=j["drive"], origin=gl(origin * MM), axis=gl(axis, 6))
        if "rj28_rides" in e:
            x["rides"] = e["rj28_rides"]
        extras[e.name] = x
    bpy.context.view_layer.update()
    return holder, extras, rest


# ── GLB plumbing ─────────────────────────────────────────────────────────────
def read_glb(path):
    data = Path(path).read_bytes()
    magic, _ver, total = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF" and total == len(data)
    n, kind = struct.unpack_from("<I4s", data, 12)
    assert kind == b"JSON"
    js = json.loads(data[20:20 + n].decode("utf-8"))
    rest = data[20 + n:]
    blob = b""
    if rest:
        m, kind = struct.unpack_from("<I4s", rest, 0)
        assert kind == b"BIN\x00"
        blob = rest[8:8 + m]
    return js, blob


def write_glb(path, js, blob):
    j = json.dumps(js, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    j += b" " * (-len(j) % 4)
    blob = bytes(blob) + b"\x00" * (-len(blob) % 4)
    js_len = len(j)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + js_len + 8 + len(blob)))
        f.write(struct.pack("<I4s", js_len, b"JSON"))
        f.write(j)
        f.write(struct.pack("<I4s", len(blob), b"BIN\x00"))
        f.write(blob)


def node_extras(obs):
    """extras for every part and assembly node, offsets in glTF axes and metres."""
    out = {}
    for r in roots():
        out[r.name] = dict(assembly=r["rj28_assembly"], title=r["rj28_title"], explode_stage=1,
                           explode_offset=gl(r["explode_offset"]))
    for ob in obs:
        x = dict(number=ob["rj28_number"], assembly=ob["rj28_assembly"], material_key=_key(ob),
                 material_class=measure.part_class(ob), explode_stage=int(ob.get("explode_stage", 2)),
                 explode_offset=gl(ob.get("explode_offset", (0, 0, 0))))
        if ob.get("mount_group"):
            x["mount_group"] = ob["mount_group"]
        if ob.get("rj28_host"):
            x["host"] = ob["rj28_host"]
        out[ob.name] = x
    return out


def tidy_glb(path, obs, extras, axis_extras):
    """Fix up what the exporter wrote: extras by node name, mesh names, root order. Returns node count."""
    js, blob = read_glb(path)
    names = [n["name"] for n in js["nodes"]]
    assert len(names) == len(set(names)), "duplicate node names"
    want = {o.name for o in obs} | {r.name for r in roots()} | set(axis_extras) | {"AXES"}
    assert set(names) == want, f"nodes differ: missing {sorted(want - set(names))[:5]} extra {sorted(set(names) - want)[:5]}"
    for n in js["nodes"]:
        n.pop("extras", None)
        x = extras.get(n["name"]) or axis_extras.get(n["name"])
        if x:
            n["extras"] = x
        if "mesh" in n:
            js["meshes"][n["mesh"]]["name"] = n["name"]
    for me in js["meshes"]:
        tn = (me.get("extras") or {}).get("targetNames")
        me.pop("extras", None)
        if tn:
            me["extras"] = {"targetNames": tn}
    for m in js.get("materials", []):
        m.pop("extras", None)
    sc = js["scenes"][js.get("scene", 0)]
    sc["nodes"].sort(key=lambda i: js["nodes"][i]["name"])
    sc["name"] = "RJ28"
    sc.pop("extras", None)
    js["asset"] = dict(version="2.0", generator="rj28 export")
    write_glb(path, js, blob)
    return len(js["nodes"])


def export_lod(obs, lod, mats, axis_extras):
    finals = build_meshes(obs, lod)
    finish_meshes(obs, finals, lod, mats)
    path = RAW / f"rj28_lod{lod}.raw.glb"
    src = {}
    for ob in obs:
        src[ob.name] = (ob.data, [(m, m.show_viewport) for m in ob.modifiers])
        ob.data = finals[ob.name]
    for o in bpy.data.objects:
        o.select_set(False)
    for o in obs + roots() + [bpy.data.objects["AXES"]] + [bpy.data.objects[n] for n in axis_extras]:
        o.hide_set(False)
        o.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", use_selection=True, export_apply=False, export_yup=True,
        export_extras=False, export_normals=True, export_tangents=False, export_texcoords=True,
        export_materials="EXPORT", export_image_format="AUTO", export_vertex_color="ACTIVE",
        export_all_vertex_colors=False, export_active_vertex_color_when_no_material=True, export_attributes=False,
        export_morph=True, export_morph_normal=True, export_morph_tangent=False, export_try_sparse_sk=False,
        export_animations=False, export_skins=False, export_cameras=False, export_lights=False,
        export_shared_accessors=False, use_mesh_edges=False, use_mesh_vertices=False)
    tris = sum(_tris(m) for m in finals.values())
    by_key = {}
    for ob in obs:
        by_key[_key(ob)] = by_key.get(_key(ob), 0) + _tris(finals[ob.name])
    for ob in obs:
        ob.data = src[ob.name][0]
    for me in finals.values():
        bpy.data.meshes.remove(me)
    nodes = tidy_glb(path, obs, node_extras(obs), axis_extras)
    print(f"EXPORT lod{lod} {path.name} {path.stat().st_size} bytes, {tris} triangles, {nodes} nodes")
    return dict(file=path.name, bytes=path.stat().st_size, triangles=tris, nodes=nodes, parts=len(obs),
                triangles_by_material=dict(sorted(by_key.items())))


# ── feature edges ────────────────────────────────────────────────────────────
def feature_edges(me):
    """(vertex indices used, index pairs) of the edges a drawing would show: folds sharper than
    FEATURE_DEG, open boundaries and edges shared by more than two faces. Taken from the mesh before its
    bevel, so a bevelled edge is one line."""
    F = Faces(me)
    ev = np.zeros(F.ne * 2, np.int32)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    keep = F.count != 2
    keep[F.two[F.angle > math.radians(FEATURE_DEG)]] = True
    used, pairs = _chains(ev[keep].tolist(), F.nv)
    return F, np.array(used, np.int64), np.array(pairs, np.uint32).reshape(-1, 2)


def _chains(pairs, nv):
    """Walk the segments end to end and number the vertices in the order they are met, so that both the
    index list and the positions run in long smooth sequences (that is what compresses)."""
    adj = [[] for _ in range(nv)]
    for k, (a, b) in enumerate(pairs):
        adj[a].append(k)
        adj[b].append(k)
    done = bytearray(len(pairs))
    new, used, out = {}, [], []
    starts = [v for v in range(nv) if len(adj[v]) % 2] + [v for v in range(nv) if adj[v] and not len(adj[v]) % 2]
    for v in starts:
        while True:
            k = -1
            while adj[v]:
                c = adj[v].pop()
                if not done[c]:
                    k = c
                    break
            if k < 0:
                break
            done[k] = 1
            a, b = pairs[k]
            w = b if a == v else a
            for x in (v, w):
                if x not in new:
                    new[x] = len(used)
                    used.append(x)
            out.append((new[v], new[w]))
            v = w
    return used, out


def export_edges(obs):
    """rj28_edges.raw.glb: one LINES primitive per part on a node of the same name, under the same
    assembly nodes and in the same pose. Decals get a node and no lines. The energy chain's lines carry
    the same morph target as its mesh."""
    blob = bytearray()
    js = dict(asset=dict(version="2.0", generator="rj28 export"), scene=0, scenes=[dict(name="RJ28", nodes=[])],
              nodes=[], meshes=[], accessors=[], bufferViews=[], buffers=[{}])

    def view(arr, target):
        blob.extend(b"\x00" * (-len(blob) % 4))
        js["bufferViews"].append(dict(buffer=0, byteOffset=len(blob), byteLength=arr.nbytes, target=target))
        blob.extend(arr.tobytes())
        return len(js["bufferViews"]) - 1

    def positions(p, bounds=True):
        acc = dict(bufferView=view(p, 34962), componentType=5126, count=len(p), type="VEC3")
        if bounds:
            acc["min"], acc["max"] = [float(v) for v in p.min(0)], [float(v) for v in p.max(0)]
        js["accessors"].append(acc)
        return len(js["accessors"]) - 1

    conv = np.array(_CONV.to_3x3(), np.float32)
    index, segments = {}, 0
    for r in roots():
        index[r.name] = len(js["nodes"])
        js["nodes"].append(dict(name=r.name, children=[]))
        js["scenes"][0]["nodes"].append(index[r.name])
    for ob in obs:
        node = dict(name=ob.name)
        if max(abs(a - b) for ra, rb in zip(ob.matrix_local, Matrix.Identity(4)) for a, b in zip(ra, rb)) > 1e-9:
            node["matrix"] = gl_matrix(ob.matrix_local)
        me = ob.data
        if not ob.get("rj28_decal") and len(me.edges):
            F, used, pairs = feature_edges(me)
            if len(pairs):
                p = (F.co[used] @ conv.T).astype(np.float32)
                prim = dict(mode=1, attributes=dict(POSITION=positions(p)))
                small = len(used) < 65536
                idx = pairs.astype(np.uint16 if small else np.uint32).ravel()
                js["accessors"].append(dict(bufferView=view(idx, 34963), componentType=5123 if small else 5125,
                                            count=int(idx.size), type="SCALAR"))
                prim["indices"] = len(js["accessors"]) - 1
                mesh = dict(name=ob.name, primitives=[prim])
                if me.shape_keys:
                    names, weights, targets = [], [], []
                    for kb in me.shape_keys.key_blocks[1:]:
                        k = np.zeros(F.nv * 3, np.float32)
                        kb.data.foreach_get("co", k)
                        d = ((k.reshape(-1, 3) - F.co)[used] @ conv.T).astype(np.float32)
                        targets.append(dict(POSITION=positions(d)))
                        names.append(kb.name)
                        weights.append(float(kb.value))
                    prim["targets"] = targets
                    mesh["weights"] = weights
                    mesh["extras"] = dict(targetNames=names)
                node["mesh"] = len(js["meshes"])
                js["meshes"].append(mesh)
                segments += len(pairs)
        js["nodes"][index[ob.parent.name]]["children"].append(len(js["nodes"]))
        js["nodes"].append(node)
    for r in roots():
        if not js["nodes"][index[r.name]]["children"]:
            del js["nodes"][index[r.name]]["children"]
    js["buffers"][0]["byteLength"] = len(blob) + (-len(blob) % 4)
    path = RAW / "rj28_edges.raw.glb"
    write_glb(path, js, blob)
    print(f"EXPORT edges {path.name} {path.stat().st_size} bytes, {segments} segments, {len(js['nodes'])} nodes")
    return dict(file=path.name, bytes=path.stat().st_size, segments=segments, nodes=len(js["nodes"]), parts=len(obs))


# ── mount data ───────────────────────────────────────────────────────────────
def write_mount(obs, tracker_rest):
    """mount.json: what the site needs to move the cannon exactly as poses.set_mount does."""
    tr = poses.trunnion()
    trav_pivot = Vector((PR.BORE_X, PR.TRUNNION_Y, PR.TRUNNION_Z - PR.YOKE_DROP - 39.0))
    groups = {g: [o.name for o in obs if o.get("mount_group") == g] for g in ("elev", "trav")}
    states = {s: dict(elevation=e, traverse=t) for s, (e, t) in poses.STATES.items()}
    check = {}
    for s, (e, t) in poses.STATES.items():
        pm = poses.pose_matrices(e, t)
        check[s] = {g: gl_matrix(_metres(pm[g])) for g in ("elev", "trav")}
    lock = [o for o in obs if o.get("zone") == "lock"]
    pin = next(o for o in lock if o.name.endswith("Travel_Lock_Pin"))
    c = sum((pin.matrix_world @ Vector(b) for b in pin.bound_box), Vector()) / 8.0
    dims = pin.dimensions
    long_axis = [1.0 if i == max(range(3), key=lambda k: dims[k]) else 0.0 for i in range(3)]
    chain = next(o for o in obs if o.get("mount_morph"))
    keys = [k.name for k in chain.data.shape_keys.key_blocks]
    data = dict(
        axes="glTF: +Y up, the robot faces +Z, its left is +X. Metres and degrees. Matrices are column-major.",
        glb_pose=POSE,
        states=states,
        limits=dict(elevation=[PR.ELEV_MIN, PR.ELEV_MAX], traverse=[-PR.TRAVERSE, PR.TRAVERSE]),
        elevation=dict(joint="mount_elevation", axis_node="AXIS_mount_elevation", pivot=gl(tr * MM), axis=[-1.0, 0.0, 0.0],
                       zero="barrel level, pointing the way the robot faces", positive="muzzle up"),
        traverse=dict(joint="mount_traverse", axis_node="AXIS_mount_traverse", pivot=gl(trav_pivot * MM),
                      axis=[0.0, 1.0, 0.0], positive="muzzle swings inboard, towards the robot's left"),
        pose=dict(
            E="T(elevation.pivot) * R(elevation.axis, elevation) * T(-elevation.pivot)",
            V="T(traverse.pivot) * R(traverse.axis, traverse) * T(-traverse.pivot)",
            elev="V * E",
            trav="V",
            apply="The mesh of every group node is drawn in the level pose (elevation 0, traverse 0) and the pose "
                  "is the node's own matrix; parents are assembly nodes with no transform. Set node.matrix to the "
                  "group's matrix.",
            explode="explode_offset of a group node is measured in the level pose, so it is a vector in the "
                    "cannon's own frame and goes inside the pose: node.matrix = matrix * T(explode_offset * amount). "
                    "For every other part the two orders are the same thing.",
            rotation="R(axis, angle) is the right-handed rotation about axis. The traverse turns the elevation "
                     "axis with it, which V * E already does; the trunnion pivot lies on the traverse axis.",
        ),
        groups=dict(elev=dict(matrix="V * E", nodes=groups["elev"]), trav=dict(matrix="V", nodes=groups["trav"])),
        riders=[dict(node=n, group="elev", matrix="V * E * rest_matrix", rest_matrix=m,
                     note="Joint axis that travels with the cannon. In the GLB it is posed like the group.")
                for n, m in sorted(tracker_rest.items())],
        check=check,
        travel_lock=dict(
            nodes=[o.name for o in lock], engaged="stowed", latch=next(o.name for o in lock if "Latch" in o.name),
            pivot=gl(c), axis=gl(long_axis),
            note="Fixed to the backpack; the sprung latch captures the breech when the barrel is vertical. The "
                 "latch is modelled closed and is not animated by the build."),
        energy_chain=dict(
            node=chain.name, method="morph_target", target=keys[1], target_index=0,
            basis="shape at elevation 0", weight="clamp(elevation / 90, 0, 1)", glb_weight=1.0,
            files=["rj28_lod0.glb", "rj28_lod1.glb", "rj28_edges.glb"],
            note="One mesh joining the fixed backpack to the elevating breech; it does not follow either group. "
                 "A linear blend between its two end shapes, as in the build. It does not follow the traverse."),
    )
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "mount.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("EXPORT mount.json", len(groups["elev"]), "elev", len(groups["trav"]), "trav")


# ── studio HDRI ──────────────────────────────────────────────────────────────
def studio_hdri():
    """Render the studio panorama and say where its light is, so a black or lampless file cannot pass."""
    from . import hero
    path = hero.hdri(width=2048)
    img = bpy.data.images.load(str(path))
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)[..., :3]
    bpy.data.images.remove(img)
    lum = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    # direction of every pixel in glTF axes: image centre looks along +Z (the way the robot faces),
    # the right-hand edge of the image is the robot's right (-X), rows run from straight down to straight up
    az = ((np.arange(w) + 0.5) / w - 0.5) * 2.0 * math.pi
    el = ((np.arange(h) + 0.5) / h - 0.5) * math.pi
    solid = np.cos(el)[:, None] * (math.pi / h) * (2.0 * math.pi / w)
    d = np.stack([-np.sin(az)[None, :] * np.cos(el)[:, None], np.sin(el)[:, None] * np.ones((1, w)),
                  np.cos(az)[None, :] * np.cos(el)[:, None]], -1)
    flux = lum * solid
    up = float(flux[h // 2:].sum() / flux.sum())
    y, x = np.unravel_index(int(lum.argmax()), lum.shape)
    key_rows = el > math.radians(45.0)                      # the key is the only lamp above 45 degrees
    kd = (d[key_rows] * flux[key_rows][..., None]).sum((0, 1))
    kd /= np.linalg.norm(kd)
    info = dict(file=path.name, bytes=path.stat().st_size, width=w, height=h, mean=round(float(lum.mean()), 4),
                max=round(float(lum.max()), 2), flux_from_above=round(up, 3),
                key_direction=[round(float(v), 3) for v in kd],
                brightest_direction=[round(float(v), 3) for v in d[y, x]],
                mapping="equirectangular; image centre is +Z (the way the robot faces), image right is -X, top is +Y")
    print("HDRI", json.dumps(info))
    assert lum.max() > 1.0 and up > 0.5, "the studio panorama has no lamps in it"
    return info


# ── driver ───────────────────────────────────────────────────────────────────
def run(opts):
    arg = {o.split("=")[0]: o.split("=")[1] for o in opts if "=" in o}
    if "check" in opts:
        return check()
    everything = "all" in opts
    want = {k for k in ("lod0", "lod1", "edges", "stations", "hdri") if everything or k in opts or k in arg}
    obs = scene("cache" in opts)
    RAW.mkdir(parents=True, exist_ok=True)
    stats_path = RAW / "stats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    stats["parts"] = len(obs)
    if "stations" in want:
        from . import stations
        if "noproof" not in opts:
            stations.render(set(arg["stations"].split(",")) if "stations" in arg else None)
        stations.write()
    if "hdri" in want:
        stats["hdri"] = studio_hdri()
    poses.set_mount(POSE)
    if "edges" in want:
        stats["edges"] = export_edges(obs)
    if want & {"lod0", "lod1"} or everything:
        _holder, axis_extras, tracker_rest = axis_nodes()
        write_mount(obs, tracker_rest)
        mats, renamed = standins(obs)
        try:
            for lod in (0, 1):
                if f"lod{lod}" in want:
                    stats[f"lod{lod}"] = export_lod(obs, lod, mats, axis_extras)
        finally:
            restore_materials(mats, renamed)
    stats_path.write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8", newline="\n")


# ── check: re-import the finished files and look at them ─────────────────────
def check():
    """Import the compressed GLBs into an empty scene and render them as they are."""
    from . import hero, render as RD
    from .lib import core as C
    for lod in (0, 1):
        C.reset_scene()
        path = RAW / f"check_lod{lod}.glb"             # written by verify.mjs from the compressed file
        bpy.ops.import_scene.gltf(filepath=str(path))
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
        tris = sum(_tris(o.data) for o in meshes)
        print(f"CHECK lod{lod} imported {len(bpy.data.objects)} objects, {len(meshes)} meshes, {tris} triangles")
        # COLOR_0 is data, but the importer multiplies it into the base colour: put the file's own factor back
        factors = {m["name"]: m.get("pbrMetallicRoughness", {}).get("baseColorFactor", [1, 1, 1, 1])
                   for m in read_glb(path)[0]["materials"]}
        for m in bpy.data.materials:
            b = m.node_tree.nodes.get("Principled BSDF") if m.use_nodes else None
            if b is None or m.name not in factors:
                continue
            tex = next((n for n in m.node_tree.nodes if n.type == "TEX_IMAGE"), None)
            for link in list(b.inputs["Base Color"].links):
                m.node_tree.links.remove(link)
            if tex is not None:
                m.node_tree.links.new(tex.outputs["Color"], b.inputs["Base Color"])
            else:
                b.inputs["Base Color"].default_value = factors[m.name]
        shots = dict(front=((2250, -3800, 1150), (-20, -80, 1030), 62), rear=((-2550, 3650, 1520), (-40, 70, 1060), 62))
        if lod == 0:
            shots["chest"] = ((420, -1500, 1500), (0, -150, 1390), 85)
        for name, (loc, target, lens) in shots.items():
            hero.studio(2000.0, 1.15, loc)
            hero.setup((1200, 1500) if name != "chest" else (1200, 900), 64, 1.0)
            RD.camera(loc, target, lens)
            RD.render(REVIEW / f"check_lod{lod}_{name}.jpg", "final")
        if lod == 0:
            mask = bpy.data.materials.new("_mask")
            mask.use_nodes = True
            nt = mask.node_tree
            nt.nodes.clear()
            col = nt.nodes.new("ShaderNodeVertexColor")
            em = nt.nodes.new("ShaderNodeEmission")
            out = nt.nodes.new("ShaderNodeOutputMaterial")
            nt.links.new(col.outputs["Color"], em.inputs["Color"])
            nt.links.new(em.outputs[0], out.inputs["Surface"])
            bpy.context.view_layer.material_override = mask
            for name, (loc, target, lens) in dict(mask_front=shots["front"], mask_chest=shots["chest"]).items():
                s = hero.setup((1200, 1500) if "chest" not in name else (1200, 900), 16, 1.0)
                s.view_settings.view_transform = "Standard"
                s.view_settings.look = "None"
                RD.camera(loc, target, lens)
                s.render.image_settings.file_format = "JPEG"
                s.render.filepath = str(REVIEW / f"check_lod0_{name}.jpg")
                bpy.ops.render.render(write_still=True)
                print("RENDER", s.render.filepath)
            bpy.context.view_layer.material_override = None
