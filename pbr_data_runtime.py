"""Runtime integration for high-quality generated PBR data maps.

This module deliberately stays small and generic. It fixes two practical issues:

1. Generated Blender images are explicitly updated before a second save. This
   makes sure foreach_set() pixel changes are committed to the image buffer
   before PNG export on Blender builds/drivers that otherwise leave stale data.
2. Generated bark maps can carry self-describing material-response metadata.
   The material builder consumes those values instead of applying one global
   normal/bump strength to every species and every generator revision.
"""

from . import generator, procedural_pbr


_PREVIOUS_NEW_IMAGE = None
_PREVIOUS_CREATE_BARK_MATERIAL = None
_INSTALLED = False


def _new_image_committed(name, width, height, pixels, filepath, non_color=False, pack=False):
    image = _PREVIOUS_NEW_IMAGE(name, width, height, pixels, filepath, non_color, pack)
    # foreach_set writes the raw buffer quickly, but update() is the explicit API
    # step that tells Blender the image data changed. Save again after the update
    # so data maps are not dependent on implicit refresh behaviour.
    try:
        image.update()
    except Exception:
        pass
    try:
        image.alpha_mode = "STRAIGHT"
    except Exception:
        pass
    try:
        image.save()
    except Exception:
        pass
    return image


def _create_bark_material_metadata(settings, suffix):
    material = _PREVIOUS_CREATE_BARK_MATERIAL(settings, suffix)
    if material is None or not getattr(material, "use_nodes", False):
        return material

    nodes = material.node_tree.nodes

    normal_image = getattr(settings, "bark_normal_image", None)
    normal_node = nodes.get("Bark Normal Decode")
    if normal_image is not None and normal_node is not None:
        try:
            strength = float(normal_image.get("trees2_normal_node_strength", 0.30))
            socket = normal_node.inputs.get("Strength")
            if socket is not None:
                socket.default_value = max(0.0, min(2.0, strength))
        except Exception:
            pass

    height_image = getattr(settings, "bark_height_image", None)
    bump = nodes.get("Bark Micro Height")
    if height_image is not None and bump is not None:
        try:
            strength = float(height_image.get("trees2_bump_strength", 0.075))
            distance = float(height_image.get("trees2_bump_distance", 0.018))
            if bump.inputs.get("Strength") is not None:
                bump.inputs["Strength"].default_value = max(0.0, min(1.0, strength))
            if bump.inputs.get("Distance") is not None:
                bump.inputs["Distance"].default_value = max(0.0, min(0.25, distance))
        except Exception:
            pass

    return material


def install():
    global _PREVIOUS_NEW_IMAGE, _PREVIOUS_CREATE_BARK_MATERIAL, _INSTALLED
    if _INSTALLED:
        return

    _PREVIOUS_NEW_IMAGE = procedural_pbr._new_image
    procedural_pbr._new_image = _new_image_committed

    _PREVIOUS_CREATE_BARK_MATERIAL = generator.create_bark_material
    generator.create_bark_material = _create_bark_material_metadata
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    procedural_pbr._new_image = _PREVIOUS_NEW_IMAGE
    generator.create_bark_material = _PREVIOUS_CREATE_BARK_MATERIAL
    _INSTALLED = False
