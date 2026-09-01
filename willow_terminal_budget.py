"""Bridge outward-distribution terminal metadata into the willow curtain budget.

willow_outward_distribution classifies retained *real* terminal branches before
structural deformation.  The later willow_anchor_distribution pass adds virtual
supports after the final curved/spread skeleton is known.  This small final
stage runs after both and converts only the pre-classified mid/inner real
terminals into budgeted foliage supports understood by willow_foliage_fix.

Outer real terminals remain full-strength.  Mid terminals get fewer/shorter
curtains.  The small retained inner population becomes short fill-only growth,
which preserves crown volume without returning to a floor-length central mop.
"""

from . import generator


_PREVIOUS_GENERATE = None
_INSTALLED = False


def _generate_with_terminal_budget(settings):
    branches, terminals = _PREVIOUS_GENERATE(settings)
    if str(getattr(settings, "species_preset", "")) != "WILLOW":
        return branches, terminals

    budgeted = 0
    inner_fill = 0
    for branch in terminals:
        if "willow_terminal_weight" not in branch:
            continue

        weight = float(branch.get("willow_terminal_weight", 1.0))
        length_scale = float(branch.get("willow_terminal_length_scale", 1.0))
        fill_only = bool(branch.get("willow_terminal_fill_only", False))

        # Outer terminals intentionally remain ordinary real terminals so the
        # curtain generator can use its full 3-5 member bundle logic.
        if weight >= 0.92 and length_scale >= 0.90 and not fill_only:
            continue

        # Reuse the already-tested virtual-support budget path in
        # willow_foliage_fix.  This tagging happens *after* final anchor scoring,
        # so no later stage will mistake these for provisional virtual anchors.
        branch["willow_aux_anchor"] = True
        branch["willow_real_terminal_budgeted"] = True
        branch["willow_anchor_weight"] = max(0.22, min(0.90, weight))
        branch["willow_length_scale"] = max(0.38, min(0.90, length_scale))
        branch["willow_fill_only"] = fill_only
        branch["willow_max_bundles"] = 2 if fill_only else 4
        branch["willow_anchor_level"] = int(branch.get("level", 0))
        branch["willow_radial_exposure"] = float(branch.get("willow_terminal_exposure", 0.0))
        budgeted += 1
        if fill_only:
            inner_fill += 1

    try:
        trunk = next(branch for branch in branches if int(branch.get("level", 0)) == 0)
        trunk["willow_terminal_budget_version"] = 1
        trunk["willow_budgeted_real_terminals"] = int(budgeted)
        trunk["willow_inner_fill_budgeted"] = int(inner_fill)
    except Exception:
        pass

    return branches, terminals


def install():
    global _PREVIOUS_GENERATE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_GENERATE = generator.generate_skeleton
    generator.generate_skeleton = _generate_with_terminal_budget
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    generator.generate_skeleton = _PREVIOUS_GENERATE
    _INSTALLED = False
