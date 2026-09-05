"""Build the editable DrugTree body scene and its transparent browser render.

Run with Blender 4.5: blender --background --python scripts/build_body_atlas.py
    -- --base-mesh /path/to/base.obj
The script also runs through Blender MCP's execute_blender_code tool.

Base mesh: MakeHuman hm08, CC0 (only the body group, no helper geometry).
https://github.com/makehumancommunity/makehuman/blob/master/makehuman/data/3dobjs/base.obj
https://github.com/makehumancommunity/makehuman/blob/master/LICENSE.md
The saved .blend contains the mesh; re-rendering it needs no download or addon.
Organ geometry is illustrative and supports region navigation, not diagnosis.
"""

import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


ROOT = Path(globals().get("DRUGTREE_ROOT") or Path(__file__).resolve().parents[1])
BASE_MESH = globals().get("DRUGTREE_BASE_MESH")
if "--base-mesh" in sys.argv:
    BASE_MESH = sys.argv[sys.argv.index("--base-mesh") + 1]
if not BASE_MESH or not Path(BASE_MESH).is_file():
    raise FileNotFoundError("Pass --base-mesh /path/to/MakeHuman/base.obj (CC0; source URL above).")
BASE_MESH = Path(BASE_MESH)
ASSETS = ROOT / "src/frontend/assets"
ASSETS.mkdir(parents=True, exist_ok=True)
DESIGN = ROOT / "design"
DESIGN.mkdir(exist_ok=True)


