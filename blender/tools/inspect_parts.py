"""Debug helper: build some assemblies and list suspicious parts.

    blender --background --python blender/tools/inspect_parts.py -- head,neck
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rj28 import model, parts  # noqa: E402
from rj28.lib import core as C  # noqa: E402

only = set(sys.argv[sys.argv.index("--") + 1].split(",")) if "--" in sys.argv else None
model.build(only, context=False)
for ob in parts.all_parts():
    if ob.type != "MESH":
        continue
    n = len(ob.data.vertices)
    lo, hi = C.bounds_mm([ob]) if n else (None, None)
    flag = "EMPTY" if n == 0 else ""
    size = (hi - lo) if n else None
    if n == 0 or max(size) > 900 or min(size) < 0.05:
        flag = flag or "SIZE"
    if flag:
        print("PART", flag, ob.name, n, None if size is None else [round(v, 1) for v in size])
print("INSPECT done", len(parts.all_parts()))
