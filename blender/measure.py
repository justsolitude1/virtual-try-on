"""Slice each garment horizontally and print the x-intervals (clusters) at each height.
Run: blender -b --factory-startup -P measure.py -- <glb> [...]
"""
import bpy, sys, os
import numpy as np

files = sys.argv[sys.argv.index("--") + 1:]
for path in files:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    ob = next(o for o in bpy.context.scene.objects if o.type == "MESH")
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    co = co @ np.array(ob.matrix_world)[:3, :3].T + np.array(ob.matrix_world)[:3, 3]
    x, y, z = co.T
    print(f"=== {os.path.basename(path)}  z {z.min():.3f}..{z.max():.3f}  x {x.min():.3f}..{x.max():.3f}  y {y.min():.3f}..{y.max():.3f}")
    H = z.max() - z.min()
    for zz in np.linspace(z.min() + 0.005, z.max() - 0.005, 32):
        m = np.abs(z - zz) < 0.006
        if m.sum() < 5:
            continue
        xs = np.sort(x[m])
        gaps = np.where(np.diff(xs) > 0.012)[0]
        starts = np.r_[xs[0], xs[gaps + 1]]
        ends = np.r_[xs[gaps], xs[-1]]
        ivs = []
        for a, b in zip(starts, ends):
            sel = m & (x >= a) & (x <= b)
            ivs.append(f"[{a:+.3f},{b:+.3f} y{y[sel].min():+.3f},{y[sel].max():+.3f}]")
        print(f"z {zz:.3f}: " + " ".join(ivs))
