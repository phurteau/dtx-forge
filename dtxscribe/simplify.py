"""Difficulty-aware cleanup -- de-conflict a redundant second timekeeper.

Real GITADORA charts of EVERY difficulty mix note values freely: even Advanced/Extreme
are mostly quarter + 8th with 16th a minority (Extreme ~7% 16th) and the occasional 32nd
fill, and difficulty comes from density, speed and limb combinations -- NOT from a
coarser grid. So this module does NOT cap note values by tier: a chart of any difficulty
keeps whatever 16th / 32nd content the song actually has. The only simplification is
dropping a redundant SECOND timekeeper -- hi-hat AND ride both playing a full pattern in
one bar -- which no drummer plays at once.
"""

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
    """De-conflict a redundant simultaneous timekeeper: when hi-hat AND ride both play a
    full pattern in the same bar, keep the denser one and drop the other (every tier
    except Master, which keeps both). Note VALUES are NEVER capped by tier -- the chart
    keeps whatever 16th / 32nd content the song actually has, at any difficulty, because
    real GITADORA charts of every tier mix subdivisions. Mutates and returns ``events``
    plus the number of notes removed.
    """
    tier = str(tier).lower()
    removed = 0
    if tier != "master":
        events, r = deconflict_metals(events)
        removed += r
    return events, removed
