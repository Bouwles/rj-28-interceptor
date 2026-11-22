"""Decal atlas. Every label() call registers a quad; build_atlas() packs the
distinct texts into one square texture, renders it from real text objects in
the stencil face (so it is reproducible without external rasterisers), and
points each quad's UVs at its rectangle.
"""
from pathlib import Path

import bpy

from . import materials as M
from .lib import fittings as F
from .lib.core import MM

SRGB_WHITE = (0.56, 0.56, 0.55)             # paint, not paper: bright enough to read, never the brightest thing
FLAG_RED, FLAG_GREEN = (0.36, 0.007, 0.010), (0.0, 0.17, 0.04)   # the flag's red and green, toned to paint like the white

# Cedar of the Lebanese flag, right half, in a unit box (x from the axis, y up): tiers of
# upswept boughs over a short trunk. It stands the full height of the white band.
_CEDAR = [(0.0, 1.0), (0.05, 0.93), (0.03, 0.905), (0.17, 0.80), (0.07, 0.775), (0.31, 0.61), (0.12, 0.575),
          (0.43, 0.41), (0.15, 0.365), (0.50, 0.215), (0.47, 0.155), (0.055, 0.15), (0.05, 0.0)]


def _poly(sc, pts, mat, z=0.0):
    me = bpy.data.meshes.new("_p")
    me.from_pydata([(x * MM, y * MM, z) for x, y in pts], [], [list(range(len(pts)))])
    me.materials.append(mat)
    ob = bpy.data.objects.new("_p", me)
    sc.collection.objects.link(ob)
    return ob


def _flag_lebanon(sc, x, y, w, h, mats):
    """Red, white, red in 1 : 2 : 1 with the green cedar centred on the white band, one third of the fly wide."""
    out = [_poly(sc, [(x, y + h * 0.75), (x + w, y + h * 0.75), (x + w, y + h), (x, y + h)], mats["flag_red"]),
           _poly(sc, [(x, y + h * 0.25), (x + w, y + h * 0.25), (x + w, y + h * 0.75), (x, y + h * 0.75)], mats["white"]),
           _poly(sc, [(x, y), (x + w, y), (x + w, y + h * 0.25), (x, y + h * 0.25)], mats["flag_red"])]
    cw, ch, cx, cy = w / 3, h * 0.5, x + w / 2, y + h * 0.25
    for a, b in zip(_CEDAR, _CEDAR[1:]):             # strips out from the axis: every piece is convex
        for sgn in (1, -1):
            out.append(_poly(sc, [(cx, cy + a[1] * ch), (cx + sgn * a[0] * cw, cy + a[1] * ch),
                                  (cx + sgn * b[0] * cw, cy + b[1] * ch), (cx, cy + b[1] * ch)], mats["flag_green"], 0.001))
    return out


PICTURES = {"@flag_lebanon": _flag_lebanon}


def _pack(items, side, margin):
    """Shelf-pack (w, h) rects into side x side. Returns positions or None."""
    x = y = margin
    shelf = 0.0
    pos = []
    for w, h in items:
        if x + w + margin > side:
            x, y, shelf = margin, y + shelf + margin, 0.0
        if y + h + margin > side:
            return None
        pos.append((x, y))
        x += w + margin
        shelf = max(shelf, h)
    return pos


def build_atlas(path, size=2048):
    decs = F.DECALS
    if not decs:
        return None
    uniq = {}
    for d in decs:
        uniq.setdefault((d["text"], d["color"], round(d["cap"], 3)), d)
    keys = sorted(uniq, key=lambda k: -uniq[k]["h"])
    dims = [(uniq[k]["w"], uniq[k]["h"]) for k in keys]
    side = max(max(w for w, _ in dims) + 6.0, sum(w * h for w, h in dims) ** 0.5)
    while (pos := _pack(dims, side, 2.0)) is None:
        side *= 1.06
    rects = {k: (p[0], p[1], w, h) for k, p, (w, h) in zip(keys, pos, dims)}

    main = bpy.context.scene
    sc = bpy.data.scenes.new("RJ28_Atlas")
    cam = bpy.data.objects.new("AtlasCam", bpy.data.cameras.new("AtlasCam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = side * MM
    cam.location = (side / 2 * MM, side / 2 * MM, 1.0)
    sc.collection.objects.link(cam)
    sc.camera = cam
    mats = {}
    for name, col in (("white", SRGB_WHITE), ("cyan", tuple(c * 0.62 for c in M.CYAN)), ("dark", (0.012, 0.012, 0.013)),
                      ("flag_red", FLAG_RED), ("flag_green", FLAG_GREEN)):
        m = bpy.data.materials.new("_atlas_" + name)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*col, 1.0)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        mats[name] = m
    made = []
    for k in keys:
        d = uniq[k]
        x, y, w, h = rects[k]
        if d["text"] in PICTURES:
            made += [(ob, x, y, w, h) for ob in PICTURES[d["text"]](sc, x, y, w, h, mats)]
            continue
        tw, th, cx, cy = F.text_metrics(d["text"])
        s = d["cap"] / th * MM
        cu = bpy.data.curves.new("_t", "FONT")
        cu.body = d["text"]
        cu.font = F.font()
        cu.size = s
        cu.materials.append(mats[d["color"]])
        ob = bpy.data.objects.new("_t", cu)
        ob.location = ((x + w / 2) * MM - cx * s, (y + h / 2) * MM - cy * s, 0.0)
        sc.collection.objects.link(ob)
        made.append((ob, x, y, w, h))
    sc.render.engine = "CYCLES"
    sc.cycles.device = main.cycles.device
    sc.cycles.samples = 24
    sc.cycles.use_denoising = False
    sc.cycles.filter_width = 1.2
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True, scene=sc.name)
    for ob, *_ in made:
        data = ob.data
        bpy.data.objects.remove(ob)
        (bpy.data.curves if isinstance(data, bpy.types.Curve) else bpy.data.meshes).remove(data)
    bpy.data.objects.remove(cam)
    bpy.data.scenes.remove(sc)

    img = bpy.data.images.load(str(path))
    mat = bpy.data.materials.new("RJ28_decal")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], b.inputs["Alpha"])
    b.inputs["Roughness"].default_value = 0.55
    mat["rj28_key"] = "decal"
    for d in decs:
        ob = d["obj"] if not isinstance(d["obj"], str) else bpy.data.objects.get(d["obj"])
        try:
            if ob is None or ob.name is None:
                continue
        except ReferenceError:
            continue
        x, y, w, h = rects[(d["text"], d["color"], round(d["cap"], 3))]
        ob.data.materials.clear()
        ob.data.materials.append(mat)
        uv = ob.data.uv_layers["UVMap"].data
        if not ob.get("rj28_uv_done"):
            for l in uv:
                l.uv = ((x + l.uv[0] * w) / side, (y + l.uv[1] * h) / side)
            ob["rj28_uv_done"] = True
    print("ATLAS", path, f"{len(keys)} texts, {side:.0f} mm side, {size / side:.1f} px/mm")
    return mat
