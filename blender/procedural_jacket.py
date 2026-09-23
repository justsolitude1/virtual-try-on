"""Procedural cropped moto jacket (royal-blue twill) for Blender 5.x.

Run:  blender -b --factory-startup -P build_jacket.py -- <out_dir>
Outputs: blue_moto_jacket.blend, blue_moto_jacket.glb, preview_front.png, preview_34.png
"""
import bpy, bmesh, math, os, sys
import numpy as np
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else os.getcwd()
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)

P = 2.4  # superellipse exponent: flatter sides than an ellipse

# ---------------------------------------------------------------- body profile
# (z, half-width, half-depth) from hem up to the armpit/shoulder line, metres
RINGS = [(0.00, .165, .115), (0.04, .160, .112), (0.10, .157, .111), (0.18, .167, .118),
         (0.26, .180, .126), (0.33, .186, .122), (0.39, .192, .112), (0.43, .197, .100)]
# shoulder slope rings: (half-width, half-depth, z at side, extra z at centre)
TOP = [(.185, .087, .459, .012), (.130, .076, .491, .020), (.078, .066, .520, .0)]
PROFILE = RINGS + [(zs + c, w, d) for (w, d, zs, c) in TOP]


def sgnpow(v, e):
    return math.copysign(abs(v) ** e, v)


def ring_pt(t, w, d):
    return w * sgnpow(math.sin(t), 2 / P), -d * sgnpow(math.cos(t), 2 / P)


def wd_at(z):
    z = max(PROFILE[0][0], min(PROFILE[-1][0], z))
    for (z0, w0, d0), (z1, w1, d1) in zip(PROFILE, PROFILE[1:]):
        if z0 <= z <= z1:
            f = (z - z0) / (z1 - z0) if z1 > z0 else 0
            return w0 + (w1 - w0) * f, d0 + (d1 - d0) * f
    return PROFILE[-1][1:]


def front_y(x, z, off):
    w, d = wd_at(z)
    r = min(abs(x) / w, 0.995)
    return -d * (1 - r ** P) ** (1 / P) - off


def catmull(pts, n):
    """Smooth resample of a 2D/3D polyline to n points (Catmull-Rom, uniform in t)."""
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


