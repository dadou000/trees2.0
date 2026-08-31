import bpy


def _fresh_material(name):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    return mat


def create_bark_material(settings, suffix):
    mat = _fresh_material(f"Trees2_Bark_{suffix}")
    mat.diffuse_color = settings.bark_color
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = settings.bark_color
        bsdf.inputs["Roughness"].default_value = 0.86
    return mat


def create_leaf_material(settings, suffix):
    mat = _fresh_material(f"Trees2_Leaves_{suffix}")
    mat.diffuse_color = settings.leaf_tint
    mat.use_backface_culling = False
    mat.surface_render_method = "DITHERED"

    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    bsdf = nodes.get("Principled BSDF")
    if not bsdf:
        return mat

    bsdf.inputs["Roughness"].default_value = 0.72
    bsdf.inputs["Base Color"].default_value = settings.leaf_tint

    if settings.leaf_image:
        tex = nodes.new("ShaderNodeTexImage")
        tex.name = "Leaf Atlas"
        tex.label = "Leaf Atlas"
        tex.image = settings.leaf_image
        tex.interpolation = "Linear"

        tint = nodes.new("ShaderNodeMixRGB")
        tint.blend_type = "MULTIPLY"
        tint.inputs[0].default_value = 1.0
        tint.inputs[2].default_value = settings.leaf_tint
        links.new(tex.outputs["Color"], tint.inputs[1])
        links.new(tint.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])

    return mat
