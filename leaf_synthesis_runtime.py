"""Runtime integration and compositing fixes for high-fidelity leaf synthesis."""

import math

import numpy as np
import bpy

from . import generator, leaf_synthesis, procedural_pbr


_PREVIOUS_RENDER_LEAF = None
_PREVIOUS_GENERATE = None
_PREVIOUS_CREATE_LEAF_MATERIAL = None
_INSTALLED = False


def _render_leaf_fixed(cell, leaf, profile, pbr, style, seed, resolution_scale):
    ls = leaf_synthesis
    cx = float(leaf["cx"])
    cy = float(leaf["cy"])
    angle = float(leaf["angle"])
    sx = max(0.004, float(leaf["sx"]))
    sy = max(0.004, float(leaf["sy"]))
    kind = str(leaf["shape"])

    ca = math.cos(angle)
    sa = math.sin(angle)
    extent_x = abs(ca) * sx + abs(sa) * sy
    extent_y = abs(sa) * sx + abs(ca) * sy

    size = cell["size"]
    pad = 3.5 / max(1.0, resolution_scale)
    px0 = max(0, int(math.floor(((cx - extent_x + 1.0) * 0.5) * size - pad)))
    px1 = min(size, int(math.ceil(((cx + extent_x + 1.0) * 0.5) * size + pad)))
    py0 = max(0, int(math.floor(((cy - extent_y + 1.0) * 0.5) * size - pad)))
    py1 = min(size, int(math.ceil(((cy + extent_y + 1.0) * 0.5) * size + pad)))
    if px1 <= px0 or py1 <= py0:
        return

    xs = ((np.arange(px0, px1, dtype=np.float32) + 0.5) / size) * 2.0 - 1.0
    ys = ((np.arange(py0, py1, dtype=np.float32) + 0.5) / size) * 2.0 - 1.0
    x, y = np.meshgrid(xs, ys)
    dx = x - cx
    dy = y - cy
    u = (ca * dx + sa * dy) / sx
    v = (-sa * dx + ca * dy) / sy

    pixel_width = 2.5 / max(16.0, min(sx, sy) * size)
    alpha, half = ls._shape_alpha(kind, u, v, profile, pbr.leaf_detail, pixel_width)
    alpha = ls._damage_mask(u, v, alpha, profile, pbr.leaf_detail, seed)
    if float(alpha.max()) <= 0.001:
        return

    vein, midrib = ls._vein_field(kind, u, v, half, style, pbr.leaf_detail)
    relief, edge_band, micro = ls._leaf_surface(
        kind, u, v, half, alpha, vein, midrib, profile, pbr, style, seed
    )
    rgb = ls._leaf_color(
        kind, u, v, alpha, vein, edge_band, micro,
        profile, style, leaf.get("tone", 0.0), seed,
    )

    base_roughness = float(profile.get("leaf_roughness", 0.64))
    rough = (
        base_roughness
        + micro * 0.055
        + edge_band * 0.028
        - vein * 0.035
        - float(style["wax"]) * 0.16
    )
    rough = np.clip(rough, 0.28, 0.94).astype(np.float32)

    trans = float(style["translucency"]) * (1.0 - vein * 0.38 - midrib * 0.22)
    trans *= 0.90 + 0.10 * (1.0 - edge_band)
    trans = np.clip(trans, 0.0, 1.0).astype(np.float32)

    dst_alpha = cell["alpha"][py0:py1, px0:px1]
    out_alpha = alpha + dst_alpha * (1.0 - alpha)
    safe = np.maximum(out_alpha, 1.0e-6)
    new_weight = alpha / safe
    old_weight = dst_alpha * (1.0 - alpha) / safe

    rgb_dst = cell["rgb"][py0:py1, px0:px1]
    rgb_dst[...] = rgb * new_weight[..., None] + rgb_dst * old_weight[..., None]

    depth_bias = ((seed * 0.754877666) % 1.0) * 0.018
    height_dst = cell["height"][py0:py1, px0:px1]
    height_dst[...] = (relief + depth_bias) * new_weight + height_dst * old_weight

    rough_dst = cell["rough"][py0:py1, px0:px1]
    rough_dst[...] = rough * new_weight + rough_dst * old_weight

    trans_dst = cell["trans"][py0:py1, px0:px1]
    trans_dst[...] = trans * new_weight + trans_dst * old_weight

    dst_alpha[...] = out_alpha


def _generate_and_assign_translucency(context, species=None):
    result = _PREVIOUS_GENERATE(context, species)
    pbr = context.scene.trees2_pbr_settings
    settings = context.scene.trees2_settings
    leaf = result.get("leaf") if isinstance(result, dict) else None
    if pbr.auto_assign and leaf and hasattr(settings, "leaf_translucency_image"):
        settings.leaf_translucency_image = leaf.get("translucency")
    elif pbr.auto_assign and hasattr(settings, "leaf_translucency_image") and not leaf:
        settings.leaf_translucency_image = None
    return result


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


def _create_leaf_material_with_translucency(settings, suffix):
    mat = _PREVIOUS_CREATE_LEAF_MATERIAL(settings, suffix)
    image = getattr(settings, "leaf_translucency_image", None)
    if image is None or not getattr(mat, "use_nodes", False):
        return mat

    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        return mat

    socket = (
        bsdf.inputs.get("Subsurface Weight")
        or bsdf.inputs.get("Subsurface")
        or bsdf.inputs.get("Transmission Weight")
    )
    if socket is None:
        return mat

    tex = _image_node(nodes, image, "Leaf Translucency", non_color=True)
    strength = nodes.new("ShaderNodeMath")
    strength.name = "Leaf Translucency Strength"
    strength.label = "Leaf Translucency Strength"
    strength.operation = "MULTIPLY"
    strength.inputs[1].default_value = 0.115
    links.new(tex.outputs["Color"], strength.inputs[0])
    links.new(strength.outputs[0], socket)

    # Keep the thin-leaf scattering radius conservative and chlorophyll-biased
    # when the current Principled version exposes these inputs.
    radius = bsdf.inputs.get("Subsurface Radius")
    if radius is not None:
        try:
            radius.default_value = (0.55, 1.0, 0.36)
        except Exception:
            pass
    scale = bsdf.inputs.get("Subsurface Scale")
    if scale is not None:
        scale.default_value = 0.035
    return mat


def install():
    global _PREVIOUS_RENDER_LEAF, _PREVIOUS_GENERATE
    global _PREVIOUS_CREATE_LEAF_MATERIAL, _INSTALLED
    if _INSTALLED:
        return

    _PREVIOUS_RENDER_LEAF = leaf_synthesis._render_leaf
    leaf_synthesis._render_leaf = _render_leaf_fixed

    _PREVIOUS_GENERATE = procedural_pbr.generate_species_pbr
    procedural_pbr.generate_species_pbr = _generate_and_assign_translucency

    _PREVIOUS_CREATE_LEAF_MATERIAL = generator.create_leaf_material
    generator.create_leaf_material = _create_leaf_material_with_translucency
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    leaf_synthesis._render_leaf = _PREVIOUS_RENDER_LEAF
    procedural_pbr.generate_species_pbr = _PREVIOUS_GENERATE
    generator.create_leaf_material = _PREVIOUS_CREATE_LEAF_MATERIAL
    _INSTALLED = False
