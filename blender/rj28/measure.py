"""Measure the finished model and write the data the site shows.

    spec.json      overall dimensions (both mount states), landmark heights, joints, design notes
    parts.json     every part: number, name, assembly, material, function, box, volume, mass
    stations.json  scroll-tour camera stations (written by render.py when the cameras are authored)

Nothing on the site is typed by hand: if it is a number, it comes from here.

Mass. A part's mass is its closed-mesh volume x material density x a fill
factor for its material class. Fill factors stand for what the solid mesh
leaves out (bores, cable ducts, honeycomb, air in an enclosure) and for what
it leaves in (cells in the battery, copper in a motor). They are set per class,
never per part, then scaled together so the roll-up meets the ready mass.
"""
import json
import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

from . import axes, frames as FR, materials as M, params as PR, parts, poses
from .lib import core as C
from .lib.core import MM

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "site" / "src" / "data"

# class -> starting fill factor (before the common scale)
FILL = {
    "armour": 0.90,       # solid laminate with ceramic face
    "structure": 0.55,    # machined frames: modelled solid, really pocketed and bored
    "mechanism": 0.70,    # steel parts: hollow shafts, bores
    "actuator": 0.60,     # housings modelled solid: stator, rotor, gears and air inside
    "soft": 0.80,         # rubber, mesh
    "harness": 0.55,      # copper + insulation + air in the braid
    "optic": 0.60,
    "battery": 1.00,      # enclosure volume x cell-pack density
    "electronics": 0.35,
}
DENSITY_OVERRIDE = {"battery": 2700.0, "electronics": 1900.0, "actuator": 4300.0}


def volume_m3(ob):
    me = C.evaluated_mesh(ob)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    v = abs(bm.calc_volume(signed=True))
    bm.free()
    bpy.data.meshes.remove(me)
    return v


def part_class(ob):
    """Material class used for the mass roll-up; a part can override it with rj28_class."""
    if "rj28_class" in ob:
        return ob["rj28_class"]
    key = ob.get("rj28_material", "")
    name = ob.name
    if "Battery_Enclosure" in name:
        return "battery"
    if any(k in name for k in ("Compute_Module", "Processor_Board", "Power_Distribution", "Controller", "Lidar_Unit",
                               "Imager_Core", "Camera")):
        return "electronics"
    if any(k in name for k in ("Housing", "Motor", "Act_Body", "Drive")) and key in ("alu", "ti"):
        return "actuator"
    return M.INFO.get(key, ("", "structure", 2700))[1]


def part_rows():
    rows = []
    for ob in parts.all_parts():
        if ob.type != "MESH" or len(ob.data.vertices) == 0:
            continue
        key = ob.get("rj28_material", "")
        cls = part_class(ob)
        dens = DENSITY_OVERRIDE.get(cls, M.INFO.get(key, ("", "", 2700.0))[2])
        lo, hi = C.bounds_mm([ob])
        decal = bool(ob.get("rj28_decal"))
        rows.append(dict(
            number=ob["rj28_number"], name=ob["rj28_name"], node=ob.name, assembly=ob["rj28_assembly"],
            assembly_name=parts.ASSEMBLIES[ob["rj28_assembly"]], material=M.INFO.get(key, (key,))[0], material_key=key,
            material_class=cls, function=ob["rj28_function"],
            bbox_min=[round(v, 1) for v in lo], bbox_max=[round(v, 1) for v in hi],
            size=[round(v, 1) for v in (hi - lo)],
            volume_cm3=0.0 if decal else round(volume_m3(ob) * 1e6, 2), density=dens,
            count=int(ob.get("rj28_count", 1)), mount_group=ob.get("mount_group", ""),
            explode_stage=int(ob.get("explode_stage", 2)),
            explode_offset=[round(v, 4) for v in ob.get("explode_offset", (0, 0, 0))],
        ))
    return rows


