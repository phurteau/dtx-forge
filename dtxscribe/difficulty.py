"""Auto difficulty rating (DTXMania 0.00-9.99 scale).

Driven by the published level reference table in docs/difficulty-levels.md. Every level
from 1.0 to 9.5 is anchored to two measurable quantities:

  * avg density - notes per second across the whole chart
  * 2-sec peak  - notes per second in the busiest 2-second window (fills and bursts)

Both rise monotonically with level, so each column is an invertible lookup. A chart is
rated by measuring its own density and 2-sec peak, mapping each back onto the table to
get a level, then averaging the two. The score a chart gets is therefore the level whose
density and burst load it actually matches. The skill descriptions in the table (double
bass, rolls, and so on) are the qualitative context behind those two rate columns; the
rates already climb as those skills appear, so measuring them is enough.

Returns hundredths (int), matching DTXMania stored values (e.g. 6.40 -> 640).
"""
from . import notes as N

# Level anchors from docs/difficulty-levels.md: (level, avg_density_nps, peak_2s_nps).
_LEVEL_ANCHORS = [
    (1.0, 1.7, 3.0),
    (1.5, 1.9, 3.5),
    (2.0, 2.2, 4.0),
    (2.5, 2.5, 4.5),
    (3.0, 2.8, 5.0),
    (3.5, 3.5, 6.0),
    (4.0, 4.2, 7.0),
    (4.5, 4.9, 8.0),
    (5.0, 5.6, 8.5),
    (5.5, 6.1, 10.0),
    (6.0, 6.8, 10.5),
    (6.5, 7.5, 12.0),
    (7.0, 8.4, 13.5),
    (7.5, 9.1, 14.5),
    (8.0, 9.6, 16.0),
    (8.5, 10.4, 17.5),
    (9.0, 11.3, 19.0),
    (9.5, 12.8, 22.5),
]
_DENSITY_WEIGHT = 0.5   # avg density and 2-sec peak contribute equally
_FLOOR = 1.0            # easiest defined level; a non-empty chart never rates below it


def _peak_nps(times, win=2.0):
    """Max notes in any win-second sliding window, expressed as notes/sec."""
    ts = sorted(times)
    if not ts:
        return 0.0
    best = 0
    j = 0
    for i in range(len(ts)):
        while ts[i] - ts[j] > win:
            j += 1
        best = max(best, i - j + 1)
    return best / win


def _interp_level(value, idx):
    """Invert one column of the anchor table: given a measured metric, return the level
    it corresponds to. idx=1 reads avg density, idx=2 reads the 2-second peak. Below the
    first anchor the line runs down to (0 metric, 0 level); above the last anchor it keeps
    the final segment slope, so a very busy chart can still climb toward 9.99."""
    pts = [(a[idx], a[0]) for a in _LEVEL_ANCHORS]     # (metric, level), ascending
    m0, l0 = pts[0]
    if value <= m0:
        return (value / m0 * l0) if m0 > 0 else l0
    for (ma, la), (mb, lb) in zip(pts, pts[1:]):
        if ma <= value <= mb:
            return la if mb == ma else la + (value - ma) / (mb - ma) * (lb - la)
    (ma, la), (mb, lb) = pts[-2], pts[-1]
    slope = (lb - la) / (mb - ma) if mb != ma else 0.0
    return lb + (value - mb) * slope


def compute(events, barlens, bpm):
    flat = N.flatten(events)
    total = len(flat)
    if total == 0:
        return {"value": 100, "display": 1.0, "factors": {}}   # 1.00 floor

    for n in flat:
        n["t"] = N.abs_time(n["m"], n["pos"], barlens, bpm)
    times = [n["t"] for n in flat]
    span = max(times) - min(times)
    span = span if span > 1e-6 else 1.0

    avg_density = total / span
    peak_2s = _peak_nps(times, win=2.0)

    lvl_density = _interp_level(avg_density, 1)
    lvl_peak = _interp_level(peak_2s, 2)
    level = _DENSITY_WEIGHT * lvl_density + (1.0 - _DENSITY_WEIGHT) * lvl_peak

    display = round(max(_FLOOR, min(9.99, level)), 2)
    return {
        "value": int(round(display * 100)),
        "display": display,
        "factors": {
            "avg_density": round(avg_density, 2),
            "peak_2s": round(peak_2s, 1),
            "level_density": round(lvl_density, 2),
            "level_peak": round(lvl_peak, 2),
        },
    }