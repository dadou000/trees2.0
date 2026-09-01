"""Species-specific atlas-cluster layouts that complement 3D foliage assembly."""

import math

from . import procedural_pbr


_PREVIOUS_VARIANT_LEAVES = None
_INSTALLED = False


def _weeping_sprig(profile, rng):
    """Create a botanically plausible pendulous willow shoot in one atlas cell.

    Leaf local +Y is the blade-tip direction in the rasterizer.  The old layout
    used angles close to zero, which therefore authored the leaves *up* the
    shoot even when the 3D card itself was hanging correctly.  This version
    solves every blade from an attachment point on the shoot and uses angles
    centred on pi, so the leaf tips point down with a modest alternate lateral
    divergence.

    Willow leaf size is deliberately nearly constant.  Variation comes mainly
    from attachment spacing, divergence, tone and a small shoot curvature.
    """
    count = max(7, int(profile.get("leaf_count", 8)))
    aspect = max(float(profile.get("leaf_aspect", 4.45)), 2.5)
    kind = profile["leaf_shape"]
    leaves = []

    # Keep enough empty border for antialiasing and for variants with slightly
    # longer blades.  Attachments progress from the young top of the shoot to
    # the lower end; the leaf blades themselves hang below those attachments.
    top_y = 0.78
    bottom_y = -0.48
    base_sy = 0.235

    for i in range(count):
        t = i / max(1, count - 1)
        # Mildly irregular internode spacing without the old schematic ladder.
        attach_y = top_y + (bottom_y - top_y) * t
        attach_y += rng.uniform(-0.018, 0.018) * (0.35 + 0.65 * math.sin(math.pi * t))

        # A subtle S-curve gives the central shoot an organic silhouette.  The
        # stem renderer joins these attachment points into the actual twig.
        shoot_x = (
            0.025 * math.sin(t * math.tau * 0.72 + 0.65)
            + 0.010 * math.sin(t * math.tau * 1.83 + 2.1)
            + rng.uniform(-0.006, 0.006)
        )

        side = 1.0 if i % 2 == 0 else -1.0
        # Around pi means down.  +/- divergence gives alternate right/left
        # blades while gravity remains the dominant direction.
        divergence = rng.uniform(0.34, 0.55)
        angle = math.pi - side * divergence + rng.uniform(-0.045, 0.045)
        direction_x = math.sin(angle)
        direction_y = math.cos(angle)

        # Willow leaves are quite consistent in size.  Keep random scale to
        # only a few percent; the lowest/oldest leaves are not inflated.
        sy = base_sy * rng.uniform(0.955, 1.045)
        sx = sy / aspect

        # _render_stems() treats the blade base as center - direction*sy*0.72.
        # Solve the center from the desired attachment point so petiole and leaf
        # meet exactly instead of drawing a long accidental brown connector.
        center_offset = sy * 0.73
        cx = shoot_x + direction_x * center_offset
        cy = attach_y + direction_y * center_offset

        leaves.append(procedural_pbr._leaf_record(
            cx,
            cy,
            angle,
            sx,
            sy,
            kind,
            rng.uniform(-0.16, 0.16),
            shoot_x,
            attach_y,
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