def material(name, color, roughness=0.4, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Subsurface Weight"].default_value = 0.06
    return mat


def smooth(obj, mat, region=None):
    obj.data.materials.append(mat)
    for poly in getattr(obj.data, "polygons", []):
        poly.use_smooth = True
    if region:
        obj["body_region"] = region
    return obj


def ellipsoid(name, position, scale, mat, region=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=40, ring_count=24, location=position)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    return smooth(obj, mat, region)


def tube(name, points, radius, mat, region=None):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 12
    curve.bevel_depth = radius
    curve.bevel_resolution = 4
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, xyz in zip(spline.bezier_points, points):
        point.co = xyz
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    return smooth(obj, mat, region)


def loft(name, rings, mat, region):
    # Cross sections: (height, center x, center y, radius x, radius y).
    verts, faces = [], []
    sides = 40
    for z, x, y, rx, ry in rings:
        for i in range(sides):
            a = i * math.tau / sides
            verts.append((x + rx * math.cos(a), y + ry * math.sin(a), z))
    for j in range(len(rings) - 1):
        for i in range(sides):
            k, n = j * sides + i, j * sides + (i + 1) % sides
            faces.append((k, n, n + sides, k + sides))
    faces.extend([tuple(reversed(range(sides))), tuple(range(len(verts) - sides, len(verts)))])
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    smooth(obj, mat, region)
    modifier = obj.modifiers.new("Organic surface", "SUBSURF")
    modifier.levels = 2
    return obj


def build_body(mat):
    verts, faces = [], []
    group = ""
    for line in BASE_MESH.read_text().splitlines():
        if line.startswith("v "):
            verts.append(tuple(map(float, line.split()[1:4])))
        elif line.startswith("g "):
            group = line[2:]
        elif line.startswith("f ") and group == "body":
            faces.append(tuple(int(p.split("/")[0]) - 1 for p in line.split()[1:]))
    used = sorted({i for face in faces for i in face})
    index = {old: new for new, old in enumerate(used)}
    normalized = []
    for i in used:
        x, height, depth = verts[i]
        side = 1 if x >= 0 else -1
        # Lower the relaxed arms toward a neutral anatomical stance.
        if height > 1.2:
            blend = min(1, max(0, (abs(x) - 1.25) / 0.8))
            angle = math.radians(19) * blend
            dx, dz = abs(x) - 1.68, height - 5.24
            x = side * (1.68 + dx * math.cos(angle) + dz * math.sin(angle))
            height = 5.24 - dx * math.sin(angle) + dz * math.cos(angle)
        # Bring the feet under the hips while retaining a visible leg gap.
        if height < 0.5:
            x -= side * 0.78 * min(1, (0.5 - height) / 8.5)
        scale = 1.76 / 16.6589
        normalized.append((x * scale, -depth * scale, (height + 8.1676) * scale))
    mesh = bpy.data.meshes.new("MakeHuman hm08 body — CC0")
    mesh.from_pydata(normalized, [], [tuple(index[i] for i in face) for face in faces])
    mesh.update()
    obj = bpy.data.objects.new("Human body", mesh)
    bpy.context.collection.objects.link(obj)
    smooth(obj, mat, "skin")
    obj["source"] = "MakeHuman hm08 base.obj — CC0 1.0 Universal"
    modifier = obj.modifiers.new("Anatomical surface", "SUBSURF")
    modifier.levels = 2
    return obj


# Work in a new scene so the user's other scenes are preserved.
scene = bpy.data.scenes.new("DrugTree Anatomy")
bpy.context.window.scene = scene
skin = material("Porcelain blue skin", (0.18, 0.31, 0.43), 0.43, 0.05)
bone = material("Ivory bone", (0.65, 0.76, 0.79), 0.5)
lung_mat = material("Lungs — muted rose", (0.40, 0.22, 0.28), 0.43)
heart_mat = material("Heart — carmine", (0.48, 0.065, 0.10), 0.31)
artery = material("Arteries", (0.49, 0.10, 0.13), 0.37)
vein = material("Veins", (0.05, 0.23, 0.43), 0.32)
liver_mat = material("Liver — warm umber", (0.37, 0.13, 0.10), 0.37)
stomach_mat = material("Stomach — warm rose", (0.63, 0.34, 0.27), 0.4)
intestine_mat = material("Intestines", (0.53, 0.28, 0.25), 0.45)
brain_mat = material("Brain", (0.61, 0.42, 0.41), 0.48)
kidney_mat = material("Kidneys", (0.41, 0.12, 0.17), 0.38)
gland = material("Endocrine and lymphatic", (0.30, 0.50, 0.38), 0.4)
body = build_body(skin)

# The brain and organs sit in an illustrated anterior cutaway. Their modeled
# depth is deliberately shallow for legibility from the fixed atlas camera.
for side in (-1, 1):
    hemi = ellipsoid(f"Cerebral hemisphere {side}", (side * 0.034, -0.098, 1.686), (0.037, 0.058, 0.054), brain_mat, "brain_cns")
    for row in range(6):
        z = 1.649 + row * 0.013
        width = 0.026 * math.sqrt(max(0.1, 1 - ((z - 1.686) / 0.06) ** 2))
        points = [(side * (0.014 + width * t / 8), -0.151 - 0.004 * math.sin(t * 1.5 + row), z + 0.005 * math.sin(t * 1.6 + row)) for t in range(9)]
        tube(f"Cortical fold {side} {row}", points, 0.0032, brain_mat, "brain_cns")
    # Eyes remain quiet, with a natural corneal shape and pupils.
    ellipsoid(f"Eye {side}", (side * 0.0325, -0.132, 1.632), (0.0115, 0.007, 0.007), bone, "eye_ear")
    ellipsoid(f"Iris {side}", (side * 0.0325, -0.138, 1.632), (0.004, 0.002, 0.004), vein, "eye_ear")

tube("Trachea", [(0, -0.072, 1.495), (0, -0.10, 1.40), (0, -0.113, 1.35)], 0.009, bone, "lung_respiratory")
for i in range(10):
    z = 1.385 + i * 0.009
    tube(f"Tracheal ring {i}", [(-0.009, -0.103, z), (0, -0.113, z + 0.002), (0.009, -0.103, z)], 0.0014, bone, "lung_respiratory")
for side in (-1, 1):
    loft(f"Lung {side}", [
        (1.147, side * 0.084, -0.104, 0.018, 0.018),
        (1.162, side * 0.080, -0.11, 0.058, 0.039),
        (1.21, side * 0.084, -0.105, 0.062, 0.045),
        (1.29, side * 0.078, -0.105, 0.06, 0.040),
        (1.36, side * 0.061, -0.105, 0.047, 0.033),
        (1.405, side * 0.044, -0.09, 0.012, 0.012),
    ], lung_mat, "lung_respiratory")
    tube(f"Main bronchus {side}", [(0, -0.13, 1.36), (side * 0.038, -0.146, 1.32), (side * 0.077, -0.15, 1.255)], 0.0045, bone, "lung_respiratory")
    for i in range(4):
        z = 1.33 - i * 0.035
        tube(f"Bronchial branch {side} {i}", [(side * 0.052, -0.15, z), (side * 0.087, -0.151, z + 0.012), (side * 0.117, -0.137, z + 0.021)], 0.002, bone, "lung_respiratory")
    tube(f"Pulmonary fissure {side}", [(side * 0.04, -0.14, 1.28), (side * 0.085, -0.153, 1.235), (side * 0.134, -0.123, 1.21)], 0.0014, liver_mat, "lung_respiratory")

heart = loft("Anatomical heart", [
    (1.21, 0.042, -0.156, 0.002, 0.004),
    (1.23, 0.026, -0.157, 0.026, 0.022),
    (1.27, 0.013, -0.159, 0.04, 0.03),
    (1.306, 0.008, -0.151, 0.03, 0.025),
    (1.317, 0.01, -0.149, 0.016, 0.016),
], heart_mat, "heart_vascular")
tube("Aortic arch", [(-0.003, -0.162, 1.292), (-0.017, -0.15, 1.342), (0.007, -0.147, 1.365), (0.027, -0.13, 1.335), (0.022, -0.083, 1.13)], 0.01, artery, "heart_vascular")
tube("Superior vena cava", [(-0.025, -0.154, 1.30), (-0.029, -0.151, 1.35), (-0.028, -0.10, 1.42)], 0.007, vein, "heart_vascular")
tube("Coronary artery", [(0.001, -0.183, 1.30), (0.012, -0.191, 1.275), (0.030, -0.185, 1.248), (0.04, -0.17, 1.229)], 0.0023, stomach_mat, "heart_vascular")

loft("Liver", [
    (1.07, -0.10, -0.13, 0.006, 0.009),
    (1.09, -0.081, -0.13, 0.046, 0.031),
    (1.128, -0.031, -0.13, 0.104, 0.037),
    (1.17, -0.045, -0.12, 0.09, 0.029),
    (1.185, -0.052, -0.105, 0.046, 0.008),
], liver_mat, "liver_biliary_pancreas")
ellipsoid("Gallbladder", (-0.048, -0.14, 1.09), (0.013, 0.013, 0.026), gland, "liver_biliary_pancreas")
tube("Stomach", [(0.04, -0.10, 1.16), (0.066, -0.124, 1.125), (0.073, -0.135, 1.085), (0.044, -0.144, 1.061), (0.002, -0.137, 1.075)], 0.028, stomach_mat, "stomach_upper_gi")
tube("Pancreas", [(-0.049, -0.11, 1.033), (-0.011, -0.115, 1.032), (0.057, -0.102, 1.047)], 0.011, stomach_mat, "liver_biliary_pancreas")
for side in (-1, 1):
    kidney = ellipsoid(f"Kidney {side}", (side * 0.112, -0.062, 1.052 + side * 0.013), (0.022, 0.03, 0.043), kidney_mat, "kidney_urinary")
    kidney.rotation_euler[1] = side * -0.18
    tube(f"Ureter {side}", [(side * 0.101, -0.091, 1.027), (side * 0.063, -0.083, 0.95), (side * 0.013, -0.075, 0.864)], 0.0026, stomach_mat, "kidney_urinary")
    ellipsoid(f"Adrenal gland {side}", (side * 0.11, -0.08, 1.10 + side * 0.013), (0.018, 0.012, 0.009), gland, "endocrine_metabolic")
    thyroid = ellipsoid(f"Thyroid lobe {side}", (side * 0.014, -0.10, 1.474), (0.012, 0.014, 0.019), gland, "endocrine_metabolic")

# Continuous intestinal curves give a recognizable colon and fine bowel loops.
colon = [(-0.072, -0.106, 0.899), (-0.087, -0.11, 0.95), (-0.082, -0.115, 1.015), (-0.045, -0.132, 1.022), (0, -0.135, 1.008), (0.045, -0.125, 1.022), (0.079, -0.11, 1.006), (0.085, -0.106, 0.937), (0.056, -0.118, 0.889), (0.013, -0.106, 0.892), (0, -0.095, 0.866)]
tube("Large intestine", colon, 0.014, stomach_mat, "intestine_colorectal")
for row in range(5):
    z = 0.91 + row * 0.020
    points = [(-0.059 + j * 0.0148, -0.118 - 0.009 * math.sin(j * 1.4 + row), z + 0.007 * math.sin(j * 1.5 + row * 0.8)) for j in range(9)]
    tube(f"Small intestine loop {row}", points, 0.0085, intestine_mat, "intestine_colorectal")
ellipsoid("Bladder", (0, -0.086, 0.852), (0.024, 0.02, 0.023), stomach_mat, "kidney_urinary")

# Clavicles and lymph nodes provide restrained supporting anatomical detail.
for side in (-1, 1):
    tube(f"Clavicle {side}", [(side * 0.014, -0.088, 1.425), (side * 0.071, -0.10, 1.438), (side * 0.157, -0.04, 1.418)], 0.005, bone, "bone_joint_muscle")
    for x, z in [(0.155, 1.33), (0.143, 1.295), (0.072, 0.87)]:
        ellipsoid(f"Lymph node {side} {z}", (side * x, -0.085, z), (0.005, 0.006, 0.009), gland, "blood_immune")

# Give the skin a soft cutaway window over the organs while retaining opaque
# contour, facial planes, limbs and hands. Local Position is in world meters.
nodes, links = skin.node_tree.nodes, skin.node_tree.links
shader = nodes.get("Principled BSDF")
output = nodes.get("Material Output")
position = nodes.new("ShaderNodeNewGeometry")
separate = nodes.new("ShaderNodeSeparateXYZ")
links.new(position.outputs["Position"], separate.inputs[0])
absolute_x = nodes.new("ShaderNodeMath")
absolute_x.operation = "ABSOLUTE"
links.new(separate.outputs["X"], absolute_x.inputs[0])
width = nodes.new("ShaderNodeMapRange")
width.clamp = True
width.inputs["From Min"].default_value = 0.09
width.inputs["From Max"].default_value = 0.165
width.inputs["To Min"].default_value = 0.10
width.inputs["To Max"].default_value = 1.0
links.new(absolute_x.outputs[0], width.inputs["Value"])
above = nodes.new("ShaderNodeMapRange")
above.clamp = True
above.interpolation_type = "SMOOTHSTEP"
above.inputs["From Min"].default_value = 0.79
above.inputs["From Max"].default_value = 0.9
links.new(separate.outputs["Z"], above.inputs["Value"])
below = nodes.new("ShaderNodeMapRange")
below.clamp = True
below.interpolation_type = "SMOOTHSTEP"
below.inputs["From Min"].default_value = 1.35
below.inputs["From Max"].default_value = 1.46
below.inputs["To Min"].default_value = 1
below.inputs["To Max"].default_value = 0
links.new(separate.outputs["Z"], below.inputs["Value"])
inside = nodes.new("ShaderNodeMath")
inside.operation = "MULTIPLY"
links.new(above.outputs[0], inside.inputs[0])
links.new(below.outputs[0], inside.inputs[1])
factor = nodes.new("ShaderNodeMix")
factor.data_type = "FLOAT"
factor.inputs[2].default_value = 1.0
links.new(inside.outputs[0], factor.inputs[0])
links.new(width.outputs["Result"], factor.inputs[3])
transparent = nodes.new("ShaderNodeBsdfTransparent")
mix = nodes.new("ShaderNodeMixShader")
scalp = nodes.new("ShaderNodeMapRange")
scalp.clamp = True
scalp.interpolation_type = "SMOOTHSTEP"
scalp.inputs["From Min"].default_value = 1.638
scalp.inputs["From Max"].default_value = 1.665
scalp.inputs["To Min"].default_value = 1
scalp.inputs["To Max"].default_value = 0.12
links.new(separate.outputs["Z"], scalp.inputs["Value"])
opacity = nodes.new("ShaderNodeMath")
opacity.operation = "MULTIPLY"
links.new(factor.outputs[0], opacity.inputs[0])
links.new(scalp.outputs[0], opacity.inputs[1])
links.new(opacity.outputs[0], mix.inputs[0])
links.new(transparent.outputs[0], mix.inputs[1])
links.new(shader.outputs[0], mix.inputs[2])
links.new(mix.outputs[0], output.inputs["Surface"])

world = bpy.data.worlds.new("Atlas studio")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.25, 0.32, 0.43, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
scene.world = world
for name, location, energy, color, size in [
    ("Key softbox", (-2, -3, 3), 260, (0.82, 0.9, 1), 3),
    ("Fill softbox", (2, -1.6, 1.5), 140, (0.64, 0.8, 1), 2.5),
    ("Rim softbox", (0.5, 1.4, 2.0), 300, (0.42, 0.70, 1), 2),
]:
    data = bpy.data.lights.new(name, "AREA")
    data.energy, data.color, data.shape, data.size = energy, color, "DISK", size
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector((0, 0, 0.95)) - obj.location).to_track_quat("-Z", "Y").to_euler()

