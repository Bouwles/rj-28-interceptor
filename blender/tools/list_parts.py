"""Print the bounding box of parts whose name matches any of the given words.

    blender --background --python blender/tools/list_parts.py -- thorax,pelvis Panel,Flank,Tub
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rj28 import model, parts  # noqa: E402
from rj28.lib import core as C  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
only = set(args[0].split(",")) if args and args[0] != "all" else None
words = args[1].split(",") if len(args) > 1 else [""]
model.build(only, context=False)
for ob in parts.all_parts():
    if ob.type == "MESH" and len(ob.data.vertices) and any(w in ob.name for w in words):
        lo, hi = C.bounds_mm([ob])
        print("PART", ob.name, [round(v) for v in lo], [round(v) for v in hi])
print("DONE")
