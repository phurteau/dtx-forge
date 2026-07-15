"""Standardize an audio-transcribed hit list into a clean, playable chart.

Audio onset detection yields raw ``(time, drum)`` events with millisecond jitter and
detection noise (stem bleed -> phantom hits). Emitting those straight onto the fine
1/64 grid produces off-beat "doubled" hi-hats and un-followable tom stacks. This pass
turns the raw hits into a musically standardized chart:

  1. Quantize   -- snap the groove to a musical 1/16 grid so timing lands on 1-e-&-a.
  2. Adaptive 1/32 -- but KEEP thirty-second resolution where the music genuinely has
                   it: a real roll/fill (>= RUN_MIN consecutive 1/32 onsets across the
                   kit) or a fast same-drum double. Isolated off-grid hits that a 1/16
                   snap would merge are treated as jitter and collapsed.
  3. De-dupe    -- collapse multiple onsets of the SAME drum in one grid cell.
  4. Cap voices -- at most two "hand" instruments per cell (you have two hands); drop
                   the least-musical extras (usually bleed). Feet (kick + hi-hat pedal)
                   are exempt.

The result is grid-locked and physically playable; the pipeline's playability check +
auto-relax then runs on top and thins anything still too fast for two hands + two feet.
So standardize decides *what the music is*; playability decides *what a human can hit*.
"""
from fractions import Fraction
from . import dtx

# Base musical grid (sixteenths) and the adaptive refinement grid (thirty-seconds).
GRID_DIV = 16
FINE_DIV = 32

# A 1/32 faster than this (seconds) is detection noise, never kept as a real note.
MIN_32_SEC = 0.025
# Consecutive 1/32-spaced onsets (across the kit) that constitute a genuine roll/fill.
RUN_MIN = 4
# A same-drum pair is a real 1/32 double only if spaced at least this fraction of a
# 1/32 apart; closer than that is a flam / jitter and gets merged.
COLLIDE_FACTOR = 0.7

# Lanes struck with the feet -- exempt from the two-hand simultaneity cap.
_FEET = {"13", "1B"}          # kick, left-foot hi-hat pedal

# When too many hands land on one grid cell, keep these first (most musical): snare
# backbone, then cymbal accents, then hats/ride, then toms (the likeliest bleed).
_HAND_PRIORITY = ["12", "16", "1A", "19", "11", "18", "14", "15", "17"]


def _rank_hands(chans):
    order = {c: i for i, c in enumerate(_HAND_PRIORITY)}
    return sorted(chans, key=lambda c: order.get(c, 99))


def _snap16(fine_cont):
    """Nearest 1/16 position expressed in fine (1/32) units (always an even int)."""
    return 2 * int(round(fine_cont / 2.0))


def _place_flat(hits, anchor, bar_time, grid_div):
    """Snap every hit to a single fixed grid (used for the Raw first-pass output)."""
    placed = []
    for t, midi in hits:
        if midi not in dtx.MAP:
            continue
        b = (t - anchor) / bar_time
        if b < -1e-6:
            continue
        bar = int(b)
        s = int(round((b - bar) * grid_div))
        if s >= grid_div:
            bar += 1
            s = 0
        ch, lab = dtx.MAP[midi]
        placed.append((bar, Fraction(s, grid_div), ch, lab))
    return placed


