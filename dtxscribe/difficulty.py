"""Auto difficulty rating (DTXMania 0.00–9.99 scale).

Estimates how hard a chart is to PLAY, rated from a skilled-drummer reference so
the number is honest - a beginner reading it gets a realistic sense of the demand,
rather than an artificially low "easy". Blends five signals:

  * density   - overall notes per second
  * burst     - busiest 1-second window (fills / bursts)
  * feet      - fastest sustained single-foot rate (double-bass pressure)
  * hands     - fastest sustained hand-stream rate
  * coord     - how often 3+ limbs fire together + double-bass presence
  * variety   - how much of the kit is used (toms/cymbals/ride richness)

Each maps to 0..1, is weighted, then scaled to 0..9.99. Returns hundredths (int),
matching DTXMania's stored value (e.g. 6.40 -> 640).
"""
from . import notes as N

# calibration anchors (rate = hits/sec). Tuned so a plain rock groove reads ~3,
# a busy idol/pop chart ~6–7, and relentless double-bass metal ~8.5–9.5.
_NPS_LO, _NPS_HI   = 2.0, 13.0
_BURST_LO, _BURST_HI = 5.0, 22.0
_FOOT_LO, _FOOT_HI = 3.0, 12.0
_HAND_LO, _HAND_HI = 4.0, 14.0
SIMUL_EPS = 0.012


def _clamp01(x):
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def _fast_rate(times, frac=0.10):
    """Sustained fast rate for a limb: median of the fastest `frac` of gaps -> hits/s.
    Using a robust percentile (not the single min gap) avoids one grace note
    inflating difficulty."""
    ts = sorted(times)
    gaps = [ts[i] - ts[i-1] for i in range(1, len(ts)) if ts[i] - ts[i-1] > SIMUL_EPS]
    if not gaps:
        return 0.0
    gaps.sort()
    k = max(1, int(len(gaps) * frac))
    fastest = gaps[:k]
    med = fastest[len(fastest) // 2]
    return 1.0 / med if med > 0 else 0.0


def _peak_nps(times, win=1.0):
    """Max notes in any `win`-second sliding window, as notes/sec."""
    ts = sorted(times)
    if not ts:
        return 0.0
    best = 0; j = 0
    for i in range(len(ts)):
        while ts[i] - ts[j] > win:
            j += 1
        best = max(best, i - j + 1)
    return best / win


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

    foot_t = [n["t"] for n in flat if n["ch"] in N.FOOT_LANES]
    rf_t   = [n["t"] for n in flat if n["ch"] == N.BD]
    lf_t   = [n["t"] for n in flat if n["ch"] == N.LP]
    hand_t = [n["t"] for n in flat if n["ch"] in N.HAND_LANES]

    nps   = total / span
    burst = _peak_nps(times)
    foot  = max(_fast_rate(rf_t), _fast_rate(lf_t), _fast_rate(foot_t) * 0.6)
    hands = _fast_rate(hand_t)

    # coordination: share of simultaneous clusters that need 3+ limbs
    clusters = _cluster(sorted(flat, key=lambda n: n["t"]))
    heavy = sum(1 for c in clusters if _limbs_needed(c) >= 3)
    coord = heavy / max(1, len(clusters))
    if lf_t:                                   # any real double-bass adds pressure
        coord = min(1.0, coord + 0.15)

    # kit variety: distinct lanes used, 3 (kick/snare/hat) .. 9+
    lanes = len(set(n["ch"] for n in flat))
    variety = _clamp01((lanes - 3) / 6.0)

    f_density = _clamp01((nps   - _NPS_LO)   / (_NPS_HI   - _NPS_LO))
    f_burst   = _clamp01((burst - _BURST_LO) / (_BURST_HI - _BURST_LO))
    f_feet    = _clamp01((foot  - _FOOT_LO)  / (_FOOT_HI  - _FOOT_LO))
    f_hands   = _clamp01((hands - _HAND_LO)  / (_HAND_HI  - _HAND_LO))

    raw = (0.26 * f_density + 0.20 * f_burst + 0.20 * f_feet
           + 0.17 * f_hands + 0.11 * coord + 0.06 * variety)

    # skilled-drummer reference: a genuine full-kit groove is never "trivial",
    # so lift the floor a touch and let the top reach 9.99 for extreme charts.
    display = round(min(9.99, 0.6 + raw * 9.4), 2)
    return {
        "value": int(round(display * 100)),
        "display": display,
        "factors": {
            "nps": round(nps, 2), "burst": round(burst, 1),
            "foot_rate": round(foot, 1), "hand_rate": round(hands, 1),
            "coord": round(coord, 2), "lanes": lanes,
        },
    }


def _limbs_needed(cluster):
    h = sum(1 for n in cluster if n["ch"] in N.HAND_LANES)
    need = min(2, h)
    if any(n["ch"] == N.BD for n in cluster):
        need += 1
    if any(n["ch"] == N.LP for n in cluster):
        need += 1
    return need


def _cluster(sorted_notes):
    clusters, cur = [], []
    for n in sorted_notes:
        if cur and n["t"] - cur[-1]["t"] > SIMUL_EPS:
            clusters.append(cur); cur = []
        cur.append(n)
    if cur:
        clusters.append(cur)
    return clusters
