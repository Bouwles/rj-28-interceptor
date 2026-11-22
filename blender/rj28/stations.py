"""Scroll-tour camera stations.

Ten stations, authored here in millimetres and robot axes (Z up, robot faces
-Y, robot's left is +X) and checked in real renders before the site ever sees
them. write() converts them to glTF axes and metres for the site.

    loc, target      camera position and aim point
    loc2, target2    where the camera ends up if it moves during the section
    move             how to get there: "orbit" turns about the vertical through
                     the target (radius and height interpolated), "dolly" is a
                     straight line
    lens             focal length in mm on a 36 mm wide sensor
    mount            cannon state for the section; mount_to if it changes
    focus            (assembly, short part name) or an assembly number
    highlight        assemblies kept lit while the rest dims; empty = everything
    xray             armour of the highlighted assemblies fades
"""
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

from . import hero, parts, poses, render as RD
from .lib.core import MM

ROOT = Path(__file__).resolve().parents[2]
PROOFS = ROOT / "docs" / "review" / "phase8"
DATA = ROOT / "site" / "src" / "data"
SENSOR = 36.0
PROOF_RES = (960, 540)

STATIONS = [
    dict(id="00", section="Title", title="RJ-28 INTERCEPTOR",
         loc=(2900, -5900, 420), target=(-30, 0, 1010), lens=55, mount="stowed",
         focus="03", highlight=[]),
    dict(id="01", section="Overview", title="General arrangement",
         loc=(3500, -5600, 1350), target=(-30, 20, 1010), loc2=(-5100, -4200, 1350), target2=(-30, 20, 1010),
         move="orbit", lens=55, mount="stowed", focus="03", highlight=[]),
    dict(id="02", section="Head and cap", title="Sensor head and cap",
         loc=(520, -1010, 1700), target=(0, -45, 1638), loc2=(640, 960, 1790), target2=(0, 20, 1650),
         move="orbit", lens=85, mount="stowed", gain=0.6, focus="01", highlight=["01"]),
    dict(id="03", section="Thorax", title="Power, compute and cooling",
         loc=(330, -2500, 1465), target=(0, -40, 1370), lens=70, mount="stowed",
         focus=("03", "Battery_Enclosure"), highlight=["03"], xray=True),
    dict(id="04", section="Arms and hands", title="Arms and hands",
         loc=(2655, -2615, 1190), target=(345, -40, 1095), loc2=(1110, -940, 790), target2=(385, -70, 745),
         move="dolly", lens=70, mount="stowed", focus="07", highlight=["07", "09"]),
    dict(id="05", section="Legs", title="Knee and ankle drive",
         loc=(2560, 760, 400), target=(190, 30, 300), lens=68, mount="stowed", gain=1.4,
         focus=("11", "Knee_Shaft"), highlight=["11", "13"]),
    dict(id="06", section="Interceptor cannon", title="Interceptor mount",
         loc=(-2650, 2250, 2050), target=(-240, -20, 1640), loc2=(-2950, 1500, 1900), target2=(-240, -60, 1600),
         move="orbit", lens=66, mount="stowed", mount_to="deployed", focus="15", highlight=["15"]),
    dict(id="07", section="Armour and materials", title="Armour and materials",
         loc=(2600, -2600, 200), target=(200, -40, 775), lens=47, mount="deployed", gain=1.15,
         focus=("11", "Shin_Armour_Front"), highlight=[]),
    dict(id="08", section="Drawings", title="Drawings",
         loc=(0, -18000, 1025), target=(0, 0, 1025), lens=150, mount="stowed", focus="03", highlight=[]),
    dict(id="09", section="Inspect", title="Inspector",
         loc=(3400, -6600, 1500), target=(0, 20, 1000), lens=55, mount="stowed", focus="03", highlight=[]),
]


def _gl(v):
    """mm, robot axes -> metres, glTF axes (+Y up, robot faces +Z)."""
    return [round(v[0] * MM, 4), round(v[2] * MM, 4), round(-v[1] * MM, 4)]


