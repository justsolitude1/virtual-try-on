"""Import each GLB, report stats, render a front preview.
Run: blender -b --factory-startup -P inspect.py -- <out_dir> <glb> [<glb> ...]
"""
import bpy, os, sys, json
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
OUT, FILES = args[0], args[1:]
report = {}

for path in FILES:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    scn = bpy.context.scene
    meshes = [o for o in scn.objects if o.type == "MESH"]
    lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
    tris = verts = 0
    dg = bpy.context.evaluated_depsgraph_get()
    for o in meshes:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
        me = o.evaluated_get(dg).to_mesh()
        me.calc_loop_triangles()
        tris += len(me.loop_triangles); verts += len(me.vertices)
    mats = {}
    for m in bpy.data.materials:
        texs = []
        if m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    texs.append(f"{n.image.name} {tuple(n.image.size)}")
        mats[m.name] = texs
    name = os.path.splitext(os.path.basename(path))[0]
    report[name] = {
        "objects": [o.name for o in scn.objects],
        "mesh_objects": len(meshes),
        "armatures": sum(o.type == "ARMATURE" for o in scn.objects),
        "shape_keys": sum(bool(o.data.shape_keys) for o in meshes),
        "verts": verts, "tris": tris,
        "bbox_min": [round(v, 3) for v in lo], "bbox_max": [round(v, 3) for v in hi],
        "size_xyz": [round(v, 3) for v in (hi - lo)],
        "materials": mats,
        "animations": [a.name for a in bpy.data.actions],
    }
    # quick front render
    size = hi - lo
    ctr = (hi + lo) / 2
    scn.render.engine = "BLENDER_EEVEE"
    scn.render.resolution_x = scn.render.resolution_y = 700
    scn.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("W"); world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.9, 0.9, 0.9, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    scn.world = world
    for nm, loc, e in (("Key", (1.5, -2, 1.5), 70), ("Fill", (-2, -1.5, 0.5), 30), ("Rim", (0, 2, 1.5), 50)):
        ld = bpy.data.lights.new(nm, "AREA"); ld.energy = e * max(size) ** 2 * 1.5; ld.size = 2 * max(size)
        ob = bpy.data.objects.new(nm, ld); scn.collection.objects.link(ob)
        ob.location = ctr + Vector(loc) * max(size) * 1.5
        ob.rotation_euler = (ctr - ob.location).to_track_quat("-Z", "Y").to_euler()
    cd = bpy.data.cameras.new("C"); cd.type = "ORTHO"; cd.ortho_scale = max(size) * 1.25
    cam = bpy.data.objects.new("C", cd); scn.collection.objects.link(cam); scn.camera = cam
    # glTF imports Y-up as Blender Z-up; front faces -Y
    cam.location = ctr + Vector((0, -max(size) * 4, 0))
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    cd.clip_end = max(size) * 10
    scn.render.filepath = os.path.join(OUT, f"inspect_{name.replace(' ', '_')}.png")
    bpy.ops.render.render(write_still=True)

with open(os.path.join(OUT, "inspect.json"), "w") as f:
    json.dump(report, f, indent=1)
print("REPORT", json.dumps(report, indent=1))
