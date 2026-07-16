"""Snap a chart's steady GROOVE onto the nearest idiomatic real-corpus pattern -- the
"snap groove, keep fills" DTXMania elevation.

Audio transcription (and loose tabs) yield a backbone -- kick (13), snare (12) and the
hi-hat/ride timekeeper (11/19) -- that jitters bar to bar: a missed 8th here, a ghost kick
there, so the groove reads "randomly generated" even after de-flam/de-jitter. Real GITADORA
charts instead reuse a small vocabulary of steady grooves (mined in ``groove_data`` from
4,729 approved charts: e.g. snare on 2&4 + straight-8th hats + four-on-floor kick).

This pass matches each clean 1/16 groove bar to the nearest template and, when the
transcription is already CLOSE (a small Hamming correction), replaces the groove channels
with that template -- denoising toward a real pattern without inventing a distant one. It is
deliberately conservative:

  * Only the groove channels {13, 12, 11, 19} are ever touched. Toms (14/15/17), crashes
    (16/1A), open hi-hat (18) and the feet (1B/1C) are preserved verbatim -- the FILLS and
    accents stay exactly as the song plays them.
  * A bar is left completely untouched if it is a tom FILL (>=3 toms), has no timekeeper,
    is not 4/4, carries finer-than-1/16 content (triplets, 32nd double-bass -- genuine fast
    playing, not noise), or uses the ride as its timekeeper (templates are hi-hat based).
  * The correction budget scales gently with density (1 bit on a sparse bar, up to 4 on a
    busy one) and a bar already ON a real pattern (distance 0) or too FAR from every
    template (distance > budget) is left as-is.

So this decides *which idiomatic groove the bar is closest to*; the fill layer is the song.
"""
from fractions import Fraction
from collections import Counter
from . import dtx, groove_data

GRID = groove_data.GRID
GROOVE = tuple(groove_data.GROOVE_CHANNELS)   # ("13","12","11","19") = kick, snare, hat, ride
TOMS = ("14", "15", "17")
# canonical WAV slot each groove lane references when a note is (re)placed
_CANON = {ch: dtx.LANE_DEFAULT_SLOT.get(ch, "00") for ch in GROOVE}


def _is_snare_roll(bar):
    """True if the snare (12) carries a genuine ROLL -- a run of >=4 consecutive 1/16 hits.
    A roll is a fill, not a groove: collapsing it to a backbeat would wreck it, so a roll bar
    is spared by the groove snap (the same way tom fills are). A normal backbeat plus ghost
    notes never forms a 4-in-a-row 1/16 run, so real grooves stay eligible."""
    sm = bar.get("12")
    if not sm or len(sm) < 4:
        return False
    slots = set()
    for p in sm:
        if p.denominator and GRID % p.denominator == 0:
            slots.add(int(round(float(p) * GRID)) % GRID)
        else:
            slots.add(int(round(float(p) * GRID)) % GRID)   # off-grid still buckets to nearest 1/16
    run = best = 1
    for s in range(1, GRID):
        if s in slots and (s - 1) in slots:
            run += 1
            best = max(best, run)
        else:
            run = 1
    # wrap-around (a roll straddling the barline)
    if 0 in slots and (GRID - 1) in slots:
        best = max(best, run + 1)
    return best >= 4


def _quantize_lane(positions):
    """Round a lane's onsets to the 1/16 grid and return (mask, ok).

    ok is False when the lane carries content that snapping to 1/16 would DESTROY -- a
    triplet feel (a position on a /3 subdivision) or genuine sub-1/16 density (two onsets
    that round onto the SAME 1/16 slot, e.g. a real 32nd run). Timing jitter that merely
    placed a straight 8th/16th groove onto a finer grid rounds back cleanly (no merge) and
    stays eligible -- which is exactly the noise the snap should clean."""
    slots = []
    for p in positions:
        if p.denominator % 3 == 0:
            return 0, False                       # triplet subdivision -> keep faithful
        slots.append(int(round(float(p) * GRID)) % GRID)
    if len(set(slots)) != len(slots):
        return 0, False                           # two onsets merge on 1/16 -> real sub-16th content
    mask = 0
    for s in slots:
        mask |= 1 << s
    return mask, True


