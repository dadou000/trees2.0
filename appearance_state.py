"""Extend Trees 2.0 settings snapshots with visual appearance state."""

from . import generator


_PREVIOUS_SNAPSHOT = None
_INSTALLED = False


def _appearance_snapshot(settings):
    values = _PREVIOUS_SNAPSHOT(settings)
    values.update({
        "leaf_tint": list(settings.leaf_tint),
        "bark_color": list(settings.bark_color),
        "pbr_respect_tree_colors": bool(settings.pbr_respect_tree_colors),
        "pbr_species_color_influence": float(settings.pbr_species_color_influence),
    })
    return values


def install():
    global _PREVIOUS_SNAPSHOT, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_SNAPSHOT = generator._settings_snapshot
    generator._settings_snapshot = _appearance_snapshot
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator._settings_snapshot = _PREVIOUS_SNAPSHOT
    _INSTALLED = False