def roll_up(rows, target=PR.MASS_READY_KG):
    """Assign masses. Battery parts are pinned to the pack target; every other
    class shares one scale factor so the total lands on the ready mass."""
    raw = {}
    for r in rows:
        r["_m0"] = r["volume_cm3"] * 1e-6 * r["density"] * FILL.get(r["material_class"], 0.6)
        raw[r["material_class"]] = raw.get(r["material_class"], 0.0) + r["_m0"]
    batt = raw.get("battery", 0.0)
    k_b = PR.MASS_BATTERY_KG / batt if batt > 0 else 1.0
    rest = sum(v for c, v in raw.items() if c != "battery")
    k = (target - (PR.MASS_BATTERY_KG if batt > 0 else 0.0)) / rest if rest > 0 else 1.0
    factors = {c: round(FILL.get(c, 0.6) * (k_b if c == "battery" else k), 4) for c in raw}
    for r in rows:
        r["mass_kg"] = round(r.pop("_m0") * (k_b if r["material_class"] == "battery" else k), 3)
    by_asm = {}
    for r in rows:
        a = by_asm.setdefault(r["assembly"], dict(assembly=r["assembly"], name=r["assembly_name"], parts=0, mass_kg=0.0))
        a["parts"] += 1
        a["mass_kg"] += r["mass_kg"]
    for a in by_asm.values():
        a["mass_kg"] = round(a["mass_kg"], 2)
    total = round(sum(r["mass_kg"] for r in rows), 2)
    return dict(total_kg=total, target_kg=target, error_pct=round((total - target) / target * 100, 2),
                fill_factors=factors, common_scale=round(k, 4), by_assembly=[by_asm[k_] for k_ in sorted(by_asm)],
                by_class={c: round(sum(r["mass_kg"] for r in rows if r["material_class"] == c), 2) for c in raw})


def envelope(objs):
    lo, hi = C.bounds_mm(objs)
    return dict(min=[round(v, 1) for v in lo], max=[round(v, 1) for v in hi],
                width=round(hi.x - lo.x, 1), depth=round(hi.y - lo.y, 1), height=round(hi.z, 1))


def knee_note():
    """Design note 1: static knee torque in a 90 degree squat, and the actuator force it implies."""
    from mathutils import Matrix
    from .assemblies import leg as LEG
    hip, thigh, knee, shin, ankle, foot = FR.leg(1)

    def arm_at(flex):
        """Lever arm (mm) of one actuator about the knee axis at a given flexion, from the modelled pivots."""
        p0 = thigh @ Vector(LEG.KNEE_P0)
        p1 = knee @ Matrix.Rotation(math.radians(flex), 4, "X") @ Vector(LEG.KNEE_P1)
        k = knee.translation
        ax = (knee.to_3x3() @ Vector((1, 0, 0))).normalized()
        d = (p1 - p0).normalized()
        v = (k - p0) - d * (k - p0).dot(d)
        return (v - ax * v.dot(ax)).length, (p1 - p0).length

    arm_mm, len_squat = arm_at(90.0)
    arms = {int(f): round(arm_at(f)[0], 1) for f in (0, 30, 55, 90, PR.KNEE_RANGE)}
    stroke = arm_at(0.0)[1] - arm_at(PR.KNEE_RANGE)[1]
    g = 9.81
    m_above = PR.MASS_READY_KG - 2 * 11.0            # everything above the knees: total less shins and feet
    shin_len = PR.SHIN / 1000.0
    # 90 degree squat: shins lean 35 degrees forward and the mass above the knees sits over mid-foot,
    # 50 mm ahead of the ankles. The knees are then this far ahead of the weight line:
    lever = shin_len * math.sin(math.radians(35)) - 0.05
    torque_total = m_above * g * lever
    torque_knee = torque_total / 2
    force_total = torque_knee / (arm_mm / 1000.0)
    return dict(
        title="Static knee torque in a 90 degree squat",
        inputs=dict(ready_mass_kg=PR.MASS_READY_KG, mass_above_knees_kg=round(m_above, 1),
                    shin_length_mm=round(PR.SHIN, 1), lever_mm=round(lever * 1000, 0),
                    crank_radius_mm=PR.KNEE_CRANK, knee_range_deg=PR.KNEE_RANGE,
                    actuator_moment_arm_mm=round(arm_mm, 1), moment_arm_by_flexion_mm=arms,
                    actuator_stroke_mm=round(stroke, 1), actuators_per_knee=2),
        working=[
            f"Weight above the knees: {m_above:.0f} kg x 9.81 = {m_above * g:.0f} N",
            f"Lever from knee axis to the weight line: {lever * 1000:.0f} mm",
            f"Torque, both knees: {m_above * g:.0f} N x {lever:.3f} m = {torque_total:.0f} N m",
            f"Per knee: {torque_knee:.0f} N m",
            f"Actuator moment arm at 90 degrees flexion (from the modelled pivots): {arm_mm:.0f} mm",
            f"Moment arm across the range: " + ", ".join(f"{a_} mm at {f}" for f, a_ in arms.items()) + " degrees",
            f"Actuator stroke for 0 to {PR.KNEE_RANGE:.0f} degrees: {stroke:.0f} mm",
            f"Force per knee: {torque_knee:.0f} / {arm_mm / 1000:.3f} = {force_total / 1000:.1f} kN, "
            f"{force_total / 2000:.1f} kN per actuator",
        ],
        result=dict(torque_per_knee_nm=round(torque_knee, 0), force_per_actuator_kn=round(force_total / 2000, 1)),
        verdict="Static load is a small fraction of what a 30 mm planetary roller screw carries (about 12 kN "
                "continuous). The margin is for dynamics: a landing or a single-leg push-off multiplies this several "
                "times for a fraction of a second.",
    )


