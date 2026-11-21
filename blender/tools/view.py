"""Debug helper: build the whole model once and render close-ups of any spot.

    blender --background --python blender/tools/view.py -- name:tx,ty,tz:dx,dy,dz:dist[:mode[:aa,aa]] ...

target and direction (from the target towards the camera) in mm, robot axes; dist in mm;
mode clay|final; the optional assembly list isolates those assemblies. Writes blender/out/view_<name>.jpg.
"""
import sys
from pathlib import Path

from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rj28 import model, parts, review as RV  # noqa: E402
from rj28.lib import core as C  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
model.build(None, context=False)
if "deployed" in args:
    from rj28 import poses
    poses.set_mount("deployed")
    args.remove("deployed")
out = Path(__file__).resolve().parents[1] / "out"
for a in args:
    f = a.split(":")
    name, target, d, dist = f[0], Vector(map(float, f[1].split(","))), Vector(map(float, f[2].split(","))), float(f[3])
    mode = f[4] if len(f) > 4 else "clay"
    keep = set(f[5].split(",")) if len(f) > 5 else None
    objs = [o for o in parts.all_parts() if o.type == "MESH" and (keep is None or o.get("rj28_assembly") in keep)]
    lo, hi = C.bounds_mm(objs)
    RV.closeup(objs, out / f"view_{name}.jpg", name, d, mode, target=target, dist=dist / ((hi - lo).length * 0.62),
               isolate=keep is not None)
    print("VIEW", name)
