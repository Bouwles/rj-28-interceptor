"""Procedural PBR materials (section 7.1). The whole look problem is making an
all-black machine readable, so these differ in roughness, sheen and micro
texture far more than in colour. Base colour never reaches zero.

Phase 0 versions: correct response and micro texture. Wear masks (curvature,
occlusion, dust) are layered on in Phase 7.
"""
import bpy

CYAN = (0.1144, 0.6867, 0.8879)          # #5FD8F2, linear
WHITE = (0.80, 0.80, 0.80)

# key -> (display name, material class for mass/x-ray, density kg/m3)
INFO = {
    "armour":   ("Armour composite, matte",        "armour",    2300),
    "cap":      ("Cap composite, fine matte",      "armour",    1600),
    "alu":      ("Anodised aluminium, satin black", "structure", 2810),
    "ti":       ("Titanium, dark gunmetal",        "structure", 4430),
    "steel":    ("Steel, polished",                "mechanism", 7850),
    "fastener": ("Fastener black oxide",           "mechanism", 7850),
    "rubber":   ("Rubber",                         "soft",      1150),
    "braid":    ("Braided sleeve",                 "harness",   1400),
    "cfrp":     ("CFRP",                           "armour",    1550),
    "glass":    ("Sensor glass",                   "optic",     2500),
    "mesh":     ("Mesh",                           "soft",      2700),
    "emissive": ("Emissive cyan",                  "optic",     1200),
}

_cache = {}


