"""Species-specific atlas-cluster layouts that complement 3D foliage assembly."""

from . import procedural_pbr


_PREVIOUS_VARIANT_LEAVES = None
_INSTALLED = False


def _weeping_sprig(profile, rng):
    """Create one narrow alternate-leaved willow sprig inside an atlas cell.

    Salix foliage is simple, alternate and linear-lanceolate.  A vertical sprig
    is therefore a much better batched-card primitive than a radial leaf ball;
    the 3D assembly system can chain these cards into long pendulous curtains.
    """
    count = max(5, int(profile.get("leaf_count", 8)))
    aspect = max(float(profile.get("leaf_aspect", 4.45)), 1.0)
    leaves = []
    for i in range(count):
        t = i / max(1, count - 1)
        y = -0.52 + 1.02 * t
        side = -1.0 if i % 2 else 1.0
        # Leaves remain mostly aligned with the hanging shoot, with alternate
        # divergence rather than a starburst around the card center.
        angle = side * rng.uniform(0.42, 0.72) + rng.uniform(-0.06, 0.06)
        sy = rng.uniform(0.20, 0.29)
        sx = sy / aspect
        cx = side * rng.uniform(0.055, 0.115)
        leaves.append(procedural_pbr._leaf_record(
            cx,
            y,
            angle,
            sx,
            sy,
            profile["leaf_shape"],
            rng.uniform(-0.10, 0.10),
            0.0,
            y - 0.055,
        ))
    return leaves


def _variant_leaves(profile, rng):
    if profile.get("arrangement") == "WEEPING_SPRIG":
        return _weeping_sprig(profile, rng)
    return _PREVIOUS_VARIANT_LEAVES(profile, rng)


def install():
    global _PREVIOUS_VARIANT_LEAVES, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_VARIANT_LEAVES = procedural_pbr._variant_leaves
    procedural_pbr._variant_leaves = _variant_leaves
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    procedural_pbr._variant_leaves = _PREVIOUS_VARIANT_LEAVES
    _INSTALLED = False