camera_data = bpy.data.cameras.new("Anterior orthographic camera")
camera = bpy.data.objects.new("Anterior orthographic camera", camera_data)
scene.collection.objects.link(camera)
camera.location = (0, -6, 0.88)
camera.rotation_euler = (math.pi / 2, 0, 0)
camera_data.type, camera_data.ortho_scale = "ORTHO", 1.94
scene.camera = camera
scene.render.engine = "CYCLES"
scene.cycles.samples = 96
scene.cycles.use_denoising = True
try:
    preferences = bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type = "OPTIX"
    preferences.get_devices()
    for device in preferences.devices:
        device.use = device.type == "OPTIX"
    scene.cycles.device = "GPU" if any(device.type == "OPTIX" for device in preferences.devices) else "CPU"
except Exception:
    scene.cycles.device = "CPU"
scene.render.resolution_x, scene.render.resolution_y = 840, 1520
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
scene.render.image_settings.file_format = "WEBP"
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.quality = 88
scene.render.filepath = "//../src/frontend/assets/human-body.webp"
scene.view_settings.view_transform = "AgX"
scene["anatomy_note"] = "Illustrative organ placement for drug-region navigation; anterior view. Not a clinical atlas."
scene["reference"] = "body-atlas-reference.png — generated with the built-in imagegen tool; visual guidance only."
reference_path = DESIGN / "body-atlas-reference.png"
if reference_path.exists():
    reference = bpy.data.objects.new("Modeling reference (imagegen)", None)
    reference.empty_display_type = "IMAGE"
    reference.data = bpy.data.images.load(str(reference_path), check_existing=True)
    reference.data.pack()
    reference.location = (1.3, 0.3, 0.88)
    reference.rotation_euler = (math.pi / 2, 0, 0)
    reference.empty_display_size = 1.76
    reference.hide_render = True
    scene.collection.objects.link(reference)
for area in bpy.context.screen.areas:
    if area.type == "VIEW_3D":
        area.spaces.active.region_3d.view_perspective = "CAMERA"
bpy.ops.wm.save_as_mainfile(filepath=str(DESIGN / "body-atlas.blend"), compress=True)
bpy.ops.render.render(write_still=True)
print("DrugTree body atlas rendered", scene.render.filepath, "objects", len(scene.objects))
