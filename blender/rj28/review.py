"""Review sheets for the detailed model: one assembly alone, or the whole robot."""
import bpy
from mathutils import Vector

from . import parts, poses, render as RD
from .lib import core as C

DIRS = {"front": (0, -1, 0), "left": (1, 0, 0), "back": (0, 1, 0), "right": (-1, 0, 0)}


def _isolate(objs):
    keep = set(o.name for o in objs)
    hidden = []
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name not in keep and not o.name.startswith("RJ28_Floor") and not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    return hidden


def _light(center, extent, mode, front):
    if mode == "clay":
        RD.studio(center, extent, power=0.42, front=front)
        RD.floor(center[2] - extent * 0.62 if center[2] > extent else 0.0, base=0.35, rough=0.7)
        RD.world(0.55, (0.62, 0.64, 0.66))
    else:
        RD.studio(center, extent, power=1.0, front=front)
        RD.floor(center[2] - extent * 0.62 if center[2] > extent else 0.0)
        RD.world(0.03)


def sheet(objs, out, title, mode="clay", views=("front", "left", "back", "right", "q"), res=(900, 1100),
          samples=48, isolate=True, q_dir=(-0.55, -0.75, 0.32), pad=1.12):
    """Orthographic views at one scale plus a three-quarter perspective, tiled."""
    lo, hi = C.bounds_mm(objs)
    c = (lo + hi) / 2
    size = hi - lo
    extent = max(size.z, size.x, size.y) * pad
    hidden = _isolate(objs) if isolate else []
    paths = []
    for v in views:
        RD.setup(samples, *res)
        if v == "q":
            d = Vector(q_dir).normalized()
            RD.camera(tuple(c + d * extent * 3.3), tuple(c), lens=80)
            front = Vector((d.x, d.y, 0)).normalized()
        elif v == "top":
            RD.camera((c.x, c.y - 1.0, c.z + 9000), tuple(c), ortho=extent * res[1] / res[0] if res[0] > res[1] else extent)
            front = Vector((0, -1, 0))
        else:
            d = Vector(DIRS[v])
            RD.camera(tuple(c + d * 9000), tuple(c), ortho=extent if res[1] >= res[0] else extent * res[0] / res[1])
            front = d
        _light(tuple(c), max(extent, 300.0), mode, front)
        paths.append(RD.render(out.parent / "wip" / f"{out.stem}_{v}.jpg", mode, f"{title}  {v}"))
    for o in hidden:
        o.hide_render = False
    return RD.sheet(paths, out, cols=len(paths))


def closeup(objs, out, title, direction, mode="clay", res=(1400, 1000), samples=64, isolate=False, lens=85, dist=3.0,
            target=None):
    """One perspective close-up of a group of parts from a given direction."""
    lo, hi = C.bounds_mm(objs)
    c = Vector(target) if target is not None else (lo + hi) / 2
    extent = max(hi - lo) * 1.15
    hidden = _isolate(objs) if isolate else []
    d = Vector(direction).normalized()
    RD.setup(samples, *res)
    RD.camera(tuple(c + d * extent * dist), tuple(c), lens=lens)
    _light(tuple(c), max(extent, 300.0), mode, Vector((d.x, d.y, 0)).normalized() if abs(d.z) < 0.99 else Vector((0, -1, 0)))
    p = RD.render(out, mode, title)
    for o in hidden:
        o.hide_render = False
    return p


def robot(out_dir, tag="", mode="clay", samples=48):
    """Whole-robot turnaround, both mount states."""
    everything = [o for o in bpy.data.objects if o.type == "MESH" and not o.name.startswith("RJ28_Floor")]
    sheets = []
    for state in ("stowed", "deployed"):
        poses.set_mount(state)
        paths = []
        for v, d in DIRS.items():
            RD.setup(samples, 860, 1480)
            RD.camera((d[0] * 9000, d[1] * 9000, 1140), (0, 0, 1140), ortho=2380.0)
            _light((0, 0, 1000), 2200.0, mode, Vector(d))
            paths.append(RD.render(out_dir / "wip" / f"robot_{mode}_{state}_{v}{tag}.jpg", mode, f"{v.upper()}  {state}"))
        sheets.append(RD.sheet(paths, out_dir / f"robot_{mode}_{state}{tag}.jpg"))
    return sheets


def assembly_objects(*aas):
    return [o for o in parts.all_parts() if o.get("rj28_assembly") in aas and o.type == "MESH"]
