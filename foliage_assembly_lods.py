"""Assembly-aware stable LOD derivation for structured foliage."""

import bpy

from . import generator, stable_lods


_PREVIOUS_DERIVE = None
_INSTALLED = False


def _assembly_enabled():
    scene = getattr(bpy.context, "scene", None)
    assembly = getattr(scene, "trees2_foliage_assembly", None) if scene else None
    return bool(assembly and assembly.enabled)


def _copy_record(record, scale_boost):
    copied = dict(record)
    copied["position"] = record["position"].copy()
    copied["rotation"] = record["rotation"].copy()
    copied["scale"] = record["scale"].copy() * scale_boost
    return copied


def _derive_weeping(master_records, settings, lod):
    cfg = generator.LOD[lod]
    factor = float(cfg["foliage"])
    if factor >= 0.999:
        return [_copy_record(record, 1.0) for record in master_records]

    # Reduce strand count and per-strand card count separately.  Top-K rankings
    # are deterministic, therefore each lower LOD remains a strict subset.
    strand_fraction = max(0.20, factor ** 0.46)
    card_fraction = max(0.24, factor ** 0.44)

    by_branch = {}
    loose = []
    for record in master_records:
        strand_id = int(record.get("strand_id", -1))
        if int(record.get("assembly_role", -1)) != 2 or strand_id < 0:
            loose.append(record)
            continue
        branch_id = int(record.get("source_branch_id", -1))
        by_branch.setdefault(branch_id, {}).setdefault(strand_id, []).append(record)

    selected = []
    for branch_id, strands in by_branch.items():
        ranked_strands = sorted(
            strands.items(),
            key=lambda item: stable_lods._stable_unit(
                int(settings.seed) ^ (branch_id * 0x45D9F3B),
                int(item[0]) * 37 + 17,
            ),
        )
        keep_strands = max(1, min(len(ranked_strands), round(len(ranked_strands) * strand_fraction)))
        for strand_id, cards in ranked_strands[:keep_strands]:
            cards = sorted(cards, key=lambda r: float(r.get("strand_t", 0.0)))
            if len(cards) <= 2:
                selected.extend(cards)
                continue
            target_cards = max(2, min(len(cards), round(len(cards) * card_fraction)))
            # Keep curtain endpoints. Rank the interior deterministically so the
            # selected set remains nested instead of changing shape each LOD.
            endpoints = [cards[0], cards[-1]]
            interior = cards[1:-1]
            ranked_interior = sorted(
                interior,
                key=lambda r: stable_lods._stable_unit(
                    int(settings.seed) ^ (strand_id * 0x9E3779B9),
                    int(r.get("source_local_index", r.get("source_index", 0))),
                ),
            )
            selected.extend(endpoints)
            selected.extend(ranked_interior[:max(0, target_cards - 2)])

    # This path is normally pure willow, but preserve any auxiliary records if
    # future assembly modes mix roles.
    if loose:
        loose_derived = _PREVIOUS_DERIVE(loose, settings, lod)
        selected.extend(loose_derived)

    # Structured curtains need much less size compensation than random leaf
    # clouds; large LOD cards would otherwise turn back into visible slabs.
    coverage = factor ** -0.20 if factor > 0.0 else 1.0
    scale_boost = min(1.85, max(float(cfg["card_scale"]), coverage))
    return [_copy_record(record, scale_boost) for record in selected]


def _derive(master_records, settings, lod):
    if not _assembly_enabled() or not any(int(r.get("assembly_role", -1)) == 2 for r in master_records):
        return _PREVIOUS_DERIVE(master_records, settings, lod)
    return _derive_weeping(master_records, settings, lod)


def install():
    global _PREVIOUS_DERIVE, _INSTALLED
    if _INSTALLED:
        return
    _PREVIOUS_DERIVE = stable_lods.derive_lod_foliage
    stable_lods.derive_lod_foliage = _derive
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    stable_lods.derive_lod_foliage = _PREVIOUS_DERIVE
    _INSTALLED = False