def _new(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    return m, nt, nt.nodes["Principled BSDF"]


def _set(b, **kw):
    for k, v in kw.items():
        sock = b.inputs[k.replace("_", " ")]
        sock.default_value = (*v, 1.0) if isinstance(v, tuple) and len(v) == 3 else v


def _grey(v):
    return (v, v, v)


def _noise_bump(nt, b, scale, strength, distance=0.00015, detail=3.0, stretch=None,
                rough_var=0.0, rough_base=0.5):
    """Object-space noise -> bump (and optional roughness breakup). scale is in
    1/m, so 1500 gives ~0.7 mm grain regardless of part size."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    src = tc.outputs["Object"]
    if stretch:
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = stretch
        nt.links.new(src, mp.inputs["Vector"])
        src = mp.outputs["Vector"]
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = detail
    nt.links.new(src, nz.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    nt.links.new(nz.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    if rough_var:
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = rough_base - rough_var
        mr.inputs["To Max"].default_value = rough_base + rough_var
        nz2 = nt.nodes.new("ShaderNodeTexNoise")
        nz2.inputs["Scale"].default_value = scale * 0.02
        nz2.inputs["Detail"].default_value = 4.0
        nt.links.new(src, nz2.inputs["Vector"])
        nt.links.new(nz2.outputs[0], mr.inputs["Value"])
        nt.links.new(mr.outputs[0], b.inputs["Roughness"])
    return bump


def _uv_math(nt):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    return sep


def _math(nt, op, a, b=None, clamp=False):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def _build(key):
    m, nt, b = _new("RJ28_" + key)
    if key == "armour":
        _set(b, Base_Color=_grey(0.030), Roughness=0.65, Metallic=0.0)
        _noise_bump(nt, b, 1400, 0.35, rough_var=0.05, rough_base=0.65)
    elif key == "cap":
        _set(b, Base_Color=_grey(0.022), Roughness=0.76, Metallic=0.0)
        _noise_bump(nt, b, 4200, 0.18, distance=0.00006)
        _set(b, Sheen_Weight=0.05, Sheen_Roughness=0.4)
    elif key == "alu":
        _set(b, Base_Color=_grey(0.036), Roughness=0.35, Metallic=1.0)
        _noise_bump(nt, b, 900, 0.10, distance=0.00004, detail=1.0,
                    stretch=(1.0, 1.0, 60.0), rough_var=0.04, rough_base=0.35)
    elif key == "ti":
        _set(b, Base_Color=(0.105, 0.097, 0.088), Roughness=0.40, Metallic=1.0)
        _noise_bump(nt, b, 2600, 0.08, distance=0.00003, rough_var=0.04, rough_base=0.40)
    elif key == "steel":
        _set(b, Base_Color=_grey(0.62), Roughness=0.12, Metallic=1.0)
    elif key == "fastener":
        _set(b, Base_Color=_grey(0.055), Roughness=0.50, Metallic=1.0)
    elif key == "rubber":
        _set(b, Base_Color=_grey(0.024), Roughness=0.85, Metallic=0.0)
        _set(b, Sheen_Weight=0.06, Sheen_Roughness=0.5)
        _noise_bump(nt, b, 3000, 0.10, distance=0.00005)
    elif key == "braid":
        _set(b, Base_Color=_grey(0.028), Roughness=0.80, Metallic=0.0)
        sep = _uv_math(nt)
        u = _math(nt, "MULTIPLY", sep.outputs[0], 75.4)       # 12 strands round
        v = _math(nt, "MULTIPLY", sep.outputs[1], 2600.0)     # ~2.4 mm pitch
        w = _math(nt, "MULTIPLY",
                  _math(nt, "SINE", _math(nt, "ADD", u, v)),
                  _math(nt, "SINE", _math(nt, "SUBTRACT", u, v)))
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.6
        bump.inputs["Distance"].default_value = 0.0003
        nt.links.new(w, bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    elif key == "cfrp":
        _set(b, Base_Color=_grey(0.026), Roughness=0.45, Metallic=0.0,
             Coat_Weight=1.0, Coat_Roughness=0.12)
        tc = nt.nodes.new("ShaderNodeTexCoord")
        ck = nt.nodes.new("ShaderNodeTexChecker")
        ck.inputs["Scale"].default_value = 500.0             # 2 mm twill tow
        ck.inputs["Color1"].default_value = (0.36, 0.36, 0.36, 1)
        ck.inputs["Color2"].default_value = (0.52, 0.52, 0.52, 1)
        nt.links.new(tc.outputs["Object"], ck.inputs["Vector"])
        nt.links.new(ck.outputs["Color"], b.inputs["Roughness"])
    elif key == "glass":
        # smoked, coated glass: dark at a glance, but emitters and optics behind it show through
        _set(b, Base_Color=(0.10, 0.13, 0.16), Roughness=0.03, Metallic=0.0,
             Coat_Weight=1.0, Coat_Roughness=0.02, IOR=1.52)
        b.inputs["Transmission Weight"].default_value = 0.94
        b.inputs["Coat Tint"].default_value = (0.55, 0.75, 1.0, 1.0)
    elif key == "mesh":
        _set(b, Base_Color=_grey(0.03), Roughness=0.55, Metallic=1.0)
        sep = _uv_math(nt)                                    # UVs are in metres
        fu = _math(nt, "FRACT", _math(nt, "MULTIPLY", sep.outputs[0], 420.0))
        fv = _math(nt, "FRACT", _math(nt, "MULTIPLY", sep.outputs[1], 420.0))
        wire_u = _math(nt, "LESS_THAN", fu, 0.30)
        wire_v = _math(nt, "LESS_THAN", fv, 0.30)
        alpha = _math(nt, "MAXIMUM", wire_u, wire_v)
        nt.links.new(alpha, b.inputs["Alpha"])
    elif key == "emissive":
        _set(b, Base_Color=(0.0, 0.0, 0.0), Roughness=0.3)
        b.inputs["Emission Color"].default_value = (*CYAN, 1.0)
        b.inputs["Emission Strength"].default_value = 6.0
    elif key == "clay":
        _set(b, Base_Color=_grey(0.42), Roughness=0.55, Metallic=0.0)
    elif key == "cavity":
        _set(b, Base_Color=_grey(0.004), Roughness=0.9)
    elif key == "silhouette":
        _set(b, Base_Color=(0, 0, 0), Roughness=1.0)
        b.inputs["Specular IOR Level"].default_value = 0.0
    else:
        raise KeyError(key)
    m["rj28_key"] = key
    return m


def get(key):
    if key not in _cache or _cache[key].name not in bpy.data.materials:
        _cache[key] = _build(key)
    return _cache[key]


def reset():
    _cache.clear()