def _q16_collapse(positions):
    """Quantize onsets to the 1/16 grid, COLLAPSING near-duplicates into one slot. Used by
    the aggressive DTXMania pass: a jittery 1/32 hi-hat mess (the 'random noisy hi-hats')
    folds onto clean 1/16 lines and de-dupes, which is exactly the idiomatic cleanup wanted
    when faithfulness is waived for GITADORA feel."""
    mask = 0
    for p in positions:
        mask |= 1 << (int(round(float(p) * GRID)) % GRID)
    return mask


def _tripletish(positions):
    """True if the onsets sit better on a /12 (triplet) grid than on /16 -- a real triplet
    feel that 1/16 snapping would wreck. Such bars are left faithful even in aggressive mode."""
    if len(positions) < 2:
        return False
    def err(g):
        return sum(abs(float(p) * g - round(float(p) * g)) for p in positions) / len(positions)
    return err(12) + 0.03 < err(16)


def _bits(mask):
    return [i for i in range(GRID) if mask & (1 << i)]


def _hamming(a, b):
    return bin(a ^ b).count("1")


def _rot(mask, r):
    """Rotate a GRID-bit bar mask LEFT by r slots (wrapping within the bar)."""
    r %= GRID
    if r == 0:
        return mask
    return ((mask << r) | (mask >> (GRID - r))) & ((1 << GRID) - 1)


def _budget(total_hits):
    """Correction reach for an UNrecognized (non-real) groove -- i.e. transcription noise.
    Real grooves are already protected by the KNOWN check, so this only governs how far a
    noisy groove may reach for a common target: gentle on sparse bars, a little more on
    dense ones. Anything beyond is a genuinely different groove and is left faithful."""
    if total_hits >= 12:
        return 3
    if total_hits >= 6:
        return 2
    return 1


def _pack(k, s, h, r):
    return k | (s << 16) | (h << 32) | (r << 48)


_ROT_TARGETS = {}


def _rotated_targets(tier):
    """All targets pre-rotated to every phase: (k,s,h,r, freq, phase_shift). Cached."""
    rt = _ROT_TARGETS.get(tier)
    if rt is None:
        base = groove_data.TARGETS.get(tier) or groove_data.TARGETS["advanced"]
        rt = []
        for (tk, ts, th, tr, tf) in base:
            for rot in range(GRID):
                rt.append((_rot(tk, rot), _rot(ts, rot), _rot(th, rot), _rot(tr, rot),
                           tf, min(rot, GRID - rot)))
        _ROT_TARGETS[tier] = rt
    return rt


