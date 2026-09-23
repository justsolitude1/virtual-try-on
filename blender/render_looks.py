"""Dress the avatars per fit.json and render a contact sheet of looks.
Run: blender -b --factory-startup -P render_looks.py -- <models_dir with fit.json> <out.png> <sizes,comma> <views,comma> [tile_w]
Looks (columns): mannequin, each top alone, pants alone, each top + pants.  Rows: size x view.
"""
import bpy, json, os, sys
import numpy as np
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
D, OUT, SIZES, VIEWS = a[0], a[1], a[2].split(","), a[3].split(",")
TW = int(a[4]) if len(a) > 4 else 300
TH = int(TW * 1.75)
FIT = json.load(open(os.path.join(D, "fit.json")))
G = FIT["garments"]
tops = [k for k, v in G.items() if v["slot"] == "top"]
bottoms = [k for k, v in G.items() if v["slot"] == "bottom"]
LOOKS = [[]] + [[t] for t in tops] + [[b] for b in bottoms] + [[t, b] for t in tops for b in bottoms]


def imp(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def setup_scene():
    scn = bpy.context.scene
    scn.render.engine = "BLENDER_EEVEE"
    scn.render.resolution_x, scn.render.resolution_y = TW, TH
    scn.view_settings.view_transform = "Standard"
    for attr in ("use_raytracing", "use_gtao", "use_shadows"):
        if hasattr(scn.eevee, attr):
            setattr(scn.eevee, attr, True)
    w = bpy.data.worlds.new("W"); w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.93, 0.93, 0.93, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.55
    scn.world = w
    ctr = Vector((0, 0, 0.9))
    for nm, loc, e in (("Key", (2.0, -3.0, 2.6), 170), ("Fill", (-3.0, -2.0, 1.2), 70), ("Rim", (0.5, 3.0, 2.4), 120)):
        ld = bpy.data.lights.new(nm, "AREA"); ld.energy = e; ld.size = 2.5
        ob = bpy.data.objects.new(nm, ld); scn.collection.objects.link(ob)
        ob.location = loc
        ob.rotation_euler = (ctr - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    cd = bpy.data.cameras.new("C"); cd.type = "ORTHO"; cd.ortho_scale = 1.95
    cam = bpy.data.objects.new("C", cd); scn.collection.objects.link(cam); scn.camera = cam
    return scn, cam


VIEWPOS = {"front": (0, -6, 0.9), "back": (0, 6, 0.9), "side": (6, 0, 0.9), "34": (4.2, -4.2, 1.2)}
tiles = []
TUCK = {}
for size in SIZES:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn, cam = setup_scene()
    avatar = {o.name.split(".")[0]: o for o in imp(os.path.join(D, FIT["avatars"][size]["file"]))
              if o.type == "MESH"}
    gs = FIT["avatars"][size]["garment_scale"]
    garments = {}
    for key, spec in G.items():
        objs = [o for o in imp(os.path.join(D, spec["file"])) if o.type == "MESH"]
        for o in objs:
            o.scale = [s * k for s, k in zip(spec["scale"], gs)]
            o.location = spec["offset"]
            t = spec.get("tuck_under_top")
            if t:
                orig = [v.co.copy() for v in o.data.vertices]
                tucked = []
                for c in orig:
                    u = min(1, max(0, (c.z - t["z0"]) / (t["z1"] - t["z0"])))
                    u = u * u * (3 - 2 * u)
                    k = 1 + (t["scale"] - 1) * u
                    tucked.append(Vector((c.x * k, c.y * k, c.z)))
                TUCK[o.name] = (orig, tucked)
        garments[key] = objs
    for view in VIEWS:
        cam.location = VIEWPOS[view]
        cam.rotation_euler = (Vector((0, 0, 0.9)) - cam.location).to_track_quat("-Z", "Y").to_euler()
        for look in LOOKS:
            hidden = {p for g in look for p in G[g]["hides"]}
            for name, o in avatar.items():
                o.hide_render = name in hidden
            has_top = any(G[g]["slot"] == "top" for g in look)
            for key, objs in garments.items():
                for o in objs:
                    o.hide_render = key not in look
                    if o.name in TUCK:
                        src = TUCK[o.name][1] if has_top else TUCK[o.name][0]
                        for v, c in zip(o.data.vertices, src):
                            v.co = c
                        o.data.update()
            path = os.path.join(os.path.dirname(OUT), f"_tile_{size}_{view}_{len(tiles)}.png")
            scn.render.filepath = path
            bpy.ops.render.render(write_still=True)
            tiles.append(path)

# contact sheet
cols = len(LOOKS)
rows = len(tiles) // cols
sheet = np.ones((rows * TH, cols * TW, 4), dtype=np.float32)
for i, p in enumerate(tiles):
    img = bpy.data.images.load(p)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(TH, TW, 4)
    r, c = divmod(i, cols)
    sheet[(rows - 1 - r) * TH:(rows - r) * TH, c * TW:(c + 1) * TW] = px
    bpy.data.images.remove(img)
    os.remove(p)
out = bpy.data.images.new("sheet", cols * TW, rows * TH)
out.pixels.foreach_set(sheet.ravel())
out.filepath_raw = OUT
out.file_format = "PNG"
out.save()
print("SHEET", OUT, "looks:", [("+".join(l) or "mannequin") for l in LOOKS])
