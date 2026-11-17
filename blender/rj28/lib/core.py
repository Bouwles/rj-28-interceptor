"""Scene, object and modifier plumbing.

Every public dimension in this package is in millimetres. Geometry is stored
in metres (1 Blender unit = 1 m) so the GLB exports at true scale; the single
conversion happens in obj_from_bm().
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

MM = 0.001
BEVEL_ATTR = "bevel_weight_edge"


# ── scene ────────────────────────────────────────────────────────────────────
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.unit_settings.system = "METRIC"
    s.unit_settings.scale_length = 1.0
    s.unit_settings.length_unit = "MILLIMETERS"
    return s


def coll(name, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


# ── placement (all in mm) ────────────────────────────────────────────────────
def T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def R(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


def frame(origin, z_dir, x_hint=(1, 0, 0)):
    """Matrix whose +Z is z_dir and whose +X is x_hint made perpendicular."""
    z = Vector(z_dir).normalized()
    x = Vector(x_hint) - z * z.dot(Vector(x_hint))
    if x.length < 1e-6:
        x = z.orthogonal()
    x.normalize()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(origin)
    return m


# ── bevel / shading policy ───────────────────────────────────────────────────
def bevel_layer(bm):
    return bm.edges.layers.float.get(BEVEL_ATTR) or bm.edges.layers.float.new(BEVEL_ATTR)


def mark_bevel(bm, angle=30.0, weight=1.0, only_unset=False):
    """Give every edge sharper than `angle` a bevel weight. The Bevel modifier
    runs on weights, so booleans applied later don't get surprise bevels."""
    bm.normal_update()
    lay = bevel_layer(bm)
    lim = math.radians(angle)
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > lim:
            if not (only_unset and e[lay] > 0.0):
                e[lay] = weight


def shade(me, sharp_angle=35.0):
    """Smooth faces; mark sharp only the hard edges that carry no bevel."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    lay = bm.edges.layers.float.get(BEVEL_ATTR)
    lim = math.radians(sharp_angle)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        w = e[lay] if lay else 0.0
        hard = len(e.link_faces) == 2 and e.calc_face_angle(0.0) > lim
        e.smooth = not (hard and w == 0.0)
    bm.to_mesh(me)
    bm.free()


def add_bevel(ob, width, segments=2):
    """Live weight-limited bevel + weighted normals. width in mm."""
    for m in list(ob.modifiers):
        if m.type in {"BEVEL", "WEIGHTED_NORMAL"}:
            ob.modifiers.remove(m)
    if width:
        b = ob.modifiers.new("Bevel", "BEVEL")
        b.width = width * MM
        b.segments = segments
        b.limit_method = "WEIGHT"
        b.use_clamp_overlap = True
        b.harden_normals = False
    wn = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    wn.keep_sharp = True
    wn.weight = 100
    wn.mode = "FACE_AREA"
    ob["bevel_mm"] = float(width or 0.0)


# ── object creation ──────────────────────────────────────────────────────────
def obj_from_bm(name, bm, matrix=None, collection=None, material=None,
                bevel=1.0, segments=2, bevel_angle=30.0):
    """Bake `matrix` (mm) into the verts, convert to metres, make an object.

    material: Material, or list of Materials (slot order = face material_index).
    bevel: edge bevel width in mm (0/None for none). Objects keep identity
    transform, so "apply all transforms" is true by construction.
    """
    if matrix is not None:
        bm.transform(matrix)
    bmesh.ops.scale(bm, vec=(MM, MM, MM), verts=bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=2e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if bevel:
        mark_bevel(bm, bevel_angle)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    if material is not None:
        for m in (material if isinstance(material, (list, tuple)) else [material]):
            me.materials.append(m)
    shade(me)
    add_bevel(ob, bevel, segments)
    return ob


def empty(name, matrix, collection=None, size=30.0):
    """Axis empty; matrix in mm, local Z is the joint axis."""
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "ARROWS"
    e.empty_display_size = size * MM
    m = matrix.copy()
    m.translation = m.translation * MM
    e.matrix_world = m
    (collection or bpy.context.scene.collection).objects.link(e)
    return e


# ── evaluated / applied meshes, booleans ─────────────────────────────────────
def evaluated_mesh(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    return bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)


def boolean(target, cutters, op="DIFFERENCE", lip=None, keep=False):
    """Apply an EXACT boolean to target's base mesh now; other modifiers stay live.

    lip: bevel weight (fraction of the object's bevel width) for the new hard
    edges the cut creates. None leaves them crisp (they are marked sharp).
    """
    cutters = list(cutters) if isinstance(cutters, (list, tuple)) else [cutters]
    saved = [(m, m.show_viewport) for m in target.modifiers]
    for m, _ in saved:
        m.show_viewport = False
    mods = []
    for c in cutters:
        b = target.modifiers.new("_bool", "BOOLEAN")
        b.operation = op
        b.solver = "EXACT"
        b.object = c
        mods.append(b)
    new = evaluated_mesh(target)
    for b in mods:
        target.modifiers.remove(b)
    for m, vis in saved:
        m.show_viewport = vis
    if len(new.vertices) == 0 and len(target.data.vertices) > 0 and op != "INTERSECT":
        # the exact solver gives up on cutters that are tangent to an edge or that
        # overlap themselves; keep the part and say so rather than emptying it
        print("BOOLEAN EMPTY", target.name, "- cut skipped")
        bpy.data.meshes.remove(new)
        if not keep:
            for c in cutters:
                me = c.data
                bpy.data.objects.remove(c)
                if me.users == 0:
                    bpy.data.meshes.remove(me)
        return target
    old = target.data
    new.name = old.name
    target.data = new
    bpy.data.meshes.remove(old)

    bm = bmesh.new()
    bm.from_mesh(new)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=2e-7)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-7, edges=bm.edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if lip:
        mark_bevel(bm, 30.0, weight=lip, only_unset=True)
    bm.to_mesh(new)
    bm.free()
    shade(new)
    if not keep:
        for c in cutters:
            me = c.data
            bpy.data.objects.remove(c)
            if me.users == 0:
                bpy.data.meshes.remove(me)
    return target


def cutter(bm, matrix=None, name="_cutter"):
    """Temporary boolean operand from a bmesh (mm). No bevel weights."""
    if matrix is not None:
        bm.transform(matrix)
    bmesh.ops.scale(bm, vec=(MM, MM, MM), verts=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll("_cutters").objects.link(ob)
    return ob


def boolean_cut(target, cutters, lip=None, keep=False):
    return boolean(target, cutters, "DIFFERENCE", lip, keep)


def boolean_join(target, others, lip=None):
    return boolean(target, others, "UNION", lip)


def boolean_intersect(target, others, lip=None):
    return boolean(target, others, "INTERSECT", lip)


def bounds_mm(objs):
    """World AABB of evaluated objects, in mm: (min Vector, max Vector)."""
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for ob in objs:
        if ob.type != "MESH" or len(ob.data.vertices) == 0:
            continue
        ev = ob.evaluated_get(dg)
        for c in ev.bound_box:
            w = ev.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], w[i])
                hi[i] = max(hi[i], w[i])
    return lo / MM, hi / MM
