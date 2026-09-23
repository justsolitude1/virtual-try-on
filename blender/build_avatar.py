"""Faceless fashion-mannequin avatars (sizes S and L), built to sit inside the garment GLBs.

Run:  blender -b --factory-startup -P build_avatar.py -- <out_dir>
Writes avatar_S.glb, avatar_L.glb (+ .blend). Each avatar is split into named parts so the
try-on can hide whatever a garment covers:  head, torso_upper, hips, arms, hands, legs, feet.
Units are metres, Blender Z-up, front faces -Y (glTF export converts to Y-up, front +Z).
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else os.getcwd()
os.makedirs(OUT, exist_ok=True)

SIZES = {"S": 1.00, "L": 1.15}      # girth factor relative to S
TORSO_SPLIT = 1.03                  # below: hips (hidden by pants); above: torso_upper (hidden by jackets)
NECK_SPLIT = 1.445                  # above: head + neck (always visible)

# torso + neck + head as one loft: (z, half-width, half-depth, centre-y, superellipse exponent)
TORSO = [
    (0.770, .004, .004, .012, 2.4), (0.775, .060, .050, .012, 2.4), (0.795, .120, .090, .012, 2.4),
    (0.830, .160, .108, .012, 2.4), (0.900, .176, .112, .012, 2.4), (0.970, .156, .100, .008, 2.4),
    (1.020, .128, .092, .004, 2.4), (1.060, .118, .086, .000, 2.4), (1.120, .126, .090, -.004, 2.4),
    (1.180, .140, .102, -.008, 2.4), (1.250, .152, .112, -.012, 2.4), (1.310, .158, .104, -.006, 2.4),
    (1.360, .166, .090, .000, 2.4), (1.395, .160, .076, .005, 2.4), (1.420, .115, .064, .010, 2.4),
    (1.440, .070, .056, .012, 2.2), (1.455, .056, .052, .012, 2.0),
]
NECK_HEAD = [  # not scaled by girth (a slightly thicker neck for L is handled below)
    (1.500, .049, .050, .012, 2.0), (1.525, .050, .054, .008, 2.0), (1.545, .058, .070, -.008, 2.0),
    (1.570, .068, .086, -.008, 2.0), (1.610, .076, .095, .000, 2.0), (1.650, .079, .098, .004, 2.0),
    (1.690, .074, .092, .008, 2.0), (1.720, .058, .075, .010, 2.0), (1.738, .030, .042, .010, 2.0),
    (1.745, .002, .002, .010, 2.0),
]
# limbs: control points (x on the +X side, y, z) and (radius-a, radius-b) per point
ARM = [((.150, .010, 1.375), (.052, .054)), ((.190, .012, 1.330), (.050, .052)),
       ((.212, .018, 1.200), (.044, .046)), ((.225, .022, 1.100), (.038, .040)),
       ((.245, .020, 0.970), (.034, .035)), ((.262, .015, 0.850), (.022, .027))]
LEG = [((.082, .012, .900), (.088, .092)), ((.095, .012, .750), (.080, .085)),
       ((.108, .010, .600), (.068, .072)), ((.118, .008, .480), (.052, .056)),
       ((.128, .020, .360), (.055, .060)), ((.140, .015, .220), (.042, .045)),
       ((.150, .010, .100), (.032, .034))]
# hand (palm faces the thigh): radius-a = thickness (x), radius-b = width (y); x is relative to wrist
HAND = [((.000, .015, .870), (.020, .026)), ((.001, .012, .820), (.016, .036)),
        ((.004, .005, .760), (.013, .040)), ((.000, .000, .700), (.011, .034)),
        ((-.007, -.002, .675), (.008, .022))]
THUMB = [((.006, -.010, .835), (.011, .011)), ((.000, -.030, .800), (.010, .010)),
         ((-.007, -.038, .765), (.008, .008))]
WRIST_X = .262
# ankle boot: shaft + foot (foot tube runs heel->toe: radius-a = height, radius-b = width)
SHAFT = [((.150, .010, .035), (.041, .043)), ((.150, .010, .150), (.038, .040))]
FOOT = [((.150, .060, .042), (.042, .034)), ((.150, .010, .042), (.042, .040)),
        ((.151, -.070, .032), (.030, .041)), ((.152, -.150, .022), (.014, .024))]
ANKLE_X = .150


def sgnpow(v, e):
    return math.copysign(abs(v) ** e, v)


def catmull(pts, n):
    pts = [Vector(p) for p in pts]
    ext = [pts[0] * 2 - pts[1]] + pts + [pts[-1] * 2 - pts[-2]]
    segs = len(pts) - 1
    out = []
    for i in range(n):
        u = i / (n - 1) * segs
        k = min(int(u), segs - 1)
        t = u - k
        p0, p1, p2, p3 = ext[k:k + 4]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return out


def lerp_list(vals, n):
    out = []
    for i in range(n):
        u = i / (n - 1) * (len(vals) - 1)
        k = min(int(u), len(vals) - 2)
        f = u - k
        out.append(tuple(a + (b - a) * f for a, b in zip(vals[k], vals[k + 1])))
    return out


def quads(bm, rows, closed=True):
    n = len(rows[0])
    for r in range(len(rows) - 1):
        for j in range(n if closed else n - 1):
            j2 = (j + 1) % n
            bm.faces.new([rows[r][j], rows[r][j2], rows[r + 1][j2], rows[r + 1][j]])


def loft(bm, rings, N=48):
    rows = []
    for z, w, d, cy, p in rings:
        row = []
        for j in range(N):
            t = 2 * math.pi * j / N
            row.append(bm.verts.new((w * sgnpow(math.sin(t), 2 / p),
                                     cy - d * sgnpow(math.cos(t), 2 / p), z)))
        rows.append(row)
    quads(bm, rows)


def tube(bm, ctrl, n=36, seg=24, caps=True):
    """Elliptical tube along a Catmull-Rom path with domed ends."""
    path = catmull([c[0] for c in ctrl], n)
    radii = lerp_list([c[1] for c in ctrl], n)
    frames = []
    prev = None
    for i, p in enumerate(path):
        tng = (path[min(i + 1, n - 1)] - path[max(i - 1, 0)]).normalized()
        ref = Vector((0, 1, 0)) if abs(tng.y) < 0.9 else Vector((1, 0, 0))
        nrm = tng.cross(ref).normalized()
        if prev is not None and nrm.dot(prev) < 0:
            nrm = -nrm
        prev = nrm
        frames.append((p, tng, nrm, tng.cross(nrm), radii[i]))
    specs = []
    if caps:
        p, t, a, b, (ra, rb) = frames[0]
        for ang in (88, 75, 55, 30):
            s = math.cos(math.radians(ang))
            specs.append((p - t * min(ra, rb) * math.sin(math.radians(ang)), a, b, ra * s, rb * s))
    specs += [(p, a, b, ra, rb) for p, t, a, b, (ra, rb) in frames]
    if caps:
        p, t, a, b, (ra, rb) = frames[-1]
        for ang in (30, 55, 75, 88):
            s = math.cos(math.radians(ang))
            specs.append((p + t * min(ra, rb) * math.sin(math.radians(ang)), a, b, ra * s, rb * s))
    rows = []
    for c, a, b, ra, rb in specs:
        rows.append([bm.verts.new(c + a * (ra * math.cos(2 * math.pi * k / seg))
                                  + b * (rb * math.sin(2 * math.pi * k / seg))) for k in range(seg)])
    quads(bm, rows)


def mirror(ctrl, side, g=1.0, rscale=1.0, dx=0.0):
    return [((side * (x * g + dx), y, z), (ra * rscale, rb * rscale)) for (x, y, z), (ra, rb) in ctrl]


def material(name, rgb, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    return m


def make_object(name, bm, mat, parent, subsurf):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    if subsurf:
        ob.modifiers.new("Smooth", "SUBSURF").levels = subsurf
    return ob


def bake(ob):
    """Apply modifiers in place (so we can split without seams)."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear()
    old = ob.data
    ob.data = me
    bpy.data.meshes.remove(old)
    for p in me.polygons:
        p.use_smooth = True


