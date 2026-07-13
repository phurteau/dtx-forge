"""Shared note helpers: flatten/unflatten the per-measure event structure and
compute absolute times. Events = list[measure] of {channel: {Fraction pos: label}}."""
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
