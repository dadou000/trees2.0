"""Coherent post-motion crown-width correction for mature weeping willow.

The target crown is substantially wider than the v0.8.6 fountain-like result.
This stage expands complete top-level scaffold subtrees around their trunk
attachment point. Descendants receive the exact same affine transform as their
parent scaffold, so branch junctions stay connected.

Co-dominant leaders receive the strongest horizontal expansion and a small
vertical compression; ordinary primary scaffolds receive a milder correction.
"""

from mathutils import Vector

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False


_LOD_SPREAD = {
    "LOD0": (1.10, 1.24),
    "LOD1": (1.09, 1.21),
    "LOD2": (1.07, 1.16),
    "LOD3": (1.04, 1.10),
    "LOD4": (1.00, 1.04),
}


def _children_map(branches):
    result = {}
    for branch in branches:
        result.setdefault(int(branch.get("parent_id", -1)), []).append(branch)
    return result


def _subtree(root, children):
    output = []
    stack = [root]
    while stack:
        branch = stack.pop()
        output.append(branch)
        stack.extend(children.get(int(branch.get("id", -1)), ()))
    return output


def _transform_subtree(branches, origin, horizontal_scale, vertical_scale):
    for branch in branches:
        new_points = []
        for point, radius in branch.get("points", ()):
            offset = point - origin
            transformed = Vector((
                origin.x + offset.x * horizontal_scale,
                origin.y + offset.y * horizontal_scale,
                origin.z + offset.z * vertical_scale,
            ))
            new_points.append((transformed, float(radius)))
        if new_points:
            branch["points"] = new_points
            branch["length"] = generator._polyline_length(branch)
            branch["willow_crown_spread"] = True


def _generate_with_spread(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW" or not branches:
        return branches, terminals

    ordinary_scale, leader_scale = _LOD_SPREAD.get(str(settings.lod), _LOD_SPREAD["LOD0"])
    children = _children_map(branches)
    roots = [
        branch for branch in branches
        if int(branch.get("level", 0)) == 1
        and int(branch.get("parent_id", -1)) == 0
        and not branch.get("willow_root_buttress", False)
        and len(branch.get("points", ())) >= 2
    ]

    transformed_ids = set()
    for root in roots:
        subtree = [branch for branch in _subtree(root, children) if int(branch.get("id", -1)) not in transformed_ids]
        if not subtree:
            continue
        origin = root["points"][0][0].copy()
        if root.get("willow_codominant", False):
            horizontal_scale = leader_scale
            vertical_scale = 0.91
        else:
            horizontal_scale = ordinary_scale
            vertical_scale = 0.96
        _transform_subtree(subtree, origin, horizontal_scale, vertical_scale)
        transformed_ids.update(int(branch.get("id", -1)) for branch in subtree)

    try:
        trunk = branches[0]
        trunk["willow_crown_spread_version"] = 1
        trunk["willow_crown_spread_branch_count"] = len(transformed_ids)
        trunk["willow_crown_spread_scale"] = float(ordinary_scale)
        trunk["willow_codominant_spread_scale"] = float(leader_scale)
    except Exception:
        pass

    # Terminals are references to the same branch dictionaries and already see
    # the transformed positions.
    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_with_spread
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
