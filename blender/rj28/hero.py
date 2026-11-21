"""Hero studio, cameras and offline renders (Phase 7).

A dark studio: one large soft overhead key, two long cool rims behind left and
right (they draw the black silhouette), a low warm-neutral fill, a dark floor
with a soft reflection. Light is neutral to cool white; cyan comes only from
the robot. The same rig is rendered as an equirectangular panorama and used
as the site's HDRI, so the web model and these renders match.
"""
from pathlib import Path

import bpy
from mathutils import Vector

from . import explode, poses, render as RD
from .lib.core import MM

ROOT = Path(__file__).resolve().parents[2]
RENDERS = ROOT / "site" / "public" / "renders"

# name -> mount state, camera position, target (mm), lens, resolution, exposure, exploded amount
SHOTS = {
    "front_deployed": dict(state="deployed", loc=(2250, -3800, 1150), target=(-20, -80, 1005), lens=75,
                           res=(3840, 4800)),
    "rear_stowed": dict(state="stowed", loc=(-2550, 3650, 1520), target=(-40, 70, 1085), lens=75, res=(3840, 5120)),
    "head_cap": dict(state="deployed", loc=(-470, -980, 1705), target=(-10, -50, 1640), lens=105, res=(3840, 2880)),
    "mount": dict(state="deployed", loc=(-1180, 880, 1790), target=(-300, 110, 1570), lens=90, res=(3840, 2880)),
    "knee": dict(state="stowed", loc=(1150, 840, 640), target=(176, 30, 505), lens=105, res=(3840, 2880)),
    "exploded": dict(state="stowed", loc=(-5200, -7400, 2500), target=(0, 0, 900), lens=85, res=(3840, 3840),
                     explode=1.0, extent=3800.0),
    "social_card": dict(state="deployed", loc=(-2700, -3600, 1250), target=(-520, -80, 1120), lens=70, res=(3840, 2016)),
}


def _area(name, loc, target, size, power, color=(1, 1, 1), size_y=None, spread=180.0):
    import math
    L = bpy.data.lights.new(name, "AREA")
    L.energy = power
    L.color = color
    L.size = size * MM
    if size_y:
        L.shape = "RECTANGLE"
        L.size_y = size_y * MM
    L.spread = math.radians(spread)
    ob = bpy.data.objects.new(name, L)
    ob.location = Vector(loc) * MM
    ob.rotation_euler = (Vector(target) * MM - ob.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(ob)
    return ob


def studio(extent=2000.0, gain=1.0):
    """Build the hero light rig around a subject standing at the origin."""
    RD.clear_lights()
    for ob in [o for o in bpy.data.objects if o.name.startswith("RJ28_Floor")]:
        bpy.data.objects.remove(ob)
    k = extent / 2000.0
    p = gain * k * k
    c = Vector((0, 0, 1050)) * k
    _area("Hero_Key", Vector((250, -700, 3700)) * k, c, 3200 * k, 170 * p, (1.0, 0.99, 0.97), spread=140)
    rims = [_area(name, Vector((sx * 2300, 2100, 1550)) * k, c + Vector((0, 0, 100)) * k, 380 * k, 95 * p,
                  (0.80, 0.90, 1.0), 2700 * k, spread=100) for name, sx in (("Hero_Rim_L", 1), ("Hero_Rim_R", -1))]
    rims.append(_area("Hero_Fill", Vector((900, -3300, 450)) * k, c, 2200 * k, 18 * p, (1.0, 0.95, 0.90), 1300 * k,
                      spread=150))
    RD.world(0.012, (0.5, 0.55, 0.6))
    fl = RD.floor(0.0, base=0.008, rough=0.5)
    # the rims draw the silhouette and the fill opens the shadows; only the key lights the floor (light linking)
    block = bpy.data.collections.get("RJ28_RimBlock") or bpy.data.collections.new("RJ28_RimBlock")
    for ob in list(block.objects):
        block.objects.unlink(ob)
    block.objects.link(fl)
    for entry in block.collection_objects:
        entry.light_linking.link_state = "EXCLUDE"
    for r in rims:
        r.light_linking.receiver_collection = block
    return fl


def setup(res, samples=256, scale=1.0):
    s = RD.setup(samples, int(res[0] * scale), int(res[1] * scale))
    s.cycles.adaptive_threshold = 0.01
    s.view_settings.view_transform = "AgX"
    try:
        s.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    s.view_settings.exposure = 0.0
    return s


def render(name, scale=1.0, samples=256, out=None, tag=""):
    """Render one hero shot. scale < 1 gives a quick proof."""
    shot = SHOTS[name]
    poses.set_mount(shot["state"])
    amount = shot.get("explode", 0.0)
    if amount:
        explode.apply()
        explode.pose(amount)
    studio(shot.get("extent", 2000.0))
    setup(shot["res"], samples, scale)
    cam = RD.camera(shot["loc"], shot["target"], shot["lens"])
    cam.data.dof.use_dof = False
    path = (out or RENDERS) / f"{name}{tag}.jpg"
    RD.render(path, "final")
    if amount:
        explode.pose(0.0)
    return path


def hdri(path=None, width=2048):
    """Render the empty studio as an equirectangular panorama (Radiance .hdr)."""
    path = Path(path) if path else ROOT / "site" / "public" / "hdri" / "studio.hdr"
    path.parent.mkdir(parents=True, exist_ok=True)
    studio()
    hidden = []
    for ob in bpy.data.objects:
        if ob.type == "MESH" and not ob.name.startswith("RJ28_Floor") and not ob.hide_render:
            ob.hide_render = True
            hidden.append(ob)
    s = RD.setup(128, width, width // 2)
    cam = RD.camera((0, 0, 1150), (0, -1000, 1150), 50, name="RJ28_Pano")
    cam.data.type = "PANO"
    cam.data.panorama_type = "EQUIRECTANGULAR"
    s.render.image_settings.file_format = "HDR"
    s.render.image_settings.color_mode = "RGB"
    s.view_settings.view_transform = "Standard"
    s.view_settings.look = "None"
    s.render.use_stamp = False
    s.render.filepath = str(path)
    bpy.context.view_layer.material_override = None
    bpy.ops.render.render(write_still=True)
    for ob in hidden:
        ob.hide_render = False
    bpy.data.objects.remove(cam)
    s.camera = bpy.data.objects.get("RJ28_Cam")
    print("HDRI", path)
    return path