def endurance_note():
    h = PR.PACK_KWH / PR.AVG_DRAW_KW
    usable = 0.9
    enc = [o for o in parts.all_parts() if "Battery_Enclosure" in o.name]
    vol_l = volume_m3(enc[0]) * 1000.0 if enc else float("nan")
    return dict(
        title="Endurance from pack energy and average draw",
        inputs=dict(pack_kwh=PR.PACK_KWH, average_draw_kw=PR.AVG_DRAW_KW, usable_fraction=usable,
                    pack_mass_kg=PR.MASS_BATTERY_KG),
        working=[
            f"Pack energy: {PR.PACK_KWH:.1f} kWh at {PR.PACK_VOLTAGE:.0f} V nominal = {PR.PACK_KWH * 1000 / PR.PACK_VOLTAGE:.0f} Ah",
            f"Mixed-duty average draw: {PR.AVG_DRAW_KW:.1f} kW",
            f"Endurance to empty: {PR.PACK_KWH:.1f} / {PR.AVG_DRAW_KW:.1f} = {h:.1f} h",
            f"Endurance to the {int((1 - usable) * 100)}% reserve: {h * usable:.2f} h",
            f"Pack specific energy: {PR.PACK_KWH * 1000 / PR.MASS_BATTERY_KG:.0f} Wh/kg at pack level",
            f"Enclosure volume from the model: {vol_l:.1f} L, so {PR.PACK_KWH * 1000 / vol_l:.0f} Wh/L "
            f"and {PR.MASS_BATTERY_KG / vol_l:.2f} kg/L at pack level",
        ],
        result=dict(endurance_h=round(h, 2), endurance_to_reserve_h=round(h * usable, 2),
                    pack_wh_per_kg=round(PR.PACK_KWH * 1000 / PR.MASS_BATTERY_KG, 0)),
        verdict="2.5 h holds only if the pack is run to empty; the dossier quotes 2.5 h mixed duty and 2.25 h to reserve. "
                "The volumetric figure needs silicon-anode cells (about 1,100 Wh/L at the cell) stacked cell-to-pack; "
                f"with ordinary NMC cells at 430 Wh/L pack level this enclosure would hold about {vol_l * 0.43:.1f} kWh.",
    )


