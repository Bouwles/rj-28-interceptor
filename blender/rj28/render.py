"""Review rendering: Cycles on the GPU, cameras, light rigs, contact sheets.
Positions and sizes in mm."""
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

from . import materials as M
from .lib.core import MM

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "docs" / "review"


def setup(samples=64, w=1600, h=1200, transparent=False):
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    gpu = False
    for kind in ("OPTIX", "HIP", "CUDA"):
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        prefs.get_devices()
        devs = [d for d in prefs.devices if d.type == kind]
        if devs:
            for d in prefs.devices:
                d.use = d.type == kind
            gpu = True
            break
    s.cycles.device = "GPU" if gpu else "CPU"
    s.cycles.samples = samples
    s.cycles.use_adaptive_sampling = True
    s.cycles.adaptive_threshold = 0.02
    s.cycles.use_denoising = True
    if gpu and prefs.compute_device_type == "OPTIX":
        s.cycles.denoiser = "OPTIX"
    s.render.resolution_x, s.render.resolution_y = w, h
    s.render.resolution_percentage = 100
    s.render.film_transparent = transparent
    s.view_settings.view_transform = "AgX"
    try:
        s.view_settings.look = "AgX - Base Contrast"
    except TypeError:
        pass
    return s


def camera(loc, target, lens=60.0, ortho=None, name="RJ28_Cam"):
    """Aim the review camera. ortho = orthographic width in mm (None = perspective)."""
    s = bpy.context.scene
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        s.collection.objects.link(cam)
    cam.location = Vector(loc) * MM
    d = Vector(target) * MM - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho * MM
    else:
        cam.data.type = "PERSP"
        cam.data.lens = lens
    cam.data.clip_start, cam.data.clip_end = 0.01, 200.0
    s.camera = cam
    return cam


def _area(name, loc, target, size, power, color=(1, 1, 1), size_y=None):
    L = bpy.data.lights.new(name, "AREA")
    L.energy = power
    L.color = color
    L.size = size * MM
    if size_y:
        L.shape = "RECTANGLE"
        L.size_y = size_y * MM
    ob = bpy.data.objects.new(name, L)
    ob.location = Vector(loc) * MM
    ob.rotation_euler = (Vector(target) * MM - ob.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(ob)
    return ob


def world(strength=0.02, color=(0.5, 0.5, 0.5)):
    w = bpy.data.worlds.get("RJ28_World") or bpy.data.worlds.new("RJ28_World")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*color, 1.0)
    bg.inputs["Strength"].default_value = strength
    bpy.context.scene.world = w
    return w


def clear_lights():
    for ob in [o for o in bpy.data.objects if o.type == "LIGHT" or o.name.startswith("RJ28_Floor")]:
        bpy.data.objects.remove(ob)