# ---------------------------------------------------------------- materials
def twill_normal_map(size=512, period=12):
    i, j = np.meshgrid(np.arange(size), np.arange(size), indexing="ij")
    rng = np.random.default_rng(7)
    h = 0.5 + 0.5 * np.sin(2 * np.pi * (i + j) / period)             # diagonal twill ribs
    h += 0.25 * np.sin(2 * np.pi * (i - j) / (period / 2)) * (h > .5)  # interlacing bumps
    h += 0.15 * rng.random((size, size))                               # yarn noise
    gy, gx = np.gradient(h)
    s = 2.0
    n = np.dstack([-gx * s, -gy * s, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    rgba = np.dstack([(n + 1) / 2, np.ones_like(h)]).astype(np.float32)
    img = bpy.data.images.new("twill_normal", size, size, alpha=False)
    img.pixels.foreach_set(rgba.ravel())
    img.colorspace_settings.name = "Non-Color"
    img.filepath_raw = os.path.join(OUT, "twill_normal.png")
    img.file_format = "PNG"
    img.save()
    return img


def material(name, rgb, rough, metal=0.0, normal_img=None, sheen=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if sheen and "Sheen Weight" in bsdf.inputs:
        bsdf.inputs["Sheen Weight"].default_value = sheen
    if normal_img:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = normal_img
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = 0.5
        nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return m


twill = twill_normal_map()
M_BLUE = material("Royal Blue Twill", (0.016, 0.05, 0.46), 0.85, normal_img=twill, sheen=0.0)
M_LINING = material("Satin Lining", (0.008, 0.022, 0.21), 0.3)
M_PIPING = material("Black Leather Piping", (0.012, 0.012, 0.014), 0.38)
M_ZIP = material("Zip Tape", (0.01, 0.01, 0.012), 0.6)
M_METAL = material("Gunmetal", (0.25, 0.25, 0.27), 0.3, metal=1.0)

ROOT = bpy.data.objects.new("BlueMotoJacket", None)
bpy.context.scene.collection.objects.link(ROOT)


def finish(bm, name, mats, solid=0.0, subsurf=2, solid_offset=-1.0):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = ROOT
    if solid:
        s = ob.modifiers.new("Thickness", "SOLIDIFY")
        s.thickness = solid
        s.offset = solid_offset
        s.material_offset = 1 if len(mats) > 1 else 0
        s.use_even_offset = True
    if subsurf:
        ob.modifiers.new("Smooth", "SUBSURF").levels = subsurf
    return ob


def grid_faces(bm, rows, uv_of, closed):
    """rows: list of vertex lists; builds quads between consecutive rows with UVs."""
    uv = bm.loops.layers.uv.verify()
    n = len(rows[0])
    span = n if closed else n - 1
    for r in range(len(rows) - 1):
        for j in range(span):
            j2 = (j + 1) % n
            vs = [rows[r][j], rows[r][j2], rows[r + 1][j2], rows[r + 1][j]]
            f = bm.faces.new(vs)
            coords = [uv_of(r, j), uv_of(r, j + 1), uv_of(r + 1, j + 1), uv_of(r + 1, j)]
            for loop, c in zip(f.loops, coords):
                loop[uv].uv = c


# ---------------------------------------------------------------- body shell
def build_body():
    N = 72
    bm = bmesh.new()
    rows, zs = [], []
    for z, w, d in RINGS:
        rows.append([bm.verts.new((*ring_pt(2 * math.pi * j / N, w, d), z)) for j in range(N)])
    for w, d, zside, c in TOP:
        row = []
        for j in range(N):
            t = 2 * math.pi * j / N
            x, y = ring_pt(t, w, d)
            row.append(bm.verts.new((x, y, zside + c * (1 - abs(math.sin(t))))))
        rows.append(row)
    grid_faces(bm, rows, lambda r, j: (j / N * 10, rows[r][0].co.z * 10), closed=True)
    # open the V-neckline at the front (lining shows through)
    kill = []
    for f in bm.faces:
        c = f.calc_center_median()
        v = 0.012 + max(0, c.z - 0.23) / 0.29 * 0.07
        if c.y < -0.02 and c.z > 0.23 and abs(c.x) < v:
            kill.append(f)
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    return finish(bm, "Body", [M_BLUE, M_LINING], solid=0.008)


# ---------------------------------------------------------------- sleeves
def build_sleeve(side):
    N, L = 40, 0.60
    ang = math.radians(10)
    d = Vector((side * math.sin(ang), 0, -math.cos(ang)))
    a = Vector((side * 0.192, 0.0, 0.385))
    e1 = Vector((0, 1, 0))
    e2 = d.cross(e1).normalized()
    # (fraction along sleeve, radius across, radius front-back)
    prof = [(-.105, .004, .004), (-.097, .030, .031), (-.075, .052, .055), (-.042, .068, .072),
            (0, .074, .078), (.15, .068, .070), (.5, .061, .062), (.88, .058, .059),
            (.915, .058, .059), (.925, .066, .066), (.96, .066, .066), (1, .065, .065)]
    bm = bmesh.new()
    rows = []
    for s, rx, ry in prof:
        c = a + d * (L * s) if s >= 0 else a + d * (s * 0.6)
        rows.append([bm.verts.new(c + e1 * (ry * math.cos(2 * math.pi * j / N))
                                  + e2 * (rx * math.sin(2 * math.pi * j / N))) for j in range(N)])
    grid_faces(bm, rows, lambda r, j: (j / N * 4, prof[r][0] * L * 10), closed=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return finish(bm, "Sleeve_" + ("L" if side > 0 else "R"), [M_BLUE, M_LINING], solid=0.007)


# ---------------------------------------------------------------- lapels & collar
def build_lapel(name, inner, outer, off, flip):
    n = 28
    bm = bmesh.new()
    rows = []
    for edge in (inner, outer):
        pts = catmull([Vector((x, z)) for x, z in edge], n)
        rows.append([bm.verts.new((p.x, front_y(p.x, p.y, off), p.y)) for p in pts])
    # transpose so faces run inner->outer along the length
    cols = [[rows[0][i], rows[1][i]] for i in range(n)]
    if flip:
        cols = [c[::-1] for c in cols]
    grid_faces(bm, cols, lambda r, j: (cols[r][j].co.x * 10, cols[r][j].co.z * 10), closed=False)
    return finish(bm, name, [M_BLUE, M_LINING], solid=0.006, subsurf=1)


def build_collar():
    N = 48
    t0, t1 = 0.47 * math.pi, 1.53 * math.pi
    specs = [(.079, .067, .512), (.090, .079, .540), (.112, .100, .546)]
    bm = bmesh.new()
    rows = []
    for w, d, z in specs:
        rows.append([bm.verts.new((*ring_pt(t0 + (t1 - t0) * j / N, w, d), z)) for j in range(N + 1)])
    grid_faces(bm, rows, lambda r, j: (j / N * 5, specs[r][2] * 10), closed=False)
    return finish(bm, "Collar", [M_BLUE, M_LINING], solid=0.007)


# ---------------------------------------------------------------- tubes (piping, zip, edges)
def tube(name, pts, r, mat, seg=10, n=80):
    path = catmull(pts, n)
    bm = bmesh.new()
    rows = []
    prev_nrm = None
    for i, p in enumerate(path):
        tng = (path[min(i + 1, n - 1)] - path[max(i - 1, 0)]).normalized()
        ref = Vector((0, 1, 0)) if abs(tng.y) < 0.9 else Vector((1, 0, 0))
        nrm = tng.cross(ref).normalized()
        if prev_nrm is not None and nrm.dot(prev_nrm) < 0:
            nrm = -nrm
        prev_nrm = nrm
        bi = tng.cross(nrm)
        rows.append([bm.verts.new(p + (nrm * math.cos(2 * math.pi * k / seg)
                                       + bi * math.sin(2 * math.pi * k / seg)) * r) for k in range(seg)])
    grid_faces(bm, rows, lambda a, b: (b / seg, a / n), closed=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return finish(bm, name, [mat], subsurf=1)


def on_front(xz, off):
    return [(x, front_y(x, z, off), z) for x, z in xz]


def box(name, center, size, mat):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2])) + Vector(center)
    return finish(bm, name, [mat], subsurf=0)


build_body()
build_sleeve(+1)
build_sleeve(-1)
build_collar()

# big wrap lapel (wearer's left, +x) crosses the centre front
build_lapel("Lapel_Wrap",
            inner=[(-0.02, .23), (0.02, .32), (0.05, .42), (0.072, .51)],
            outer=[(-0.02, .23), (0.06, .31), (0.105, .37), (0.148, .425), (0.117, .447),
                   (0.128, .485), (0.10, .512)],
            off=0.013, flip=False)
# zip lapel (wearer's right, -x)
LEFT_OUTER = [(-0.01, .30), (-0.06, .355), (-0.122, .415), (-0.10, .442), (-0.118, .485), (-0.095, .512)]
build_lapel("Lapel_Zip",
            inner=[(-0.01, .30), (-0.03, .37), (-0.055, .44), (-0.07, .51)],
            outer=LEFT_OUTER, off=0.011, flip=True)

# asymmetric zip running down the edge of the zip lapel
zip_pts = on_front([(-0.128, .418), (-0.09, .38), (-0.05, .345), (-0.022, .318)], 0.022)
tube("Zip", zip_pts, 0.0042, M_ZIP)
box("Zip_Slider", zip_pts[0], (0.006, 0.004, 0.011), M_METAL)

# overlap edge of the front wrap, lapel bottom down to the hem
tube("Front_Edge", on_front([(-0.02, .232), (-0.016, .15), (-0.012, .06), (-0.01, 0.0)], 0.009),
     0.0045, M_BLUE)

# black piping on the princess seams (front and back)
for sx in (1, -1):
    tube(f"Piping_Front_{sx:+d}",
         on_front([(sx * .098, .003), (sx * .094, .10), (sx * .104, .20), (sx * .122, .30),
                   (sx * .152, .38), (sx * .172, .425)], 0.0045), 0.0026, M_PIPING)
    back = [(sx * .10, -front_y(sx * .10, z, 0) + 0.0045, z) for z in (.003, .12, .24, .34)]
    back.append((sx * .16, -front_y(sx * .16, .42, 0) + 0.0045, .42))
    tube(f"Piping_Back_{sx:+d}", back, 0.0026, M_PIPING)

# ---------------------------------------------------------------- scene, renders, export
scn = bpy.context.scene
for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "CYCLES"):
    try:
        scn.render.engine = eng
        break
    except TypeError:
        continue
for attr in ("use_raytracing", "use_gtao", "use_shadows"):
    if hasattr(scn.eevee, attr):
        setattr(scn.eevee, attr, True)
if scn.render.engine == "CYCLES":
    scn.cycles.samples = 64
scn.render.resolution_x, scn.render.resolution_y = 1000, 1200
scn.view_settings.view_transform = "Standard"

world = bpy.data.worlds.new("Studio")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.92, 0.92, 0.93, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45
scn.world = world


def light(name, loc, energy, size):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.size = energy, size
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    scn.collection.objects.link(ob)
    ob.rotation_euler = (Vector((0, 0, 0.2)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


light("Key", (1.4, -2.0, 1.6), 70, 2.0)
light("Fill", (-2.0, -1.4, 0.4), 30, 2.5)
light("Rim", (0.2, 2.0, 1.4), 60, 1.5)

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 60
cam = bpy.data.objects.new("Cam", cam_data)
scn.collection.objects.link(cam)
scn.camera = cam
target = Vector((0, 0, 0.18))
for fname, loc in (("preview_front.png", (0, -2.6, 0.2)), ("preview_34.png", (1.3, -2.25, 0.35))):
    cam.location = loc
    cam.rotation_euler = (target - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    scn.render.filepath = os.path.join(OUT, fname)
    bpy.ops.render.render(write_still=True)

bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "blue_moto_jacket.blend"))
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "blue_moto_jacket.glb"), export_format="GLB",
                          export_apply=True, export_cameras=False, export_lights=False)
print("DONE", scn.render.engine)