def run(write=True):
    """Measure the model in the current scene."""
    everything = [o for o in parts.all_parts() if o.type == "MESH" and len(o.data.vertices)]
    body = [o for o in everything if o["rj28_assembly"] not in ("15", "16", "17")]
    spec = dict(designation="RJ-28 INTERCEPTOR", klass="Autonomous humanoid interceptor, Mark 1 prototype",
                serial=PR.SERIAL)
    states = {}
    for state in ("deployed", "stowed"):
        poses.set_mount(state)
        states[state] = envelope(everything)
    spec["envelope"] = states
    spec["body"] = envelope(body)
    cap = [o for o in everything if o.get("zone") == "cap"]
    spec["height_to_cap_crown"] = envelope(cap)["height"] if cap else None
    pauld = [o for o in everything if str(o.get("zone", "")).startswith("pauldron")]
    spec["shoulder_armour_span"] = envelope(pauld)["width"] if pauld else None
    js = axes.joints()
    lm = {j["name"]: j["origin"] for j in js}
    spec["landmarks"] = dict(
        ankle_axis=round(lm["ankle_pitch_L"].z, 1), knee_axis=round(lm["knee_pitch_L"].z, 1),
        hip_axis=round(lm["hip_pitch_L"].z, 1), waist_joint=round(lm["waist_yaw"].z, 1),
        shoulder_axis=round(lm["shoulder_pitch_L"].z, 1), neck_ring=round(lm["neck_yaw"].z, 1),
        sensor_slit=PR.Z_SLIT,
        shoulder_axis_span=round(abs(lm["shoulder_pitch_L"].x - lm["shoulder_pitch_R"].x), 1),
        hip_axis_span=round(abs(lm["hip_pitch_L"].x - lm["hip_pitch_R"].x), 1),
        stance_width=round(abs(lm["ankle_pitch_L"].x - lm["ankle_pitch_R"].x), 1))
    spec["joints"] = [dict(name=j["name"], group=j["group"], origin=[round(v, 1) for v in j["origin"]],
                           axis=[round(v, 4) for v in j["axis"]], range=list(j["range"]), drive=j["drive"])
                      for j in js]
    spec["dof"] = dict(PR.DOF, total=sum(PR.DOF.values()))
    spec["mount"] = dict(barrel_od=PR.BARREL_OD, barrel_length=PR.BARREL_L, elevation=[PR.ELEV_MIN, PR.ELEV_MAX],
                         traverse=PR.TRAVERSE, trunnion=[PR.BORE_X, PR.TRUNNION_Y, PR.TRUNNION_Z],
                         bore_rise=PR.BORE_RISE)
    spec["targets"] = dict(power=f"{PR.PACK_VOLTAGE:.0f} V nominal lithium-ion pack, {PR.PACK_KWH:.1f} kWh, liquid cooled",
                           pack_voltage=PR.PACK_VOLTAGE, pack_kwh=PR.PACK_KWH, average_draw_kw=PR.AVG_DRAW_KW,
                           walk_kmh=5, run_kmh=11, sealing="IP65", mass_ready_kg=PR.MASS_READY_KG)
    rows = part_rows()
    mass = roll_up(rows)
    spec["mass"] = mass
    spec["part_count"] = len(rows)
    spec["design_notes"] = [knee_note(), endurance_note(), dict(
        title="Mass roll-up from part volumes",
        working=[f"{len(rows)} parts; mass = mesh volume x material density x class fill factor",
                 "Battery parts pinned to the pack target; all other classes share one scale factor",
                 f"Roll-up: {mass['total_kg']:.1f} kg against {mass['target_kg']:.0f} kg ({mass['error_pct']:+.2f}%)"],
        result=dict(total_kg=mass["total_kg"], common_scale=mass["common_scale"]),
        verdict="Fill factors are listed with the mass data; none is set per part.")]
    if write:
        DATA.mkdir(parents=True, exist_ok=True)
        (DATA / "spec.json").write_text(json.dumps(spec, indent=1))
        (DATA / "parts.json").write_text(json.dumps(rows, indent=1))
    poses.set_mount("stowed")
    return spec, rows
