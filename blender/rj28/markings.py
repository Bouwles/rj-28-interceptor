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

SRGB_WHITE = (0.82, 0.82, 0.82)


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
    for name, col in (("white", SRGB_WHITE), ("cyan", M.CYAN)):
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
        cu = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
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
        ob = bpy.data.objects.get(d["obj"])
        if ob is None:
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
