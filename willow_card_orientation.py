"""Lock willow sprig cards to the atlas root/tip convention.

The willow atlas is authored with the shoot root at high V (card local +Z) and
leaf/shoot tips toward low V (card local -Z).  The weeping foliage generators,
however, build their card frame from a world-space root->tip direction.  Mapping
that direction to local +Z reverses the texture: the root ends up at the bottom
of the hanging card and the leaf tips point back upward.

This final foliage-record wrapper fixes the convention in one place by rotating
willow cards 180 degrees around their *local X axis*.  Local X is the card
normal, so the visible plane and outward-facing normal are preserved while local
Y/Z (and therefore the atlas vertical axis) are reversed.  The atlas itself is
left untouched.

The wrapper is intentionally installed after all smart/willow foliage generators
and also covers the stable-LOD master foliage path.
"""

import math

from mathutils import Quaternion

from . import generator, stable_lods


_PREVIOUS_GENERATE_FOLIAGE = None
_PREVIOUS_GENERATE_MASTER = None
_INSTALLED = False
_LOCAL_AXIS_FLIP = Quaternion((1.0, 0.0, 0.0), math.pi)


def _is_willow(settings):
    return str(getattr(settings, "species_preset", "")) == "WILLOW"


def _fix_records(settings, records):
    if not _is_willow(settings) or not records:
        return records

    fixed = 0
    for record in records:
        if record.get("willow_card_orientation_v2", False):
            continue
        rotation = record.get("rotation")
        if rotation is None:
            continue

        # Post-multiplication rotates in card-local space.  This changes the
        # atlas top/bottom mapping without changing the generated world-space
        # strand trajectory or the card's outward normal.
        record["rotation"] = rotation @ _LOCAL_AXIS_FLIP
        record["willow_card_orientation_v2"] = True
        fixed += 1

    return records


def _generate_foliage(settings, terminals):
    return _fix_records(settings, _PREVIOUS_GENERATE_FOLIAGE(settings, terminals))


def _generate_master(settings, terminals):
    return _fix_records(settings, _PREVIOUS_GENERATE_MASTER(settings, terminals))


def install():
    global _PREVIOUS_GENERATE_FOLIAGE, _PREVIOUS_GENERATE_MASTER, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE_FOLIAGE = generator.generate_foliage_points
    _PREVIOUS_GENERATE_MASTER = stable_lods.generate_master_foliage
    generator.generate_foliage_points = _generate_foliage
    stable_lods.generate_master_foliage = _generate_master
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_foliage_points = _PREVIOUS_GENERATE_FOLIAGE
    stable_lods.generate_master_foliage = _PREVIOUS_GENERATE_MASTER
    _INSTALLED = False
