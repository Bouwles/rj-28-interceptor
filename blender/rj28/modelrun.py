"""Command-line driver for the detailed model (see build.py)."""
import importlib
import json

import bpy

from . import model, parts, poses, render as RD, review


def run(opts):
    arg = {o.split("=")[0]: o.split("=")[1] for o in opts if "=" in o}
    only = set(arg["only"].split(",")) if "only" in arg else None
    built = model.build(only, context="noctx" not in opts)
    out = RD.REVIEW / arg.get("phase", "phase3")
    tag = arg.get("tag", "")
    if "sweep" in opts:
        res = poses.sweep_check(report=RD.ROOT / "blender" / "out" / "mount_sweep_model.json")
        print("SWEEP", "PASS" if res["passed"] else "FAIL", res["min_clearance_mm"])
        for z in res["zones"][:8]:
            print("  ", z)
    if "save" in opts:
        bpy.ops.wm.save_as_mainfile(filepath=str(RD.ROOT / "blender" / "out" / f"model{tag}.blend"))
    if "sheets" in opts:
        for aa, a in built.items():
            objs = [o for o in a.parts if o.type == "MESH"]
            if not objs:
                continue
            name = a.title.replace(", ", "_").replace(" ", "_").lower()
            review.sheet(objs, out / f"{aa}_{name}_clay{tag}.jpg", f"{aa} {a.title}")
    # assembly modules may define review(asm, out) for their own close-ups
    if "close" in opts:
        for (m, s, aa, _z) in model.PLAN:
            if aa in built:
                mod = importlib.import_module(f"rj28.assemblies.{m}")
                if hasattr(mod, "review"):
                    mod.review(built[aa], out, tag)
    if "robot" in opts:
        review.robot(out, tag, arg.get("mode", "clay"))
    counts = {aa: len(a.parts) for aa, a in built.items()}
    print("COUNTS", json.dumps(counts), "TOTAL", len(parts.all_parts()))
