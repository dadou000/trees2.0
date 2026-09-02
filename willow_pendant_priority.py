"""Give real pendant switches a dedicated short-foliage budget.

The 0.9.8 priority pass restored pendant switches to the unrestricted real-
terminal path.  Because the willow curtain generator already creates long
hanging strands, that duplicated the droop of the *wooden* switch itself and
produced huge foliage sheets with too little visible support.

Pendant switches remain real branches in the skeleton/runtime graph, but their
foliage is routed through the existing budgeted-support path: several short
leafy runs are distributed along each real switch instead of generating another
floor-reaching curtain from it.
"""

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False


def _generate_with_switch_priority(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW":
        return branches, terminals

    budgeted = 0
    for branch in terminals:
        if not branch.get("willow_pendant_switch", False):
            continue

        # This metadata affects foliage assembly only.  The branch remains a
        # normal real woody branch with its own ID, parent and runtime mapping.
        branch["willow_aux_anchor"] = True
        branch["willow_real_terminal_budgeted"] = True
        branch["willow_switch_foliage_support"] = True
        branch["willow_anchor_weight"] = 0.62
        branch["willow_length_scale"] = 0.44
        branch["willow_fill_only"] = False
        branch["willow_max_bundles"] = 3
        branch["willow_anchor_level"] = int(branch.get("level", 0))
        branch["willow_radial_exposure"] = float(branch.get("willow_terminal_exposure", 0.72))
        branch["willow_terminal_weight"] = 0.78
        branch["willow_terminal_length_scale"] = 0.56
        branch["willow_terminal_fill_only"] = False
        branch["willow_pendant_primary_support"] = True
        budgeted += 1

    try:
        trunk = next(branch for branch in branches if int(branch.get("level", 0)) == 0)
        trunk["willow_pendant_priority_version"] = 2
        trunk["willow_pendant_primary_supports"] = int(budgeted)
        trunk["willow_pendant_short_foliage_budget"] = True
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