def snap(events, barlens, bpm, tier="advanced", aggressive=False):
    """Snap each eligible groove bar toward a common real pattern. Mutates ``events`` and
    returns (events, snapped_bar_count).

    CONSERVATIVE (default): a bar whose groove is already a KNOWN real signature (at any
    phase) is left untouched; only an UNrecognized groove -- transcription noise -- is pulled
    to the nearest common TARGET, within a small denoise budget. Matching is PHASE-TOLERANT
    (a transcription anchors bar 1 to the first onset, not the downbeat, so real grooves
    arrive rotated); the target is re-emitted at the bar's own phase, cleaning SHAPE without
    moving notes off the beat. Fills/accents untouched.

    AGGRESSIVE (GITADORA feel, faithfulness waived): EVERY 4/4 non-fill groove bar with a
    timekeeper is rewritten to its nearest common real groove -- no KNOWN bypass, no small
    budget -- so kick/snare/hat/ride read like a produced chart end to end. Jittery 1/32
    hi-hat noise is collapsed onto clean 1/16 lines first. Only a genuine triplet feel or a
    tom fill is spared. Crashes/open-hat/feet are still preserved for the fill layer.
    """
    tier = str(tier).lower()
    known = groove_data.KNOWN.get(tier) or groove_data.KNOWN["advanced"]
    snapped = 0
    for i, bar in enumerate(events):
        bl = barlens[i] if i < len(barlens) else Fraction(1)
        if bl != Fraction(1):
            continue                                  # non-4/4 -> leave faithful
        if not aggressive and sum(len(bar.get(c, {})) for c in TOMS) >= 3:
            continue                                  # conservative: a tom fill -> keep the fill
        if _is_snare_roll(bar):
            continue                                  # a genuine snare roll is a fill -> keep it
        if not (bar.get("11") or bar.get("19")):
            continue                                  # no timekeeper -> not a groove bar

        if aggressive:
            # a real triplet feel on the timekeeper is spared; everything else is rewritten
            tk_pos = list(bar.get("11", {})) or list(bar.get("19", {}))
            if _tripletish(tk_pos):
                continue
            k = _q16_collapse(list(bar.get("13", {})))
            s = _q16_collapse(list(bar.get("12", {})))
            h = _q16_collapse(list(bar.get("11", {})))
            r = _q16_collapse(list(bar.get("19", {})))
            hits = bin(k).count("1") + bin(s).count("1") + bin(h).count("1") + bin(r).count("1")
            if hits < 4:
                continue                              # genuinely sparse (intro/breakdown) -> leave it
            budget = 99                               # always take the nearest real groove
            check_known = False
        else:
            sig = []
            fit = True
            hits = 0
            for ch in GROOVE:
                pos = list(bar.get(ch, {}))
                hits += len(pos)
                m, f = _quantize_lane(pos)
                fit = fit and f
                sig.append(m)
            if not fit:
                continue                              # triplets / real sub-16th -> genuine fast content
            if hits < 4:
                continue                              # too sparse to be denoised -> keep faithful
            k, s, h, r = sig
            budget = _budget(hits)
            check_known = True
        if r and not h:
            continue                                  # ride-timekeeper bar -> targets are hat-based
        if check_known and any(
                _pack(_rot(k, rr), _rot(s, rr), _rot(h, rr), _rot(r, rr)) in known
                for rr in range(GRID)):
            continue                                  # already a REAL groove at some phase -> keep it

        best = None
        best_d = 99
        best_shift = 99
        best_f = -1.0
        for (tk, ts, th, tr, tf, shift) in _rotated_targets(tier):
            d = _hamming(k, tk) + _hamming(s, ts) + _hamming(h, th) + _hamming(r, tr)
            if d > best_d:
                continue
            # prefer: smaller distance, then a smaller phase shift, then a more common target
            if (d < best_d
                    or shift < best_shift
                    or (shift == best_shift and tf > best_f)):
                best = (tk, ts, th, tr)
                best_d, best_shift, best_f = d, shift, tf
        # conservative: skip a perfect match (already idiomatic) or one beyond the budget.
        # aggressive: even a distance-0 match is re-emitted so sub-1/16 ghosts are stripped and
        # every note lands cleanly on the grid; only "no target found" bails.
        if best is None or best_d > budget or (best_d == 0 and not aggressive):
            continue

        for ch, mask in zip(GROOVE, best):
            if mask:
                bar[ch] = {Fraction(b, GRID): _CANON[ch] for b in _bits(mask)}
            else:
                bar.pop(ch, None)
        snapped += 1
    return events, snapped


# ---------------------------------------------------------------------------------------
# SECTION-FIRST grooming -- the "neat like the real corpus" pass.
#
# Diagnosis (generated First Date vs a 120-chart Extreme corpus sample): our per-bar snap
# left only 2% of adjacent groove bars IDENTICAL vs 16% in the corpus, and produced dense
# odd hi-hat counts (6/7 a bar) where the corpus sits cleanly on 4 (quarter) and 8 (eighth).
# Real charts pick ONE groove for a phrase and repeat it; snapping each bar independently to
# its own nearest template makes neighbours diverge and reads "thrown together".
#
# So instead of per-bar matching we (1) gather the PLAIN groove bars, (2) segment them into
# sections of consecutive SIMILAR bars, (3) majority-VOTE one groove per section -- a grid
# slot survives only if it fires in more than half the section's bars, so a stray bleed hat
# in 1 of 8 bars is voted out and a quarter-note hat stays 4 hits, not an inflated 6-8 -- and
# (4) snap that clean voted groove to the nearest real template (simplify-biased) and write
# the SAME groove to every plain bar in the section. Fills, crashes, open hat and feet are
# untouched (the fill/accent layer).
SECTION_TOL = 5      # (retained for reference) Hamming tolerance when grouping raw bars
WINDOW = 5           # sliding-window radius (plain bars) for the consistency mode filter.
# Tuned on First Date vs a 120-chart Extreme corpus sample: W=5 lands the groove BACKBONE
# (kick+snare+closed-hat) at 15% adjacent-identical, matching the corpus's 16% -- i.e. as
# repetitive/neat as real charts without over-flattening genuine section changes.
MATCH_TEMPLATE = False   # emit the voted consensus directly (True re-maps it to the nearest
# real template, which can re-add rotated 16th jitter -- the consensus is already clean).


def _q16(bar, ch):
    return _q16_collapse(list(bar.get(ch, {})))


def _popcount(m):
    return bin(m).count("1")


