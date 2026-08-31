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
    """Set a Principled input across Blender naming changes."""
    for name in names:
        socket = bsdf.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return socket
    return None


def _configure_dielectric(bsdf, *, roughness, ior=1.45, ior_level=0.32):
    """Explicitly keep vegetation materials in the dielectric/non-metal regime."""
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


def create_bark_material(settings, suffix):
    mat = _fresh_material(f"Trees2_Bark_{suffix}")
    mat.diffuse_color = settings.bark_color
    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    bsdf = nodes.get("Principled BSDF")
    if not bsdf:
        return mat

    # Bark is a rough dielectric. Explicit values avoid a glossy/metallic look
    # under Material Preview HDRIs even when generated normals are detailed.
    _configure_dielectric(bsdf, roughness=0.84, ior=1.47, ior_level=0.24)
    bsdf.inputs["Base Color"].default_value = settings.bark_color

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
            # Do not multiply full AO strength into albedo; real bark still
            # receives direct light inside fissures. 0.62 keeps crevices readable.
            ao_mix.inputs[2].default_value = (0.62, 0.62, 0.62, 1.0)
            links.new(bark_color_out, ao_mix.inputs[1])
            ao_strength = nodes.new("ShaderNodeMixRGB")
            ao_strength.name = "Bark AO Strength"
            ao_strength.blend_type = "MULTIPLY"
            ao_strength.inputs[0].default_value = 0.42
            ao_strength.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)
            links.new(ao_tex.outputs["Color"], ao_strength.inputs[2])
            links.new(ao_strength.outputs["Color"], ao_mix.inputs[2])
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
        rough_out = _roughness_floor(
            nodes,
            links,
            rough.outputs["Color"],
            0.68,
            "Bark Roughness Floor",
        )
        links.new(rough_out, bsdf.inputs["Roughness"])

    normal_output = None
    if settings.bark_normal_image:
        normal_tex = _image_node(nodes, settings.bark_normal_image, "Bark Normal", non_color=True)
        normal = nodes.new("ShaderNodeNormalMap")
        normal.name = "Bark Normal Decode"
        # Generated normal maps already contain relief. A second large strength
        # multiplier was the main cause of the chrome-like highlights.
        normal.inputs["Strength"].default_value = 0.30
        links.new(normal_tex.outputs["Color"], normal.inputs["Color"])
        normal_output = normal.outputs["Normal"]

    height_image = getattr(settings, "bark_height_image", None)
    if height_image:
        height_tex = _image_node(nodes, height_image, "Bark Height", non_color=True)
        bump = nodes.new("ShaderNodeBump")
        bump.name = "Bark Micro Height"
        # Height is micro-relief only. The mesh supplies macro bark silhouette.
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

    # Leaves are dielectric and can be somewhat glossy, but never mirror-like.
    _configure_dielectric(bsdf, roughness=0.72, ior=1.43, ior_level=0.28)
    bsdf.inputs["Base Color"].default_value = settings.leaf_tint

    if settings.leaf_image:
        tex = _image_node(nodes, settings.leaf_image, "Leaf Atlas")
        tint = nodes.new("ShaderNodeMixRGB")
        tint.name = "Leaf Tint"
        tint.blend_type = "MULTIPLY"
        tint.inputs[0].default_value = 1.0
        tint.inputs[2].default_value = settings.leaf_tint
        links.new(tex.outputs["Color"], tint.inputs[1])
        links.new(tint.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])

    if settings.leaf_roughness_image:
        rough = _image_node(nodes, settings.leaf_roughness_image, "Leaf Roughness", non_color=True)
        rough_out = _roughness_floor(
            nodes,
            links,
            rough.outputs["Color"],
            0.56,
            "Leaf Roughness Floor",
        )
        links.new(rough_out, bsdf.inputs["Roughness"])

    if settings.leaf_normal_image:
        normal_tex = _image_node(nodes, settings.leaf_normal_image, "Leaf Normal", non_color=True)
        normal = nodes.new("ShaderNodeNormalMap")
        normal.name = "Leaf Normal Decode"
        normal.inputs["Strength"].default_value = 0.22
        links.new(normal_tex.outputs["Color"], normal.inputs["Color"])

        # A tangent normal map authored for the front of a card can create
        # inverted, razor-bright highlights on the back. Blend it out on
        # backfaces and let Blender use the geometric backface normal there.
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
