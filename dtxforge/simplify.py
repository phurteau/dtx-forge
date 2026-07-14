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


def thin_for_tier(events, tier):
    """Drop metal (hi-hat/ride) notes finer than the tier's grid.

    e.g. Advanced keeps metal down to 1/8, so a continuous 16th hi-hat becomes a clean
    8th pulse (roughly half the notes). Kick/snare/toms/crash are untouched. Mutates and
    returns ``events`` plus the number of notes removed.
    """
    maxden = TIER_METAL_GRID.get(str(tier).lower())
    if maxden is None:
        return events, 0
    removed = 0
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
