"""Shared note helpers: flatten/unflatten the per-measure event structure and
compute absolute times. Events = list[measure] of {channel: {Fraction pos: label}}."""
import copy
from fractions import Fraction

# DTX drum channels
BD, SD, HHc, HHo, LP = "13", "12", "11", "18", "1B"
HT, LT, FT, CY, LC, RD = "14", "15", "17", "16", "1A", "19"

HAND_LANES = {SD, HHc, HHo, HT, LT, FT, CY, LC, RD}
FOOT_LANES = {BD, LP}


def flatten(events):
    """-> list of dicts {m, pos(Fraction), ch, lab} sorted by (m, pos)."""
    out = []
    for mi, chan in enumerate(events):
        for ch, slots in chan.items():
            for pos, lab in slots.items():
                out.append({"m": mi, "pos": pos, "ch": ch, "lab": lab})
    out.sort(key=lambda n: (n["m"], float(n["pos"])))
    return out


def unflatten(notes, n_measures):
    events = [dict() for _ in range(n_measures)]
    for n in notes:
        events[n["m"]].setdefault(n["ch"], {})[n["pos"]] = n["lab"]
    return events


def bar_seconds(barlens, bpm):
    """seconds per measure (barlen is whole-notes; 4/4 -> 1.0)."""
    whole = 4 * 60.0 / bpm
    return [float(bl) * whole for bl in barlens]


def bar_starts(barlens, bpm):
    secs = bar_seconds(barlens, bpm)
    starts = [0.0]
    for s in secs:
        starts.append(starts[-1] + s)
    return starts


def abs_time(m, pos, barlens, bpm):
    starts = bar_starts(barlens, bpm)
    whole = 4 * 60.0 / bpm
    return starts[m] + float(pos) * float(barlens[m]) * whole


def plan_leadin(barlens, bpm, seconds, quantum=128):
    """Plan empty 'lead-in' bars for a `seconds`-long intro that precedes the first charted
    note, so a chart can ride on top of the FULL (untrimmed) backing track with its first
    note still landing on the first real drum hit.

    Returns a list of bar lengths (whole-note ``Fraction``s) to PREPEND to ``barlens``, or
    ``[]`` when no lead-in is needed or the inputs are unusable. The total prepended
    duration approximates ``seconds`` to within ``1/quantum`` of a whole note (~16 ms at
    120 BPM with the default quantum=128). A short fractional 'pickup' bar (the remainder)
    is placed first, then full-length bars equal to the chart's first bar, so the body
    stays on a clean bar grid. Never raises - bad input yields ``[]``."""
    try:
        bpm = float(bpm)
        seconds = float(seconds)
    except (TypeError, ValueError):
        return []
    if bpm <= 0 or seconds <= 0 or not barlens:
        return []
    whole = 4 * 60.0 / bpm                        # seconds per whole-note
    lead_wholes = seconds / whole                 # whole-notes of intro to insert
    total = Fraction(round(lead_wholes * quantum), quantum)
    if total <= 0:
        return []
    unit = Fraction(barlens[0]) if barlens[0] and barlens[0] > 0 else Fraction(1)
    n_full = int(total // unit)                    # whole 'unit'-length bars that fit
    rem = total - n_full * unit                    # leftover -> short pickup bar
    lead = []
    if rem > 0:
        lead.append(rem)                           # pickup first (classic anacrusis)
    lead += [unit] * n_full
    return lead


def prepend_leadin(events, barlens, bpm, seconds, quantum=128):
    """Pure: return ``(events, barlens, n_leadin_bars)`` with empty intro bars prepended per
    :func:`plan_leadin`. Every existing note keeps its bar-relative position, so it simply
    shifts later in absolute time by the lead-in duration (≈ ``seconds``). Returns the inputs
    unchanged with ``n=0`` when no lead-in is needed or on any error; never raises."""
    try:
        lead = plan_leadin(barlens, bpm, seconds, quantum)
        if not lead:
            return events, barlens, 0
        new_events = [dict() for _ in lead] + copy.deepcopy(list(events))
        new_barlens = list(lead) + list(barlens)
        return new_events, new_barlens, len(lead)
    except Exception:
        return events, barlens, 0