def split_by_z(ob, parts):
    """parts: list of (name, zmin, zmax). Creates one object per band from ob's faces, deletes ob."""
    out = []
    for name, lo, hi in parts:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        kill = [f for f in bm.faces if not (lo <= f.calc_center_median().z < hi)]
        bmesh.ops.delete(bm, geom=kill, context="FACES")
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(ob.data.materials[0])
        for p in me.polygons:
            p.use_smooth = True
        o = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(o)
        o.parent = ob.parent
        out.append(o)
    bpy.data.objects.remove(ob)
    return out


def build(size, g):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    skin = material("Mannequin", (0.62, 0.56, 0.50), 0.5)
    boot = material("Boot Leather", (0.02, 0.02, 0.022), 0.5)
    root = bpy.data.objects.new(f"Avatar_{size}", None)
    bpy.context.scene.collection.objects.link(root)
    root["size"] = size

    # torso -> neck -> head, one continuous loft; girth scales the body, not the head
    rings = [(z, w * g, d * g, cy, p) for z, w, d, cy, p in TORSO]
    neck_g = 1 + (g - 1) * 0.4
    rings += [(z, w * (neck_g if z < 1.53 else 1), d * (neck_g if z < 1.53 else 1), cy, p)
              for z, w, d, cy, p in NECK_HEAD]
    bm = bmesh.new()
    loft(bm, rings)
    torso = make_object("body", bm, skin, root, 2)
    bake(torso)
    split_by_z(torso, [("hips", 0, TORSO_SPLIT), ("torso_upper", TORSO_SPLIT, NECK_SPLIT),
                       ("head", NECK_SPLIT, 9)])

    bm = bmesh.new()
    for side in (1, -1):
        tube(bm, mirror(ARM, side, g, g))
    make_object("arms", bm, skin, root, 1)

    bm = bmesh.new()
    dx = WRIST_X * g
    for side in (1, -1):
        tube(bm, mirror(HAND, side, dx=dx), n=24, seg=20)
        tube(bm, mirror(THUMB, side, dx=dx), n=12, seg=12)
    make_object("hands", bm, skin, root, 1)

    bm = bmesh.new()
    for side in (1, -1):
        tube(bm, mirror(LEG, side, g, g))
    make_object("legs", bm, skin, root, 1)

    bm = bmesh.new()
    ax = ANKLE_X * g
    for side in (1, -1):
        tube(bm, mirror(SHAFT, side, dx=ax - ANKLE_X), n=8, seg=24)
        tube(bm, mirror(FOOT, side, dx=ax - ANKLE_X), n=24, seg=24)
    make_object("feet", bm, boot, root, 1)

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, f"avatar_{size}.blend"))
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, f"avatar_{size}.glb"), export_format="GLB",
                              export_apply=True, export_cameras=False, export_lights=False,
                              export_extras=True)
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons)
               for o in bpy.context.scene.objects if o.type == "MESH")
    print(f"AVATAR {size}: {tris} tris, {os.path.getsize(os.path.join(OUT, f'avatar_{size}.glb'))/1e6:.1f} MB")


for size, g in SIZES.items():
    build(size, g)