def _focus(f):
    if isinstance(f, str):
        assert f in parts.ASSEMBLIES, f
        return f
    aa, short = f
    for ob in parts.all_parts():
        if ob["rj28_assembly"] == aa and ob.name.split("_", 1)[1] == short:
            return ob.name
    raise KeyError(f"station focus {aa} {short} is not a part of the model")


def rows():
    out = []
    for st in STATIONS:
        r = dict(id=st["id"], section=st["section"], title=st["title"], position=_gl(st["loc"]),
                 target=_gl(st["target"]), lens_mm=st["lens"], sensor_mm=SENSOR, mount=st["mount"],
                 focus=_focus(st["focus"]), highlight=list(st["highlight"]), xray=bool(st.get("xray", False)))
        if "loc2" in st:
            r["position2"] = _gl(st["loc2"])
            r["target2"] = _gl(st["target2"])
            r["move"] = st["move"]
        if "mount_to" in st:
            r["mount_from"] = st["mount"]
            r["mount_to"] = st["mount_to"]
        out.append(r)
    return out


def write():
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "stations.json").write_text(json.dumps(rows(), indent=1) + "\n", encoding="utf-8", newline="\n")
    print("STATIONS", DATA / "stations.json", len(STATIONS))


def midpoint(st):
    """Camera halfway through a moving section, by the rule in `move`."""
    a, b = Vector(st["loc"]), Vector(st["loc2"])
    ta, tb = Vector(st["target"]), Vector(st["target2"])
    t = (ta + tb) / 2
    if st["move"] != "orbit":
        return tuple((a + b) / 2), tuple(t)
    ra, rb = a - ta, b - tb
    aa, ab = math.atan2(ra.y, ra.x), math.atan2(rb.y, rb.x)
    d = (ab - aa + math.pi) % (2 * math.pi) - math.pi
    if "orbit_dir" in st and d * st["orbit_dir"] < 0:
        d += 2 * math.pi * st["orbit_dir"]
    ang = aa + d / 2
    rad = (ra.xy.length + rb.xy.length) / 2
    return (t.x + rad * math.cos(ang), t.y + rad * math.sin(ang), t.z + (ra.z + rb.z) / 2), tuple(t)


def _xray(st, on):
    """Proof of the x-ray stations: armour of the highlighted assemblies out of the picture."""
    from . import measure
    for ob in parts.all_parts():
        host = bpy.data.objects.get(ob.get("rj28_host", ""))
        ref = host or ob
        if ref["rj28_assembly"] in st["highlight"] and measure.part_class(ref) == "armour":
            ob.hide_render = on


def _shot(st, loc, target, state, path, elev=None):
    poses.set_mount(state, elev=elev)
    hero.studio(2000.0, st.get("gain", 1.0), loc)
    hero.setup(PROOF_RES, 48, 1.0)
    cam = RD.camera(loc, target, st["lens"])
    cam.data.sensor_width = SENSOR
    cam.data.dof.use_dof = False
    RD.render(path, "final")


def render(only=None):
    """Low-resolution proofs: every station, plus the middle and the end of the ones that move."""
    made = []
    for st in STATIONS:
        if only and st["id"] not in only:
            continue
        if st.get("xray"):
            _xray(st, True)
        end = st.get("mount_to", st["mount"])
        made.append(PROOFS / f"station_{st['id']}.jpg")
        _shot(st, st["loc"], st["target"], st["mount"], made[-1])
        if "loc2" in st:
            mid = midpoint(st)
            half = (poses.STATES[st["mount"]][0] + poses.STATES[end][0]) / 2
            made.append(PROOFS / f"station_{st['id']}_mid.jpg")
            _shot(st, mid[0], mid[1], st["mount"], made[-1], elev=half)
            made.append(PROOFS / f"station_{st['id']}_end.jpg")
            _shot(st, st["loc2"], st["target2"], end, made[-1])
        elif end != st["mount"]:
            made.append(PROOFS / f"station_{st['id']}_end.jpg")
            _shot(st, st["loc"], st["target"], end, made[-1])
        if st.get("xray"):
            _xray(st, False)
    poses.set_mount("stowed")
    return made
