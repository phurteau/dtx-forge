"""Difficulty-aware simplification: thin dense hi-hat / ride to a coarser grid.

Audio transcription captures every hi-hat and ride hit, which for a fast song is a
near-continuous stream of 16th notes -- faithful, but very dense to read and play. Real
rhythm games solve this with difficulty tiers: lower tiers thin the cymbal timekeeping
to a coarser pulse while the kick/snare backbone, toms and crashes stay intact. This
module applies exactly that, per tier.

Only the metal timekeeping lanes (closed hi-hat, open hi-hat, ride) are thinned. Kick,
snare, toms and crash accents are never touched -- they carry the song.
"""
from . import dtx

# Timekeeping lanes that get density-limited.
_METAL = {"11", "18", "19"}     # closed hi-hat, open hi-hat, ride

# Coarsest grid (max Fraction denominator) kept for metal notes, per difficulty tier:
#   4 = quarter, 8 = eighth, 16 = sixteenth, None = keep everything (incl. 1/32 fills).
# Lower tiers read sparser; Master keeps the full transcription.
TIER_METAL_GRID = {"basic": 4, "advanced": 8, "extreme": 16, "master": None}


# Timekeeping metals that shouldn't sound simultaneously (you play hi-hat OR ride).
_HAT = "11"      # closed hi-hat
_RIDE = "19"     # ride


def deconflict_metals(events, min_hits=3):
    """Per bar, if BOTH closed hi-hat and ride act as timekeeping (each has several
    hits), keep only the denser one and drop the other. Real drummers play hi-hat OR
    ride at a time, not both, so removing the redundant second timekeeper both halves
    the metal density and reads far more idiomatically. Isolated ride accents (a single
    crash-of-ride hit) are left alone -- they only collide when ride is a full pattern.
    """
    removed = 0
    for bar in events:
        hh, rd = bar.get(_HAT), bar.get(_RIDE)
        if hh and rd and len(hh) >= min_hits and len(rd) >= min_hits:
            drop = _RIDE if len(hh) >= len(rd) else _HAT
            removed += len(bar[drop])
            del bar[drop]
    return events, removed


def thin_for_tier(events, tier):
    """Simplify hi-hat / ride density for a difficulty tier.

    Two steps: (1) de-conflict the timekeeping metals (drop the redundant hi-hat/ride
    when both play a full pattern in a bar) for every tier except Master; (2) drop metal
    notes finer than the tier's grid, so e.g. Advanced turns a continuous 16th hi-hat
    into a clean 8th pulse. Kick/snare/toms/crash are untouched. Mutates and returns
    ``events`` plus the number of notes removed.
    """
    tier = str(tier).lower()
    removed = 0
    # Master keeps the full, faithful kit (both metals); lower tiers de-conflict.
    if tier != "master":
        events, r = deconflict_metals(events)
        removed += r
    maxden = TIER_METAL_GRID.get(tier)
    if maxden is None:
        return events, removed
    for bar in events:
        for ch in list(bar.keys()):
            if ch not in _METAL:
                continue
            kept = {}
            for pos, lab in bar[ch].items():
                if pos == 0 or pos.denominator <= maxden:
                    kept[pos] = lab
                else:
                    removed += 1
            if kept:
                bar[ch] = kept
            else:
                del bar[ch]
    return events, removed
