"""List every connector / plug / port part with the point its cable would leave from.

    blender --background --python blender/tools/list_connectors.py -- arm,hand,mount,backpack
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from rj28 import model, parts  # noqa: E402
from rj28.lib.core import MM  # noqa: E402

only = set(sys.argv[sys.argv.index("--") + 1].split(",")) if "--" in sys.argv else None
model.build(only, context=False)
for ob in parts.all_parts():
    if ob.type != "MESH" or "Connector" not in ob.name:
        continue
    v = np.array([tuple(p.co) for p in ob.data.vertices]) / MM
    c = v.mean(axis=0)
    w, vec = np.linalg.eigh(np.cov((v - c).T))
    ax = vec[:, -1]
    t = (v - c) @ ax
    # the boot end is the thin end: fewer vertices far from the axis
    lo, hi = v[t.argmin()], v[t.argmax()]
    r_lo = np.linalg.norm((v[t < np.percentile(t, 15)] - c) - np.outer((v[t < np.percentile(t, 15)] - c) @ ax, ax), axis=1).max()
    r_hi = np.linalg.norm((v[t > np.percentile(t, 85)] - c) - np.outer((v[t > np.percentile(t, 85)] - c) @ ax, ax), axis=1).max()
    tail, d = (lo, -ax) if r_lo < r_hi else (hi, ax)
    print("CONN", ob.name, "tail", [round(float(x)) for x in tail], "dir", [round(float(x), 2) for x in d])
print("DONE")
