"""Regularize a standardized chart into idiomatic DTXMania patterns ("DTXMania mode").

Raw/standardized audio transcription is faithful but reads "busy" -- timekeeping has
jitter and gaps that make a chart look randomly generated. Real DTXMania/GITADORA
charts read "produced": steady, evenly-spaced timekeeping and a consistent timekeeper
(hi-hat OR ride) within a section. This pass rewrites the timekeeping layer toward
those conventions.

Grounded in an analysis of 2000 real approved GITADORA charts (188,760 bars). The data
DEBUNKED two conventions this module used to enforce, which have been removed:
  * "one crash per bar" -- WRONG: crashes stack freely with kick (107k co-hits), snare
    (49k) and even other crashes (CY+LC). Crashes are now preserved as transcribed.
  * "crash on every phrase downbeat" -- WRONG: only 31% of 4-bar phrase downbeats carry
    a crash. No crashes are injected.

What the data CONFIRMED and this module keeps:
  1. One timekeeper at a time -- hi-hat and ride coexist in only ~0.1% of bars, so a
     redundant second timekeeper is dropped. Chosen once per SECTION (a run of bars),
     not per bar, so the timekeeper doesn't flip hi-hat/ride/hi-hat between neighbours.
  2. Steady timekeeping -- 80% of multi-hit hi-hat bars are perfectly evenly spaced, so
     a bar that already carries a timekeeping pattern is rewritten as a clean pulse
     (1/8, or 1/16 when dense) at the tier's resolution.
  3. Closed hi-hat + crash on the same tick is a transcription artifact (3 in 160k real
     bars) -- the closed hi-hat is dropped there so the crash reads as the accent. (Open
     hi-hat under a crash is a real, if rare, technique and is left intact.)

Kick, snare, toms and crashes (the groove, fills and accents) are left as transcribed
-- only the hi-hat / ride timekeeping layer is regularized.
"""
from fractions import Fraction
from . import humanize

_HAT = "11"           # closed hi-hat
_HHO = "18"           # open hi-hat
_RIDE = "19"          # ride
_CRASH = ("16", "1A")  # crash, left crash
SECTION = 4           # bars per timekeeping section

# Steady timekeeping resolution per difficulty tier (notes per bar): Basic reads as a
# 1/4 pulse, Advanced 1/8, Extreme/Master 1/16 -- so the density follows the tier.
TIER_GRID = {"basic": 4, "advanced": 8, "extreme": 16, "master": 16}

# Tier-gated left-foot technique for an authentic DTXMania/GITADORA chart, from the
# 2000-chart analysis: Basic/Advanced use the left foot almost never; Extreme adds
# double bass (which only fires on kick runs too fast for one foot); Master also adds
# the hi-hat "chick" on 2 & 4 -- 95% of real Master charts use the hi-hat foot and 58%
# use double bass. (hihat_foot, double_bass) per tier:
TIER_FOOT = {
    "basic":    (False, False),
    "advanced": (False, False),
    "extreme":  (False, True),
    "master":   (True,  True),
}


def _deconflict_sectional(events, section=SECTION, min_hits=2):
    """Keep ONE timekeeper (hi-hat OR ride) consistent across each ``section`` of bars.

    Hi-hat and ride act as timekeeping in the same bar in only ~0.1% of real GITADORA
    bars, so when both play a full pattern one is redundant. Rather than deciding per
    bar (which makes the timekeeper flip hi-hat/ride/hi-hat between neighbours), the
    winner is chosen once per section -- whichever metal has more hits across the
    section -- and only the loser's full patterns are dropped. An isolated ride accent
    (a single crash-of-ride hit, fewer than ``min_hits``) is never touched."""
    removed = 0
    for start in range(0, len(events), section):
        block = events[start:start + section]
        hh_hits = sum(len(b.get(_HAT, {})) for b in block)
        rd_hits = sum(len(b.get(_RIDE, {})) for b in block)
        if not hh_hits or not rd_hits:
            continue                      # only one timekeeper in play: nothing to resolve
        drop = _RIDE if hh_hits >= rd_hits else _HAT
        for b in block:
            hh, rd = b.get(_HAT), b.get(_RIDE)
            if hh and rd and len(hh) >= min_hits and len(rd) >= min_hits:
                removed += len(b[drop])
                del b[drop]
    return events, removed


def _regularize_timekeeping(bar, grid):
    """Rewrite the bar's timekeeping metal as a clean, evenly-spaced pulse at ``grid``
    notes per bar (the steady DTXMania look). Only bars that already have a timekeeping
    pattern (>=3 hits) are regularized; sparser bars are left alone. Verified against
    real charts: 80% of multi-hit hi-hat bars are perfectly evenly spaced."""
    for ch in (_HAT, _RIDE):
        sm = bar.get(ch)
        if sm and len(sm) >= 3:
            slot = next(iter(sm.values()))                    # keep its WAV slot
            bar[ch] = {Fraction(i, grid): slot for i in range(grid)}
            return 1
    return 0


def _declutter_hh_crash(bar):
    """Remove a CLOSED hi-hat that lands on the exact tick of a crash. Across 2000 real
    charts a closed hi-hat and a crash share a tick in only 3 of 160k bars, so a
    coincident closed hat is almost always a transcription artifact -- the crash should
    read as the accent. Open hi-hat under a crash is a genuine (if rare) technique and
    is deliberately left intact."""
    hh = bar.get(_HAT)
    if not hh:
        return 0
    crash_ticks = set()
    for ch in _CRASH:
        crash_ticks |= set(bar.get(ch, {}))
    hit = [p for p in hh if p in crash_ticks]
    for p in hit:
        del hh[p]
    if not hh:
        del bar[_HAT]
    return len(hit)


def apply(events, barlens, bpm, tier="advanced"):
    """Regularize a chart toward idiomatic DTXMania patterns. Mutates and returns
    (events, changed_count). Timekeeping density follows the difficulty ``tier``."""
    grid = TIER_GRID.get(str(tier).lower(), 8)
    # 1. one timekeeper (hi-hat OR ride) at a time, chosen consistently per section.
    events, changed = _deconflict_sectional(events)
    for bar in events:
        # 2. steady, evenly-spaced timekeeping at the tier's resolution.
        changed += _regularize_timekeeping(bar, grid)
        # 3. a closed hi-hat sharing a crash's tick is an artifact -> let the crash speak.
        changed += _declutter_hh_crash(bar)
    # Crashes are preserved exactly as transcribed: real charts stack them with kick,
    # snare and other crashes, and only 31% of phrase downbeats carry one -- so this
    # pass neither collapses crashes to one-per-bar nor injects phrase-start crashes.
    return events, changed


def auto_foot(events, barlens, bpm, tier="advanced"):
    """Add tier-gated left-foot technique to a DTXMania-style chart AFTER the hands are
    regularized, so the foot fills the gaps around the FINAL hi-hat/ride layout (this is
    why it runs here rather than in the generic humanize stage, which would see the
    pre-regularized hands). The one-left-foot rule is preserved by humanize's own
    ordering -- double bass claims a tick first, then the hi-hat chick only fills a
    still-free 2 & 4 backbeat -- so a chick and a left kick can never share a tick, as in
    real charts. Returns (events, hihat_on, double_on, converted_kicks)."""
    hh, db = TIER_FOOT.get(str(tier).lower(), (False, False))
    converted = 0
    if hh or db:
        events, converted = humanize.humanize(events, barlens, bpm,
                                              hihat_on=hh, doublebass=db)
    return events, hh, db, converted