def _lane_dist(a, b):
    return sum(_hamming(a[i], b[i]) for i in range(4))


def _match_simplest(kshr, tier):
    """Nearest real template to a groove, SIMPLIFY-biased: among templates at the minimum
    Hamming distance prefer the FEWEST hits (a quarter beats an eighth), then the smallest
    phase shift, then the most common. Returns ((k,s,h,r), distance)."""
    k, s, h, r = kshr
    best = None
    best_key = None
    for (tk, ts, th, tr, tf, shift) in _rotated_targets(tier):
        d = _hamming(k, tk) + _hamming(s, ts) + _hamming(h, th) + _hamming(r, tr)
        hits = _popcount(tk) + _popcount(ts) + _popcount(th) + _popcount(tr)
        key = (d, hits, shift, -tf)
        if best_key is None or key < best_key:
            best_key = key
            best = (tk, ts, th, tr)
    return best, (best_key[0] if best_key else 99)


def snap_sections(events, barlens, bpm, tier="advanced"):
    """Section-first aggressive grooming (see the block comment above). Two stages:

      A. per-bar snap -- each plain groove bar is snapped to the nearest real template
         (simplify-biased), turning a jittery transcription into one of a small vocabulary
         of clean grooves;
      B. consistency mode filter -- a sliding window of neighbouring plain bars adopts the
         LOCAL MAJORITY template, so isolated bar-to-bar flicker collapses into a repeated
         phrase groove (neat like the corpus) while a genuine section change (a new groove
         that persists) still survives.

    Fills, crashes, open hat and feet are untouched. Mutates ``events``; returns
    (events, changed_bar_count)."""
    tier = str(tier).lower()
    plain = []                                        # (index, raw q16 masks)
    for i, bar in enumerate(events):
        bl = barlens[i] if i < len(barlens) else Fraction(1)
        if bl != Fraction(1):
            continue
        if sum(len(bar.get(c, {})) for c in TOMS) >= 3:
            continue                                  # tom fill -> keep the fill
        if _is_snare_roll(bar):
            continue                                  # snare roll -> keep the fill
        if not (bar.get("11") or bar.get("19")):
            continue                                  # no timekeeper -> not a groove bar
        tk_pos = list(bar.get("11", {})) or list(bar.get("19", {}))
        if _tripletish(tk_pos):
            continue                                  # genuine triplet feel -> keep faithful
        masks = (_q16(bar, "13"), _q16(bar, "12"), _q16(bar, "11"), _q16(bar, "19"))
        if sum(_popcount(m) for m in masks) < 4:
            continue                                  # too sparse (intro/breakdown) -> leave it
        plain.append((i, masks))
    if not plain:
        return events, 0

    # ---- B. windowed per-SLOT consensus, then simplify-match ----
    # For each plain bar, vote every groove grid-slot across a window of neighbouring plain
    # bars: a slot survives only if it fires in more than half the window. Overlapping windows
    # give adjacent bars a near-identical consensus (so the phrase repeats = neat), and a slot
    # that only appears sporadically (a bleed ghost) is voted out (so a quarter-note hat stays
    # 4, not an inflated 6-8). The clean consensus is then snapped to the nearest real template.
    masks_list = [m for _, m in plain]
    n = len(masks_list)
    assigned = []
    for p in range(n):
        lo = max(0, p - WINDOW)
        hi = min(n, p + WINDOW + 1)
        w = hi - lo
        cons = []
        for lane in range(4):
            cnt = [0] * GRID
            for q in range(lo, hi):
                m = masks_list[q][lane]
                b = 0
                while m:
                    if m & 1:
                        cnt[b] += 1
                    m >>= 1
                    b += 1
            mask = 0
            timekeeper = lane in (2, 3)               # closed hat / ride
            for b in range(GRID):
                # A 16th-grid off-beat hi-hat/ride slot (odd index) is the most jitter-prone,
                # so it must clear a STRONG majority (>=75%) to survive; the quarter/8th slots
                # (even index) keep a simple majority. This collapses jittery 16th clusters to
                # clean 8ths/quarters (the "simplify") while a genuinely sustained 16th hat run
                # -- present in nearly every window bar -- still passes. Kick/snare keep their
                # syncopation (simple majority on every slot).
                if timekeeper and (b % 2 == 1):
                    keep = cnt[b] * 4 >= w * 3
                else:
                    keep = cnt[b] * 2 > w
                if keep:
                    mask |= (1 << b)
            cons.append(mask)
        cons = tuple(cons)
        if sum(_popcount(m) for m in cons) == 0:
            cons = masks_list[p]                      # window emptied it -> keep the bar itself
        assigned.append(cons)

    # ---- C. section pass: collapse each phrase to ONE groove ----
    # The sliding window still flickers at boundaries (a lone bar between two identical ones
    # can differ). Now that the consensus masks are CLEAN they cluster tightly, so segment the
    # plain bars into sections of near-identical consensus and force every bar in a section to
    # the section's MODE groove. This is what makes a phrase actually repeat, like a real chart.
    def _dist4(a, b):
        return sum(_hamming(a[l], b[l]) for l in range(4))

    sections = []
    cur = [0]
    for p in range(1, len(assigned)):
        if _dist4(assigned[p], assigned[cur[0]]) <= SECTION_TOL:
            cur.append(p)
        else:
            sections.append(cur)
            cur = [p]
    if cur:
        sections.append(cur)
    for sec in sections:
        if len(sec) < 2:
            continue
        mode = Counter(assigned[p] for p in sec).most_common(1)[0][0]
        for p in sec:
            assigned[p] = mode

    # ---- D. optional idiom snap + emit ----
    changed = 0
    cache = {}
    for (i, _), cons in zip(plain, assigned):
        k, s, h, r = cons
        if r and not h:
            tmpl = cons                               # ride-timekeeper -> keep (templates are hat-based)
        elif MATCH_TEMPLATE:
            if cons not in cache:
                best, _bd = _match_simplest(cons, tier)
                cache[cons] = best if best is not None else cons
            tmpl = cache[cons]
        else:
            tmpl = cons                               # emit the clean voted consensus directly
        for ch, mask in zip(GROOVE, tmpl):
            if mask:
                events[i][ch] = {Fraction(b, GRID): _CANON[ch] for b in _bits(mask)}
            else:
                events[i].pop(ch, None)
        changed += 1
    return events, changed


