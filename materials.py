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

    bark_color_out = None
    if settings.bark_image:
        tex = _image_node(nodes, settings.bark_image, "Bark Color")
        bark_color_out = tex.outputs["Color"]

        ao_image = getattr(settings, "bark_ao_image", None)
        if ao_image:
            ao_tex = _image_node(nodes, ao_image, "Bark AO", non_color=True)
            ao_mix = nodes.new("ShaderNodeMixRGB")
            ao_mix.name = "Bark AO Multiply"
            ao_mix.blend_type = "MULTIPLY"
            ao_mix.inputs[0].default_value = 1.0
            links.new(bark_color_out, ao_mix.inputs[1])
            links.new(ao_tex.outputs["Color"], ao_mix.inputs[2])
            bark_color_out = ao_mix.outputs["Color"]

        tint = nodes.new("ShaderNodeMixRGB")
        tint.name = "Bark Tint"
        tint.blend_type = "MULTIPLY"
        tint.inputs[0].default_value = 1.0
        tint.inputs[2].default_value = settings.bark_color
        links.new(bark_color_out, tint.inputs[1])
        links.new(tint.outputs["Color"], bsdf.inputs["Base Color"])

    roughness_image = getattr(settings, "bark_roughness_image", None)
    if roughness_image:
        rough = _image_node(nodes, roughness_image, "Bark Roughness", non_color=True)
        links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])

    normal_output = None
    if settings.bark_normal_image:
        normal_tex = _image_node(nodes, settings.bark_normal_image, "Bark Normal", non_color=True)
        normal = nodes.new("ShaderNodeNormalMap")
        normal.inputs["Strength"].default_value = 0.82
        links.new(normal_tex.outputs["Color"], normal.inputs["Color"])
        normal_output = normal.outputs["Normal"]

    height_image = getattr(settings, "bark_height_image", None)
    if height_image:
        height_tex = _image_node(nodes, height_image, "Bark Height", non_color=True)
        bump = nodes.new("ShaderNodeBump")
        bump.name = "Bark Micro Height"
        bump.inputs["Strength"].default_value = 0.24
        bump.inputs["Distance"].default_value = 0.10
        links.new(height_tex.outputs["Color"], bump.inputs["Height"])
        if normal_output:
            links.new(normal_output, bump.inputs["Normal"])
        normal_output = bump.outputs["Normal"]

    if normal_output:
        links.new(normal_output, bsdf.inputs["Normal"])

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
