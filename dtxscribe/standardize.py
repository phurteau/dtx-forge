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

# Hard ceiling on how many bars a single take/chart may span. The bar index of a hit is
# (t - anchor) / bar_time, and the assembler allocates one dict per bar up to the largest
# index, so a stray far-future timestamp, a near-zero bpm, or a huge count-in offset (which
# pushes the anchor far from the real hits) would otherwise allocate hundreds of millions of
# bars and exhaust memory. No real drum chart approaches this: 4096 bars is ~2 hours at 4/4
# 120bpm. Hits outside this window are malformed input and are dropped, not allocated.
MAX_TAKE_BARS = 4096

# Candidate per-bar subdivisions for 4/4: straight (quarter / 8th / 16th / 32nd) plus triplets
# (8th- and 16th-triplet). Each bar uses the COARSEST of these its own onsets fit, so a
# 2-note bar stays 2 notes and a 32nd fill stays 32nds -- density mirrors the song. For an
# arbitrary meter num/den the grids generalize to num*[1,2,3,4,6,8] (beats land on lines,
# then subdivided) -- which for 4/4 is exactly [4,8,12,16,24,32], so 4/4 is unchanged.
_BAR_GRID_MULT = (1, 2, 3, 4, 6, 8)
_BAR_GRIDS = [4 * m for m in _BAR_GRID_MULT]
# An onset "fits" a grid if it lands within this fraction of a grid step of a line.
_FIT_TOL = 0.18


def _bar_grids_for_sig(num):
    """Candidate per-bar subdivisions for a meter with `num` beats/bar (num*[1,2,3,4,6,8])."""
    return [num * m for m in _BAR_GRID_MULT]

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
    for hit in hits:
        t, midi = hit[0], hit[1]
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


def _bar_grid_for(positions, max_grid, bar_grids=_BAR_GRIDS):
    """Coarsest candidate subdivision on which ALL of a bar's onsets land within
    tolerance -- the least resolution the bar actually needs, so density is neither
    inflated to nor thinned toward a fixed grid."""
    usable = [g for g in bar_grids if g <= max_grid] or [bar_grids[0]]
    for g in usable:
        if all(abs(p * g - round(p * g)) <= _FIT_TOL for p in positions):
            return g
    return usable[-1]


def _place_perbar(hits, anchor, bar_time, bar_grids=_BAR_GRIDS):
    """Faithful per-bar quantization: group onsets by bar, choose each bar's OWN natural
    subdivision, and snap within it -- so the chart mirrors what the song actually plays.
    A bar with two notes stays two notes; the next bar with a 16th run stays 16ths; a
    32nd fill stays 32nds; a triplet stays a triplet. Nothing is inflated or capped."""
    step_floor = max(MIN_STEP_SEC, 1e-6)
    max_grid = max(4, int(bar_time / step_floor))     # tempo ceiling on resolution
    by_bar = {}
    for hit in hits:
        t, midi = hit[0], hit[1]
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
        g = _bar_grid_for(positions, max_grid, bar_grids)
        for frac, midi in arr:
            idx = int(round(frac * g))
            if idx >= g:                              # rounded up into the next bar
                out_bar, slot = bar + 1, 0
            else:
                out_bar, slot = bar, idx
            ch, lab = dtx.MAP[midi]
            placed.append((out_bar, Fraction(slot, g), ch, lab))
    return placed


def _assemble(placed, max_hand_voices, bar_whole=Fraction(1)):
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

    n_bars = min(max(b for (b, _p) in grid) + 1, MAX_TAKE_BARS + 2)
    events = [{} for _ in range(n_bars)]
    for (bar, pos), cell in grid.items():
        if bar < 0 or bar >= n_bars:
            continue                     # defensive: never index outside the allocated range
        for ch, lab in cell.items():
            # store the DTX WAV slot (e.g. "03"), NOT the label ("sd"): note cells are
            # references to #WAV definitions, so a raw label plays no sound in DTXMania.
            events[bar].setdefault(ch, {})[pos] = dtx.LABEL2SLOT[lab]
    barlens = [bar_whole] * n_bars      # bar length in whole-notes (4/4 -> 1; 3/4 -> 3/4; ...)
    return events, barlens


def build_events(hits, bpm, grid_div=GRID_DIV, max_hand_voices=2, adaptive=False, anchor=None,
                 time_sig=(4, 4)):
    """Quantize + clean a raw hit list into (events, barlens, anchor).

    hits: iterable of (time_seconds, gm_midi[, velocity]) -- any extra fields (velocity) are
    ignored by the quantizer but tolerated so a richer stream can pass straight through.
    bpm: chart tempo (quarter-note BPM). When ``adaptive`` is True each bar is quantized to
    its own natural subdivision (per-bar fidelity: a 2-note bar stays 2 notes, a 32nd fill
    stays 32nds); otherwise every hit is snapped to the fixed ``grid_div`` (Raw first-pass).

    ``anchor`` is the wall-clock time (seconds) that maps to chart t=0. Default (None)
    anchors to the first surviving hit -- correct for audio transcription, where the
    detected downbeat is unknown. Live e-drum capture passes an EXPLICIT anchor (the
    count-in downbeat / musical zero), since the tempo and bar-1 position are known, so a
    late or syncopated first hit doesn't drag the whole grid off the beat.

    ``time_sig`` (num, den) sets the bar length: bar = Fraction(num, den) whole-notes, and
    the per-bar grid generalizes to num*[1,2,3,4,6,8]. Defaults to 4/4, for which this is
    exactly the legacy behavior (barlen 1, grids [4,8,12,16,24,32]) -- so audio transcription
    is unchanged; Record mode passes the user's chosen meter.
    """
    hits = sorted(h for h in hits if h)
    num, den = int(time_sig[0]), int(time_sig[1])
    bar_whole = Fraction(num, den) if (num > 0 and den > 0) else Fraction(1)
    if not hits:
        return [{}], [bar_whole], 0.0

    if anchor is None:
        anchor = hits[0][0]
    bar_time = float(bar_whole) * 4 * 60.0 / bpm
    if bar_time <= 0:
        return [{}], [bar_whole], anchor

    # Bound the number of bars the assembler will allocate. A hit's bar index is
    # (t - anchor) / bar_time; a stray far-future/past timestamp, a near-zero bpm, or a huge
    # count-in offset would otherwise drive that index into the hundreds of millions and
    # exhaust memory. Keep only hits within a sane window of the anchor (one bar of slack
    # before the downbeat for pre-roll; MAX_TAKE_BARS after). Out-of-window hits are garbage.
    lo, hi = anchor - bar_time, anchor + MAX_TAKE_BARS * bar_time
    hits = [h for h in hits if lo <= h[0] <= hi]
    if not hits:
        return [{}], [bar_whole], anchor

    bar_grids = _bar_grids_for_sig(num) if num > 0 else _BAR_GRIDS
    placed = (_place_perbar(hits, anchor, bar_time, bar_grids) if adaptive
              else _place_flat(hits, anchor, bar_time, grid_div))
    if not placed:
        return [{}], [bar_whole], anchor

    events, barlens = _assemble(placed, max_hand_voices, bar_whole)
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
