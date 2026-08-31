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


def _set_input(bsdf, names, value):
    for name in names:
        socket = bsdf.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return socket
    return None


def _configure_dielectric(bsdf, *, roughness, ior=1.45, ior_level=0.32):
    _set_input(bsdf, ("Metallic",), 0.0)
    _set_input(bsdf, ("Roughness",), roughness)
    _set_input(bsdf, ("IOR",), ior)
    _set_input(bsdf, ("IOR Level", "Specular IOR Level", "Specular"), ior_level)
    _set_input(bsdf, ("Coat Weight", "Coat"), 0.0)
    _set_input(bsdf, ("Coat Roughness",), 1.0)


def _roughness_floor(nodes, links, source, minimum, name):
    floor = nodes.new("ShaderNodeMath")
    floor.name = name
    floor.label = name
    floor.operation = "MAXIMUM"
    floor.inputs[1].default_value = minimum
    links.new(source, floor.inputs[0])
    return floor.outputs[0]


def _authoritative_color(nodes, links, texture_output, tree_color, *,
                         detail_dark, detail_light, species_influence,
                         respect_tree_color, name):
    """Use image luminance as detail while keeping the tree color authoritative.

    The raw generated species color can be blended back slightly, but the
    default path preserves the user's/preset's foliage or trunk hue.
    """
    if not respect_tree_color:
        return texture_output

    detail = nodes.new("ShaderNodeValToRGB")
    detail.name = f"{name} Detail"
    detail.label = f"{name} Detail"
    detail.color_ramp.elements[0].position = 0.0
    detail.color_ramp.elements[0].color = (detail_dark, detail_dark, detail_dark, 1.0)
    detail.color_ramp.elements[1].position = 1.0
    detail.color_ramp.elements[1].color = (detail_light, detail_light, detail_light, 1.0)
    links.new(texture_output, detail.inputs["Fac"])

    tint = nodes.new("ShaderNodeRGB")
    tint.name = f"{name} Tree Color"
    tint.label = f"{name} Tree Color"
    tint.outputs[0].default_value = tree_color

    multiply = nodes.new("ShaderNodeMixRGB")
    multiply.name = f"{name} Color x Detail"
    multiply.label = f"{name} Color x Detail"
    multiply.blend_type = "MULTIPLY"
    multiply.inputs[0].default_value = 1.0
    links.new(tint.outputs["Color"], multiply.inputs[1])
    links.new(detail.outputs["Color"], multiply.inputs[2])
    result = multiply.outputs["Color"]

    influence = max(0.0, min(1.0, float(species_influence)))
    if influence > 0.0001:
        hue_mix = nodes.new("ShaderNodeMixRGB")
        hue_mix.name = f"{name} Species Hue"
        hue_mix.label = f"{name} Species Hue ({influence:.2f})"
        hue_mix.blend_type = "MIX"
        hue_mix.inputs[0].default_value = influence
        links.new(result, hue_mix.inputs[1])
        links.new(texture_output, hue_mix.inputs[2])
        result = hue_mix.outputs["Color"]
    return result


def _tree_color_options(settings):
    respect = bool(getattr(settings, "pbr_respect_tree_colors", True))
    influence = float(getattr(settings, "pbr_species_color_influence", 0.10))
    return respect, influence


