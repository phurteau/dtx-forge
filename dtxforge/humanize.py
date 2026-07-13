"""Humanize: add realistic left-foot technique to a chart.

hi-hat foot  -> adds left-pedal (LP) 'chick' notes around hi-hat play (1:1/medium/basic)
double bass  -> ON/OFF toggle. When ON, the engine detects kicks that are too fast to
                play one-legged and converts those (and only those) to a DOUBLE KICK:
                the run alternates right-foot kick (BD, lane 13) and left-foot kick
                (LP w/ kick sample, lane 1B), DTXMania-style. Kicks slow enough for one
                foot are left untouched.

Both hi-hat-foot and double-bass write to lane 1B (left pedal); double-bass chips use
the kick sample so the left pedal actually sounds like a bass drum."""
from fractions import Fraction
from . import notes as N

LP_KICK = "02"   # bd.wav on the left pedal lane (double bass / left-foot kick)
LP_FOOT = "0C"   # lp.wav (soft foot hi-hat)

# Fastest a single foot can realistically repeat (seconds between kicks).
# Anything faster than this within a run is offloaded to the left foot.
SINGLE_FOOT_MIN = 0.115     # ~130 ms is a comfortable single-foot ceiling; 115 ms allows brisk 16ths


def _measure_positions(barlen, per_whole):
    """Return list of Fraction beat positions (0..1) at a given subdivision."""
    slots = max(1, round(float(barlen) * per_whole))
    return [Fraction(i, slots) for i in range(slots)]


def apply_hihat_foot(events, barlens, level):
    """Add left-foot pedal (LP) notes to simulate hi-hat pedal work.
    1to1: foot on every quarter where no hand hat/cymbal already sits + a 'chick'
          right after each open hat (to close it).
    medium: foot on beats 2 & 4 (backbeat) only.
    off: nothing added (the drummer's left foot stays free)."""
    if level not in ("1to1", "medium"):
        return events
    for mi, chan in enumerate(events):
        bl = barlens[mi]
        hat_present = any(l in chan for l in (N.HHc, N.HHo, N.RD, N.CY, N.LC))
        if not hat_present:
            continue
        lp = chan.setdefault(N.LP, {})
        occupied = set()
        for l in (N.HHc, N.HHo, N.CY, N.LC, N.RD):
            occupied |= set(chan.get(l, {}).keys())
        # quarter-note grid within the bar
        quarters = _measure_positions(bl, 4)
        if level == "1to1":
            targets = quarters                       # foot keeps time on every beat
        else:  # medium -> beats 2 & 4 (indices 1,3 in 4/4)
            targets = quarters[1::2]
        for q in targets:
            if q not in occupied and q not in lp:
                lp[q] = LP_FOOT
        # foot "chick" right after each open hi-hat to close it (1to1 only)
        if level == "1to1" and N.HHo in chan:
            slots = max(1, round(float(bl) * 16))
            for pos in list(chan[N.HHo].keys()):
                nxt = pos + Fraction(1, slots)
                if nxt < 1 and nxt not in occupied and nxt not in lp:
                    lp[nxt] = LP_FOOT
    return events


def apply_double_bass(events, barlens, bpm, enabled):
    """ON/OFF double kick. When enabled, find kick runs faster than one foot can
    sustain and alternate them onto the left foot (LP with kick sample), so the
    passage plays as a real double-kick (BD + LP). Kicks that are slow enough for
    a single foot are left on BD untouched. Returns count of converted notes.

    A 'run' is a maximal sequence of kicks each spaced < SINGLE_FOOT_MIN apart; we
    keep the run's first hit on the right foot and alternate from there, so only the
    genuinely-too-fast notes move to the left foot."""
    if not enabled:
        return events, 0
    thresh = SINGLE_FOOT_MIN
    kicks = []
    for mi, chan in enumerate(events):
        for pos in chan.get(N.BD, {}):
            kicks.append((N.abs_time(mi, pos, barlens, bpm), mi, pos))
    kicks.sort()
    converted = 0
    foot = "R"
    for i in range(len(kicks)):
        if i == 0:
            foot = "R"; continue
        dt = kicks[i][0] - kicks[i-1][0]
        if dt < thresh - 1e-6:
            # inside a too-fast run: alternate feet
            foot = "L" if foot == "R" else "R"
            if foot == "L":
                _, mi, pos = kicks[i]
                if pos in events[mi].get(N.BD, {}):
                    events[mi][N.BD].pop(pos, None)
                    if not events[mi].get(N.BD):
                        events[mi].pop(N.BD, None)
                    events[mi].setdefault(N.LP, {})[pos] = LP_KICK
                    converted += 1
        else:
            foot = "R"   # comfortable gap: run resets, stay on right foot
    return events, converted


def humanize(events, barlens, bpm, hihat_level="off", doublebass=False):
    # double bass first (claims LP for fast kicks), then hi-hat foot fills the rest
    events, converted = apply_double_bass(events, barlens, bpm, doublebass)
    events = apply_hihat_foot(events, barlens, hihat_level)
    return events, converted
