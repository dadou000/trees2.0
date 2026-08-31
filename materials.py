import bpy


def _fresh_material(name):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    return mat


def _image_node(nodes, image, name, non_color=False):
    node = nodes.new("ShaderNodeTexImage")
    node.name = name
    node.label = name
    node.image = image
    node.interpolation = "Linear"
    if image and non_color:
        try:
            image.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
    return node


def create_bark_material(settings, suffix):
    mat = _fresh_material(f"Trees2_Bark_{suffix}")
    mat.diffuse_color = settings.bark_color
    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    bsdf = nodes.get("Principled BSDF")
    if not bsdf:
        return mat

    bsdf.inputs["Base Color"].default_value = settings.bark_color
    bsdf.inputs["Roughness"].default_value = 0.86

    if settings.bark_image:
        tex = _image_node(nodes, settings.bark_image, "Bark Color")
        tint = nodes.new("ShaderNodeMixRGB")
        tint.blend_type = "MULTIPLY"
        tint.inputs[0].default_value = 1.0
        tint.inputs[2].default_value = settings.bark_color
        links.new(tex.outputs["Color"], tint.inputs[1])
        links.new(tint.outputs["Color"], bsdf.inputs["Base Color"])

    if settings.bark_normal_image:
        normal_tex = _image_node(nodes, settings.bark_normal_image, "Bark Normal", non_color=True)
        normal = nodes.new("ShaderNodeNormalMap")
        normal.inputs["Strength"].default_value = 0.75
        links.new(normal_tex.outputs["Color"], normal.inputs["Color"])
        links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])

    return mat


def create_leaf_material(settings, suffix):
    mat = _fresh_material(f"Trees2_Leaves_{suffix}")
    mat.diffuse_color = settings.leaf_tint
    mat.use_backface_culling = False
    mat.surface_render_method = "DITHERED"
    mat.use_transparent_shadow = True

    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    bsdf = nodes.get("Principled BSDF")
    if not bsdf:
        return mat

    bsdf.inputs["Roughness"].default_value = 0.72
    bsdf.inputs["Base Color"].default_value = settings.leaf_tint

    if settings.leaf_image:
        tex = _image_node(nodes, settings.leaf_image, "Leaf Atlas")
        tint = nodes.new("ShaderNodeMixRGB")
        tint.blend_type = "MULTIPLY"
        tint.inputs[0].default_value = 1.0
        tint.inputs[2].default_value = settings.leaf_tint
        links.new(tex.outputs["Color"], tint.inputs[1])
        links.new(tint.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])

    if settings.leaf_roughness_image:
        rough = _image_node(nodes, settings.leaf_roughness_image, "Leaf Roughness", non_color=True)
        links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])

    if settings.leaf_normal_image:
        normal_tex = _image_node(nodes, settings.leaf_normal_image, "Leaf Normal", non_color=True)
        normal = nodes.new("ShaderNodeNormalMap")
        normal.inputs["Strength"].default_value = 0.55
        links.new(normal_tex.outputs["Color"], normal.inputs["Color"])
        links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])

    return mat
