"""Command-line driver for the detailed model (see build.py).

Options: only=a,b  noctx  sheets  close  robot  sweep  save  axes  explode  measure
         phase=<review folder>  tag=<suffix>  mode=clay|final
"""
import importlib
import json

import bpy
from mathutils import Vector

from . import model, parts, poses, render as RD, review


def run(opts):
    arg = {o.split("=")[0]: o.split("=")[1] for o in opts if "=" in o}
    only = set(arg["only"].split(",")) if "only" in arg else None
    built = model.build(only, context="noctx" not in opts)
    out = RD.REVIEW / arg.get("phase", "phase3")
    tag = arg.get("tag", "")
    if "axes" in opts:
        from . import axes
        print("AXES", len(axes.build()))
    if "sweep" in opts:
        res = poses.sweep_check(report=RD.ROOT / "blender" / "out" / "mount_sweep_model.json")
        print("SWEEP", "PASS" if res["passed"] else "FAIL", res["min_clearance_mm"])
        for z in res["zones"][:8]:
            print("  ", z)
    if "sheets" in opts:
        for aa, a in built.items():
            objs = [o for o in a.parts if o.type == "MESH"]
            if not objs:
                continue
            name = a.title.replace(", ", "_").replace(" ", "_").lower()
            review.sheet(objs, out / f"{aa}_{name}_clay{tag}.jpg", f"{aa} {a.title}")
    # assembly modules may define review(asm, out, tag) for their own close-ups
    if "close" in opts:
        for (m, s, aa, _z) in model.PLAN:
            if aa in built:
                mod = importlib.import_module(f"rj28.assemblies.{m}")
                if hasattr(mod, "review"):
                    mod.review(built[aa], out, tag)
    if "robot" in opts:
        review.robot(out, tag, arg.get("mode", "clay"))
    if "explode" in opts or "measure" in opts:
        from . import explode
        explode.apply()
    if "measure" in opts:
        from . import measure
        spec, rows = measure.run(write="write" in opts)
        m = spec["mass"]
        print("MASS", m["total_kg"], "kg", m["error_pct"], "%", json.dumps(m["by_class"]))
        print("MASS_ASM", json.dumps({a["assembly"]: a["mass_kg"] for a in m["by_assembly"]}))
        print("FILL", json.dumps(m["fill_factors"]))
        print("ENVELOPE", json.dumps(spec["envelope"]), "crown", spec["height_to_cap_crown"], "span",
              spec["shoulder_armour_span"])
        for n in spec["design_notes"]:
            print("NOTE", n["title"])
            for w in n["working"]:
                print("   ", w)
    if "explode" in opts:
        from . import explode
        everything = [o for o in bpy.data.objects if o.type == "MESH" and "rj28_number" in o]
        for amt, name in ((0.5, "stage1"), (1.0, "full")):
            explode.pose(amt)
            for v, d in (("front", (0, -1, 0)), ("q", (-0.55, -0.75, 0.3))):
                RD.setup(48, 1500, 1500)
                dv = Vector(d).normalized()
                if v == "front":
                    RD.camera((0, -12000, 950), (0, 0, 950), ortho=3600.0)
                else:
                    RD.camera(tuple(Vector((0, 0, 950)) + dv * 11000), (0, 0, 950), lens=85)
                RD.studio((0, 0, 1000), 3400.0, power=0.42, front=Vector((dv.x, dv.y, 0)).normalized())
                RD.floor(-900.0, base=0.35, rough=0.7)
                RD.world(0.55, (0.62, 0.64, 0.66))
                RD.render(out / f"explode_{name}_{v}{tag}.jpg", arg.get("mode", "clay"), f"exploded {name} {v}")
        explode.pose(0.0)
    if "save" in opts:
        bpy.ops.wm.save_as_mainfile(filepath=str(RD.ROOT / "blender" / "out" / f"model{tag}.blend"))
    counts = {aa: len(a.parts) for aa, a in built.items()}
    print("COUNTS", json.dumps(counts), "TOTAL", len(parts.all_parts()))