def _place_adaptive(hits, anchor, bar_time):
    """Snap to 1/16, but preserve 1/32 where the music really is that fast."""
    step32 = bar_time / FINE_DIV
    allow32 = step32 >= MIN_32_SEC
    collide_min = max(MIN_32_SEC, COLLIDE_FACTOR * step32)

    items = []   # (fine_cont, fine, time, ch, lab)
    for t, midi in hits:
        if midi not in dtx.MAP:
            continue
        cont = (t - anchor) / bar_time * FINE_DIV
        if cont < -1e-6:
            continue
        ch, lab = dtx.MAP[midi]
        items.append((cont, int(round(cont)), t, ch, lab))
    if not items:
        return []

    promote = set()   # fine slots that keep 1/32 resolution
    if allow32:
        # (a) cross-kit rolls: >= RUN_MIN consecutive occupied 1/32 slots (a fill)
        occ = sorted({it[1] for it in items})
        run = [occ[0]]
        for s in occ[1:]:
            if s == run[-1] + 1:
                run.append(s)
            else:
                if len(run) >= RUN_MIN:
                    promote.update(run)
                run = [s]
        if len(run) >= RUN_MIN:
            promote.update(run)

        # (b) fast same-drum doubles: two onsets of one drum inside a single 1/16,
        #     far enough apart to be a real 1/32 (not a flam/jitter).
        by_lane = {}
        for cont, fine, t, ch, lab in items:
            by_lane.setdefault(ch, []).append((cont, fine, t))
        for ch, arr in by_lane.items():
            buckets = {}
            for cont, fine, t in arr:
                buckets.setdefault(_snap16(cont), []).append((fine, t))
            for s16, members in buckets.items():
                if len({f for f, _ in members}) < 2:
                    continue
                ts = sorted(t for _, t in members)
                if (ts[-1] - ts[0]) >= collide_min:
                    promote.update(f for f, _ in members)

    placed = []
    for cont, fine, t, ch, lab in items:
        final = fine if fine in promote else _snap16(cont)
        bar = final // FINE_DIV
        slot = final % FINE_DIV
        placed.append((bar, Fraction(slot, FINE_DIV), ch, lab))
    return placed


def _assemble(placed, max_hand_voices):
    """De-dupe same-drum per cell, cap hand voices, and build the (events, barlens)."""
    grid = {}   # (bar, Fraction pos) -> {channel: label}
    for bar, pos, ch, lab in placed:
        grid.setdefault((bar, pos), {}).setdefault(ch, lab)

    for cell in grid.values():
        hands = [c for c in cell if c not in _FEET]
        if len(hands) > max_hand_voices:
            keep = set(_rank_hands(hands)[:max_hand_voices])
            for c in hands:
                if c not in keep:
                    del cell[c]

    n_bars = max(b for (b, _p) in grid) + 1
    events = [{} for _ in range(n_bars)]
    for (bar, pos), cell in grid.items():
        for ch, lab in cell.items():
            # store the DTX WAV slot (e.g. "03"), NOT the label ("sd"): note cells are
            # references to #WAV definitions, so a raw label plays no sound in DTXMania.
            events[bar].setdefault(ch, {})[pos] = dtx.LABEL2SLOT[lab]
    barlens = [Fraction(1)] * n_bars
    return events, barlens


def build_events(hits, bpm, grid_div=GRID_DIV, max_hand_voices=2, adaptive=False):
    """Quantize + clean a raw hit list into (events, barlens, anchor).

    hits: iterable of (time_seconds, gm_midi). bpm: chart tempo (4/4 assumed, as for
    every audio-only transcription). When ``adaptive`` is True the groove is snapped to
    1/16 but genuine 1/32 rolls/doubles are preserved; otherwise every hit is snapped to
    the fixed ``grid_div`` (used by the Raw first-pass with grid_div=64, no voice cap).
    The first surviving hit is anchored to chart t=0.
    """
    hits = sorted(h for h in hits if h)
    if not hits:
        return [{}], [Fraction(1)], 0.0

    anchor = hits[0][0]
    bar_time = 4 * 60.0 / bpm
    if bar_time <= 0:
        return [{}], [Fraction(1)], anchor

    placed = (_place_adaptive(hits, anchor, bar_time) if adaptive
              else _place_flat(hits, anchor, bar_time, grid_div))
    if not placed:
        return [{}], [Fraction(1)], anchor

    events, barlens = _assemble(placed, max_hand_voices)
    return events, barlens, anchor