# In a typical DTXMania kit the RIGHT cymbal and the RIDE are the same physical cymbal, so
# grouping folds the right cymbal (16) onto the RIDE lane (19) -- DTXMania players expect the
# grouped hits to read on the ride. The LEFT crash (1A) is a separate cymbal on the left and
# is deliberately left ungrouped.
_GROUP_SRC = ("16",)
_RD = "19"


def group_right_cymbals(events):
    """Consolidate the right cymbal (16) onto the single RIDE lane (19), the way most
    DTXMania kits play them (right cymbal and ride are one cymbal, and DTXMania reads the
    grouped hits on the ride). The LEFT crash (1A) is a separate left-hand cymbal and is left
    exactly where it is. Mutates ``events``; returns notes moved. A tick that already has a
    ride keeps it (no duplicate); otherwise the right-cymbal note is moved to 19 with the ride
    sample. Hi-hats and everything else untouched."""
    moved = 0
    for bar in events:
        dst = bar.get(_RD)
        for ch in _GROUP_SRC:
            src = bar.get(ch)
            if not src:
                continue
            if dst is None:
                dst = {}
                bar[_RD] = dst
            for pos in src:
                if pos not in dst:
                    dst[pos] = dtx.LANE_DEFAULT_SLOT[_RD]
                    moved += 1
            bar.pop(ch, None)
    return events, moved


_HHO = "18"          # open hi-hat
_LP = "1B"           # left-foot pedal (hi-hat chick)
_LBD = "1C"          # left-foot double bass


def openhat_to_left_pedal(events):
    """Move every open hi-hat (18) onto the left-foot pedal lane (1B). A niche preference:
    some players chart the open hi-hat as a left-foot chick. Mutates ``events``; returns the
    number of notes moved. The one-left-foot rule is preserved: a tick already using the left
    foot (LP 1B or double-bass LBD 1C) is left as-is and its open hat is simply dropped (the
    foot can't play two things at once). Everything else is untouched."""
    moved = 0
    for bar in events:
        src = bar.get(_HHO)
        if not src:
            continue
        dst = bar.setdefault(_LP, {})
        busy = bar.get(_LBD, {})
        for pos in src:
            if pos in dst or pos in busy:
                continue                              # left foot already busy at this tick
            dst[pos] = dtx.LANE_DEFAULT_SLOT[_LP]
            moved += 1
        if not dst:
            bar.pop(_LP, None)
        bar.pop(_HHO, None)
    return events, moved
