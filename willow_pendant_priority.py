"""Preserve real pendant switches as full foliage supports.

The continuous crown envelope and terminal-budget stages are intentionally
conservative with ordinary inner/mid terminals.  Pendant switches are different:
they are actual thin woody supports generated only on exposed outer secondary /
tertiary branches.  Treating them as virtual fill would defeat their purpose.

This final skeleton wrapper runs after terminal budgeting and restores switch
terminals to the normal real-terminal path used by willow_foliage_fix.
"""

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False


def _generate_with_switch_priority(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW":
        return branches, terminals

    restored = 0
    for branch in terminals:
        if not branch.get("willow_pendant_switch", False):
            continue

        # Undo only foliage-budget classification.  Structural and runtime
        # metadata remain intact.
        branch.pop("willow_aux_anchor", None)
        branch.pop("willow_real_terminal_budgeted", None)
        branch.pop("willow_anchor_weight", None)
        branch.pop("willow_length_scale", None)
        branch.pop("willow_fill_only", None)
        branch.pop("willow_max_bundles", None)
        branch.pop("willow_anchor_level", None)
        branch["willow_terminal_weight"] = max(
            1.0, float(branch.get("willow_terminal_weight", 1.0))
        )
        branch["willow_terminal_length_scale"] = max(
            0.92, float(branch.get("willow_terminal_length_scale", 1.0))
        )
        branch["willow_terminal_fill_only"] = False
        branch["willow_pendant_primary_support"] = True
        restored += 1

    try:
        trunk = next(branch for branch in branches if int(branch.get("level", 0)) == 0)
        trunk["willow_pendant_priority_version"] = 1
        trunk["willow_pendant_primary_supports"] = int(restored)
    except Exception:
        pass
    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_with_switch_priority
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
