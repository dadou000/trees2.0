"""Weeping-willow canopy architecture helpers.

The generic tree skeleton remains authoritative for woody geometry.  This module
adds a cheap, species-specific *virtual branchlet* layer by exposing selected
living scaffold/secondary/tertiary branches as additional foliage anchors.

This addresses a limitation of the generic generator: foliage normally grows
only from deepest terminal branches.  Mature weeping willows carry dense,
pendulous leafy shoots all along the outer halves of scaffold limbs, so a pure
terminal-only population leaves long bare spokes and an empty crown.

No extra branch mesh is created here.  The selected branches only receive
metadata and are appended to the terminal list consumed by smart foliage
assembly, preserving the existing Geometry Nodes instancing architecture.
"""

import math

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False


def _stable_unit(seed, value):
    x = (int(value) ^ int(seed) ^ 0x9E3779B9) & 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 0x7FEB352D) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 0x846CA68B) & 0xFFFFFFFF
    x ^= x >> 16
    return x / 4294967296.0


def _anchor_metadata(level):
    # Heavy scaffold limbs only get sparse, short virtual branchlets; finer
    # branches contribute progressively more crown fill.
    if level <= 1:
        return 0.34, 0.54, 2
    if level == 2:
        return 0.58, 0.68, 3
    return 0.48, 0.78, 2


def _generate_with_willow_anchors(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    existing_ids = {int(branch.get("id", -1)) for branch in terminals}
    extras = []
    height = max(float(settings.height), 1.0e-5)
    radial_reference = max(float(settings.branch_length), float(settings.base_radius) * 4.0, 1.0e-4)

    for branch in branches:
        branch_id = int(branch.get("id", -1))
        level = int(branch.get("level", 0))
        if branch_id in existing_ids or level < 1 or level > 3 or branch.get("dead", False):
            continue
        if len(branch.get("points", ())) < 2:
            continue

        # Evaluate the outer half rather than only the endpoint. This makes the
        # selection robust when a branch curls back inward near its tip.
        p_mid, _r, _t = generator._point_on_polyline(branch, 0.62)
        p_end = branch["points"][-1][0]
        h = max(float(p_mid.z), float(p_end.z)) / height
        radial = max(
            math.hypot(float(p_mid.x), float(p_mid.y)),
            math.hypot(float(p_end.x), float(p_end.y)),
        ) / radial_reference

        # Do not repopulate the low central trunk region. Favor exposed outer
        # branches, but keep enough interior supports to create a dark canopy.
        if h < 0.27:
            continue
        probability = {1: 0.88, 2: 0.76, 3: 0.50}[level]
        probability *= 0.78 + 0.30 * min(1.0, radial)
        probability *= 0.76 + 0.30 * min(1.0, max(0.0, (h - 0.27) / 0.50))
        if _stable_unit(int(settings.seed) ^ 0x51A10A, branch_id * 53 + level * 17) > min(0.98, probability):
            continue

        weight, length_scale, max_bundles = _anchor_metadata(level)
        branch["willow_aux_anchor"] = True
        branch["willow_anchor_weight"] = float(weight)
        branch["willow_length_scale"] = float(length_scale)
        branch["willow_fill_only"] = True
        branch["willow_max_bundles"] = int(max_bundles)
        branch["willow_anchor_level"] = int(level)
        extras.append(branch)
        existing_ids.add(branch_id)

    # Store lightweight diagnostics on the trunk for Blender inspection.
    try:
        branches[0]["willow_virtual_anchor_count"] = len(extras)
        branches[0]["willow_real_terminal_count"] = len(terminals)
    except Exception:
        pass

    return branches, list(terminals) + extras


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_with_willow_anchors
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