def floor(z=0.0, size=40000.0, base=0.012, rough=0.35):
    me = bpy.data.meshes.new("RJ28_Floor")
    h = size / 2 * MM
    me.from_pydata([(-h, -h, z * MM), (h, -h, z * MM), (h, h, z * MM), (-h, h, z * MM)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("RJ28_Floor", me)
    mat = bpy.data.materials.new("RJ28_Floor")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (base, base, base, 1)
    b.inputs["Roughness"].default_value = rough
    me.materials.append(mat)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def studio(center=(0, 0, 900), extent=2000.0, power=1.0, front=(0, -1, 0)):
    """Dark studio: big soft overhead key, two long cool rims behind left and
    right, a low warm-neutral fill. `front` is the direction the subject faces."""
    clear_lights()
    c = Vector(center)
    k = extent / 2000.0
    f = Vector(front).normalized()
    side = Vector((0, 0, 1)).cross(f).normalized()     # subject's left-hand side seen from front
    p = power * k * k

    def at(fr, sd, up):
        return c + (f * fr + side * sd + Vector((0, 0, up))) * k

    _area("Key", at(600, -300, 2600), c, 2600 * k, 180 * p)
    _area("Rim_L", at(-1900, 1700, 500), c, 320 * k, 240 * p, (0.82, 0.92, 1.0), 2800 * k)
    _area("Rim_R", at(-1900, -1700, 500), c, 320 * k, 240 * p, (0.82, 0.92, 1.0), 2800 * k)
    _area("Fill", at(2800, 900, -500), c, 1600 * k, 24 * p, (1.0, 0.96, 0.92))


def _stamp(text):
    r = bpy.context.scene.render
    r.use_stamp = bool(text)
    for a in dir(r):
        if a.startswith("use_stamp_"):
            setattr(r, a, False)
    if text:
        r.use_stamp_note = True
        r.stamp_note_text = text
        r.stamp_font_size = max(14, r.resolution_y // 55)
        r.stamp_background = (0, 0, 0, 0.55)
        r.stamp_foreground = (1, 1, 1, 1)


def render(path, mode="final", stamp=None):
    """mode: final | clay | silhouette (pure black on white)."""
    s = bpy.context.scene
    vl = bpy.context.view_layer
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    saved = (s.view_settings.view_transform, s.view_settings.look, s.world,
             s.cycles.samples, s.cycles.use_denoising)
    hidden = []
    if mode == "clay":
        vl.material_override = M.get("clay")
    elif mode == "silhouette":
        vl.material_override = M.get("silhouette")
        s.view_settings.look = "None"
        s.view_settings.view_transform = "Standard"
        s.cycles.samples, s.cycles.use_denoising = 16, False
        wd = bpy.data.worlds.get("RJ28_White") or bpy.data.worlds.new("RJ28_White")
        wd.use_nodes = True
        wd.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
        wd.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
        s.world = wd
        for ob in bpy.data.objects:
            if (ob.type == "LIGHT" or ob.name.startswith("RJ28_Floor")) and not ob.hide_render:
                ob.hide_render = True
                hidden.append(ob)
    else:
        vl.material_override = None
    _stamp(stamp)
    s.render.image_settings.file_format = "JPEG" if path.suffix.lower() in (".jpg", ".jpeg") else "PNG"
    s.render.image_settings.quality = 92
    s.render.image_settings.color_mode = "RGB"
    s.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    vl.material_override = None
    for ob in hidden:
        ob.hide_render = False
    s.view_settings.view_transform = saved[0]
    s.view_settings.look = saved[1]
    s.world = saved[2]
    s.cycles.samples, s.cycles.use_denoising = saved[3], saved[4]
    print("RENDER", path)
    return path


# ── contact sheets ───────────────────────────────────────────────────────────
def _load(path):
    img = bpy.data.images.load(str(path))
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)[::-1]


def _resize(a, nh):
    """Bilinear resize to height nh, keeping aspect."""
    h, w = a.shape[:2]
    nw = max(1, round(w * nh / h))
    ys = np.clip((np.arange(nh) + 0.5) * h / nh - 0.5, 0, h - 1)
    xs = np.clip((np.arange(nw) + 0.5) * w / nw - 0.5, 0, w - 1)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, h - 1), np.minimum(x0 + 1, w - 1)
    fy, fx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    top = a[y0][:, x0] * (1 - fx) + a[y0][:, x1] * fx
    bot = a[y1][:, x0] * (1 - fx) + a[y1][:, x1] * fx
    return top * (1 - fy) + bot * fy


def sheet(paths, out, cols=None, pad=8, bg=0.08, height=None):
    """Tile images (row-major) into one sheet. Rows may differ in height;
    height resizes every tile to that many pixels first."""
    imgs = [_load(p) for p in paths]
    if height:
        imgs = [_resize(im, height) for im in imgs]
    cols = cols or len(imgs)
    rows = [imgs[i:i + cols] for i in range(0, len(imgs), cols)]
    W = max(sum(im.shape[1] for im in r) + pad * (len(r) + 1) for r in rows)
    H = sum(max(im.shape[0] for im in r) for r in rows) + pad * (len(rows) + 1)
    canvas = np.full((H, W, 4), bg, np.float32)
    canvas[..., 3] = 1.0
    y = pad
    for r in rows:
        x = pad
        rh = max(im.shape[0] for im in r)
        for im in r:
            canvas[y:y + im.shape[0], x:x + im.shape[1], :3] = im[..., :3]
            x += im.shape[1] + pad
        y += rh + pad
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img = bpy.data.images.new("_sheet", W, H, alpha=False)
    img.pixels.foreach_set(canvas[::-1].ravel())
    img.file_format = "JPEG" if out.suffix.lower() in (".jpg", ".jpeg") else "PNG"
    img.filepath_raw = str(out)
    img.save(quality=92) if img.file_format == "JPEG" else img.save()
    bpy.data.images.remove(img)
    print("SHEET", out)
    return out