def create_bark_material(settings, suffix):
    mat = _fresh_material(f"Trees2_Bark_{suffix}")
    mat.diffuse_color = settings.bark_color
    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    bsdf = nodes.get("Principled BSDF")
    if not bsdf:
        return mat

    _configure_dielectric(bsdf, roughness=0.84, ior=1.47, ior_level=0.24)
    bsdf.inputs["Base Color"].default_value = settings.bark_color
    respect, influence = _tree_color_options(settings)

    bark_color_out = None
    if settings.bark_image:
        tex = _image_node(nodes, settings.bark_image, "Bark Color")
        bark_color_out = _authoritative_color(
            nodes,
            links,
            tex.outputs["Color"],
            settings.bark_color,
            detail_dark=0.55,
            detail_light=1.12,
            species_influence=influence,
            respect_tree_color=respect,
            name="Bark",
        )

        ao_image = getattr(settings, "bark_ao_image", None)
        if ao_image:
            ao_tex = _image_node(nodes, ao_image, "Bark AO", non_color=True)
            ao_strength = nodes.new("ShaderNodeMixRGB")
            ao_strength.name = "Bark AO Strength"
            ao_strength.blend_type = "MIX"
            ao_strength.inputs[0].default_value = 0.34
            ao_strength.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)
            links.new(ao_tex.outputs["Color"], ao_strength.inputs[2])

            ao_multiply = nodes.new("ShaderNodeMixRGB")
            ao_multiply.name = "Bark AO Multiply"
            ao_multiply.blend_type = "MULTIPLY"
            ao_multiply.inputs[0].default_value = 1.0
            links.new(bark_color_out, ao_multiply.inputs[1])
            links.new(ao_strength.outputs["Color"], ao_multiply.inputs[2])
            bark_color_out = ao_multiply.outputs["Color"]

        links.new(bark_color_out, bsdf.inputs["Base Color"])

    roughness_image = getattr(settings, "bark_roughness_image", None)
    if roughness_image:
        rough = _image_node(nodes, roughness_image, "Bark Roughness", non_color=True)
        rough_out = _roughness_floor(nodes, links, rough.outputs["Color"], 0.68, "Bark Roughness Floor")
        links.new(rough_out, bsdf.inputs["Roughness"])

    normal_output = None
    if settings.bark_normal_image:
        normal_tex = _image_node(nodes, settings.bark_normal_image, "Bark Normal", non_color=True)
        normal = nodes.new("ShaderNodeNormalMap")
        normal.name = "Bark Normal Decode"
        normal.inputs["Strength"].default_value = 0.30
        links.new(normal_tex.outputs["Color"], normal.inputs["Color"])
        normal_output = normal.outputs["Normal"]

    height_image = getattr(settings, "bark_height_image", None)
    if height_image:
        height_tex = _image_node(nodes, height_image, "Bark Height", non_color=True)
        bump = nodes.new("ShaderNodeBump")
        bump.name = "Bark Micro Height"
        bump.inputs["Strength"].default_value = 0.075
        bump.inputs["Distance"].default_value = 0.018
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

    _configure_dielectric(bsdf, roughness=0.72, ior=1.43, ior_level=0.28)
    bsdf.inputs["Base Color"].default_value = settings.leaf_tint
    respect, influence = _tree_color_options(settings)

    if settings.leaf_image:
        tex = _image_node(nodes, settings.leaf_image, "Leaf Atlas")
        leaf_color = _authoritative_color(
            nodes,
            links,
            tex.outputs["Color"],
            settings.leaf_tint,
            detail_dark=0.68,
            detail_light=1.14,
            species_influence=influence,
            respect_tree_color=respect,
            name="Foliage",
        )
        links.new(leaf_color, bsdf.inputs["Base Color"])
        # The species atlas alpha remains absolute: it defines the actual leaf
        # silhouette even when its RGB hue is replaced by the tree color.
        links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])

    if settings.leaf_roughness_image:
        rough = _image_node(nodes, settings.leaf_roughness_image, "Leaf Roughness", non_color=True)
        rough_out = _roughness_floor(nodes, links, rough.outputs["Color"], 0.56, "Leaf Roughness Floor")
        links.new(rough_out, bsdf.inputs["Roughness"])

    if settings.leaf_normal_image:
        normal_tex = _image_node(nodes, settings.leaf_normal_image, "Leaf Normal", non_color=True)
        normal = nodes.new("ShaderNodeNormalMap")
        normal.name = "Leaf Normal Decode"
        normal.inputs["Strength"].default_value = 0.22
        links.new(normal_tex.outputs["Color"], normal.inputs["Color"])

        geometry = nodes.new("ShaderNodeNewGeometry")
        geometry.name = "Leaf Two-Sided Geometry"
        mix = nodes.new("ShaderNodeMix")
        mix.name = "Leaf Two-Sided Normal"
        mix.data_type = "VECTOR"
        links.new(geometry.outputs["Backfacing"], mix.inputs[0])
        links.new(normal.outputs["Normal"], mix.inputs[4])
        links.new(geometry.outputs["Normal"], mix.inputs[5])
        links.new(mix.outputs[1], bsdf.inputs["Normal"])

    return mat
