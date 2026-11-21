"""Find parts that float and parts that sink into each other.

    blender --background --python blender/tools/check_contact.py -- [float_mm] [sink_mm]

FLOAT: no vertex of the part comes within float_mm (default 1.5) of any other part.
SINK:  some vertex of part A lies more than sink_mm (default 6) inside part B.
Fasteners, cables and decals are meant to sit inside their hosts and are skipped as A.
"""
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rj28 import model, parts  # noqa: E402
from rj28.lib import core as C  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FLOAT = float(args[0]) if args else 1.5
SINK = float(args[1]) if len(args) > 1 else 6.0
SKIP_A = ("Screw", "Bolt", "Stud", "Quarter_Turn", "Cable", "Lead", "Loom", "Hose", "Line", "Loop", "Plug", "Pin",
          "Label", "Mark", "Ferrule", "Clip", "Washer")

model.build(None, context=False)
items = []
for ob in parts.all_parts():
    if ob.type != "MESH" or not len(ob.data.vertices):
        continue
    me = C.evaluated_mesh(ob)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    vs = [v.co * 1000.0 for v in bm.verts]
    tree = BVHTree.FromPolygons(vs, [[v.index for v in f.verts] for f in bm.faces])
    lo = Vector([min(v[i] for v in vs) for i in range(3)])
    hi = Vector([max(v[i] for v in vs) for i in range(3)])
    items.append((ob.name, vs[::max(1, len(vs) // 1500)], tree, lo, hi, ob.get("rj28_assembly", "")))
    bm.free()
    bpy.data.meshes.remove(me)

floats, sinks = [], []
gap = {}                                   # part -> smallest distance to any other part, either direction
for name, vs, _, lo, hi, aa in items:
    if aa == "17":
        continue
    worst = (0.0, "")
    for other, _, tree, lo2, hi2, aa2 in items:
        if other == name or aa2 == "17" or any(lo[i] > hi2[i] + 20 or hi[i] < lo2[i] - 20 for i in range(3)):
            continue
        for v in vs:
            co, no, _, d = tree.find_nearest(v, 40.0)
            if co is None:
                continue
            gap[name] = min(gap.get(name, 1e9), d)
            gap[other] = min(gap.get(other, 1e9), d)
            if d > worst[0] and (v - co).dot(no) < 0 and tree.ray_cast(v, (v - co).normalized() * -1)[0] is not None:
                # behind the nearest face: count hits along one ray to confirm it is inside a closed solid
                hits, p, dirn = 0, v.copy(), Vector((0.3, 0.5, 0.81)).normalized()
                while True:
                    h = tree.ray_cast(p, dirn)
                    if h[0] is None:
                        break
                    hits += 1
                    p = h[0] + dirn * 1e-3
                if hits % 2:
                    worst = (d, other)
    if worst[0] > SINK and not any(k in name for k in SKIP_A) and "Thorax_Frame" not in worst[1]:
        sinks.append((worst[0], name, worst[1]))

floats = [(gap.get(n, 99.0), n) for n, *_rest, aa in items if aa != "17" and gap.get(n, 99.0) > FLOAT]
for d, name in sorted(floats, reverse=True):
    print(f"FLOAT {d:6.1f} {name}")
for d, a, b in sorted(sinks, reverse=True)[:80]:
    print(f"SINK {d:6.1f} {a} in {b}")
print("CHECK", len(items), "parts,", len(floats), "floating,", len(sinks), "sunk")
