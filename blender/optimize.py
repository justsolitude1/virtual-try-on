"""Make a web-weight copy of one garment GLB.
Run: blender -b --factory-startup -P optimize.py -- <in.glb> <out.glb> <real_height_m> [target_tris]
Decimates to ~target_tris, downsizes textures to 2K, rescales so the garment is <real_height_m> tall
(feet/hem at z=0, centred on x/y), exports JPEG-textured GLB. The original file is not touched.
"""
import bpy, sys, os
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
SRC, DST, HEIGHT = a[0], a[1], float(a[2])
TARGET = int(a[3]) if len(a) > 3 else 100_000

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
ob = next(o for o in bpy.context.scene.objects if o.type == "MESH")
bpy.context.view_layer.objects.active = ob
ob.select_set(True)

tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
dec = ob.modifiers.new("Decimate", "DECIMATE")
dec.ratio = min(1.0, TARGET / tris)
bpy.ops.object.modifier_apply(modifier=dec.name)

# bake world transform, then rescale to real height and re-seat on the ground
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
lo = Vector([min(v.co[i] for v in ob.data.vertices) for i in range(3)])
hi = Vector([max(v.co[i] for v in ob.data.vertices) for i in range(3)])
s = HEIGHT / (hi.z - lo.z)
shift = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
for v in ob.data.vertices:
    v.co = (v.co - shift) * s

for img in bpy.data.images:
    if img.size[0] > 2048:
        img.scale(2048, 2048)

name = os.path.splitext(os.path.basename(DST))[0]
ob.name = ob.data.name = name
bpy.ops.export_scene.gltf(filepath=DST, export_format="GLB", export_image_format="JPEG",
                          export_jpeg_quality=85, export_cameras=False, export_lights=False)
new_tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
print(f"OPT {name}: {tris} -> {new_tris} tris, height {HEIGHT} m, {os.path.getsize(DST)/1e6:.1f} MB")
