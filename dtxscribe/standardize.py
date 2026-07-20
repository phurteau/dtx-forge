"""Standardize an audio-transcribed hit list into a clean, playable chart.

Audio onset detection yields raw ``(time, drum)`` events with millisecond jitter and
detection noise (stem bleed -> phantom hits). Emitting those straight onto the fine
1/64 grid produces off-beat "doubled" hi-hats and un-followable tom stacks. This pass
turns the raw hits into a musically standardized chart:

  1. Per-bar grid -- quantize each bar to its OWN natural subdivision (the coarsest of
                   quarter/8th/16th/32nd or 8th-/16th-triplet that the bar's onsets fit),
                   so a 2-note bar stays 2 notes and a 32nd fill stays 32nds. Density is
                   mirrored from the song, never inflated to nor capped at a fixed grid.
  2. (tempo cap) -- a bar's grid is only allowed as fine as the tempo physically permits
                   (a grid step no shorter than MIN_STEP_SEC), so detection noise can't
                   invent impossible resolutions.
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

# Raw first-pass grid (fine, no cleanup).
GRID_DIV = 16

# An onset grid step faster than this (seconds) is detection noise -- it caps how fine a
# bar's grid may get at a given tempo, so no impossible resolution is ever invented.
MIN_STEP_SEC = 0.025

# Candidate per-bar subdivisions: straight (quarter / 8th / 16th / 32nd) plus triplets
# (8th- and 16th-triplet). Each bar uses the COARSEST of these its own onsets fit, so a
# 2-note bar stays 2 notes and a 32nd fill stays 32nds -- density mirrors the song.
_BAR_GRIDS = [4, 8, 12, 16, 24, 32]
# An onset "fits" a grid if it lands within this fraction of a grid step of a line.
_FIT_TOL = 0.18

# Lanes struck with the feet -- exempt from the two-hand simultaneity cap.
_FEET = {"13", "1B"}          # kick, left-foot hi-hat pedal

# When too many hands land on one grid cell, keep these first (most musical): snare
# backbone, then cymbal accents, then hats/ride, then toms (the likeliest bleed).
_HAND_PRIORITY = ["12", "16", "1A", "19", "11", "18", "14", "15", "17"]


def _rank_hands(chans):
    order = {c: i for i, c in enumerate(_HAND_PRIORITY)}
    return sorted(chans, key=lambda c: order.get(c, 99))


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


def _bar_grid_for(positions, max_grid):
    """Coarsest candidate subdivision on which ALL of a bar's onsets land within
    tolerance -- the least resolution the bar actually needs, so density is neither
    inflated to nor thinned toward a fixed grid."""
    usable = [g for g in _BAR_GRIDS if g <= max_grid] or [_BAR_GRIDS[0]]
    for g in usable:
        if all(abs(p * g - round(p * g)) <= _FIT_TOL for p in positions):
            return g
    return usable[-1]


def _place_perbar(hits, anchor, bar_time):
    """Faithful per-bar quantization: group onsets by bar, choose each bar's OWN natural
    subdivision, and snap within it -- so the chart mirrors what the song actually plays.
    A bar with two notes stays two notes; the next bar with a 16th run stays 16ths; a
    32nd fill stays 32nds; a triplet stays a triplet. Nothing is inflated or capped."""
    step_floor = max(MIN_STEP_SEC, 1e-6)
    max_grid = max(4, int(bar_time / step_floor))     # tempo ceiling on resolution
    by_bar = {}
    for t, midi in hits:
        if midi not in dtx.MAP:
            continue
        b = (t - anchor) / bar_time
        if b < -1e-6:
            continue
        bar = int(b)
        by_bar.setdefault(bar, []).append((b - bar, midi))

    placed = []
    for bar, arr in by_bar.items():
        positions = [f for f, _ in arr]
        g = _bar_grid_for(positions, max_grid)
        for frac, midi in arr:
            idx = int(round(frac * g))
            if idx >= g:                              # rounded up into the next bar
                out_bar, slot = bar + 1, 0
            else:
                out_bar, slot = bar, idx
            ch, lab = dtx.MAP[midi]
            placed.append((out_bar, Fraction(slot, g), ch, lab))
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
    every audio-only transcription). When ``adaptive`` is True each bar is quantized to
    its own natural subdivision (per-bar fidelity: a 2-note bar stays 2 notes, a 32nd
    fill stays 32nds); otherwise every hit is snapped to the fixed ``grid_div`` (used by
    the Raw first-pass with grid_div=64, no voice cap). The first surviving hit is
    anchored to chart t=0.
    """
    hits = sorted(h for h in hits if h)
    if not hits:
        return [{}], [Fraction(1)], 0.0

    anchor = hits[0][0]
    bar_time = 4 * 60.0 / bpm
    if bar_time <= 0:
        return [{}], [Fraction(1)], anchor

    placed = (_place_perbar(hits, anchor, bar_time) if adaptive
              else _place_flat(hits, anchor, bar_time, grid_div))
    if not placed:
        return [{}], [Fraction(1)], anchor

    events, barlens = _assemble(placed, max_hand_voices)
    return events, barlens, anchor


def map_onsets(hits, bpm, anchor):
    """Map every raw ``(time, gm_midi)`` onset onto the adaptive per-bar grid as
    ``[{bar, lane, pos}]`` -- BEFORE the de-dupe/voice-cap in ``_assemble`` drops any.

    This is the editor "review" overlay's honest record of what the audio actually
    hit: a detected onset with no charted note in the same lane flags a drum the
    cleanup dropped (a likely-missed crash), while the notes themselves confirm the
    hits that survived. Uses the same quantization as the ``adaptive`` chart so the
    marks land exactly on the editor's grid."""
    bar_time = 4 * 60.0 / bpm if bpm else 0.0
    if bar_time <= 0:
        return []
    out = []
    for bar, pos, ch, _lab in _place_perbar(hits, anchor, bar_time):
        out.append({"bar": int(bar), "lane": ch, "pos": round(float(pos), 6)})
    return out
