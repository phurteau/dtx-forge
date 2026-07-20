"""Playability checker: verify a chart can realistically be played by a human
(2 hands, 2 feet) and optionally auto-relax impossible passages.

Limb model:
  Right foot  -> BD (kick)
  Left foot   -> LP (hi-hat pedal / left bass)
  2 hands     -> everything else (snare, hats, toms, cymbals, ride)
Flags:
  * a single foot asked to play faster than humanly sustainable
  * a single hand pattern faster than sustainable
  * more simultaneous hand-notes than 2 hands
  * more than 4 limbs at one instant
"""
from fractions import Fraction
from . import notes as N

# human limits (seconds between successive hits for ONE limb)
FOOT_MIN = 0.105      # ~one foot sustainable ceiling (~9.5 hits/s)
HAND_MIN = 0.085      # ~one hand (~11.7 hits/s); two hands alternate faster
SIMUL_EPS = 0.012     # notes within 12 ms are "simultaneous"


def _limb_of(ch):
    if ch == N.BD:
        return "RF"
    if ch == N.LP:
        return "LF"
    return "H"        # a hand note (assigned to one of two hands later)


def analyze(events, barlens, bpm):
    flat = N.flatten(events)
    for n in flat:
        n["t"] = N.abs_time(n["m"], n["pos"], barlens, bpm)
        n["limb"] = _limb_of(n["ch"])
    issues = []

    # ---- feet: each foot must not exceed its rate ----
    for limb, mn, name in (("RF", FOOT_MIN, "right foot (kick)"),
                           ("LF", FOOT_MIN, "left foot (pedal)")):
        ts = sorted(n["t"] for n in flat if n["limb"] == limb)
        for i in range(1, len(ts)):
            dt = ts[i] - ts[i-1]
            if dt < mn - 1e-6 and dt > SIMUL_EPS:   # faster than sustainable
                issues.append({"type": "foot_too_fast", "limb": name,
                               "t": round(ts[i], 3), "gap_ms": round(dt*1000),
                               "measure": _m_at(ts[i], barlens, bpm)})

    # ---- hands: group simultaneous hand notes; need <=2 hands ----
    hands = sorted((n for n in flat if n["limb"] == "H"), key=lambda n: n["t"])
    clusters = _cluster(hands)
    for c in clusters:
        if len(c) > 2:
            issues.append({"type": "too_many_hands", "count": len(c),
                           "t": round(c[0]["t"], 3),
                           "measure": _m_at(c[0]["t"], barlens, bpm)})
    # each hand's sustained speed: split alternating, check pair spacing
    ctimes = [c[0]["t"] for c in clusters]
    for i in range(2, len(ctimes)):
        dt = ctimes[i] - ctimes[i-2]        # same hand plays every other cluster
        if dt < HAND_MIN - 1e-6 and dt > SIMUL_EPS:
            issues.append({"type": "hands_too_fast", "t": round(ctimes[i], 3),
                           "gap_ms": round(dt*1000),
                           "measure": _m_at(ctimes[i], barlens, bpm)})

    # ---- overall limb count at an instant ----
    allc = _cluster(sorted(flat, key=lambda n: n["t"]))
    for c in allc:
        limbs = set(n["limb"] for n in c)
        # count hands needed (each hand note is a hand, up to 2)
        need = min(2, sum(1 for n in c if n["limb"] == "H")) \
               + (1 if any(n["limb"] == "RF" for n in c) else 0) \
               + (1 if any(n["limb"] == "LF" for n in c) else 0)
        raw = len(c)
        if raw > 4:
            issues.append({"type": "over_four_limbs", "count": raw,
                           "t": round(c[0]["t"], 3),
                           "measure": _m_at(c[0]["t"], barlens, bpm)})

    total = len(flat)
    n_issue = len(issues)
    score = 100 if total == 0 else max(0, round(100 * (1 - n_issue / max(total, 1))))
    by_type = {}
    for it in issues:
        by_type[it["type"]] = by_type.get(it["type"], 0) + 1
    verdict = "playable" if n_issue == 0 else ("tight" if score >= 92 else "problem")
    return {"score": score, "verdict": verdict, "total_notes": total,
            "issue_count": n_issue, "by_type": by_type,
            "issues": issues[:40]}


def _cluster(sorted_notes):
    clusters, cur = [], []
    for n in sorted_notes:
        if cur and n["t"] - cur[-1]["t"] > SIMUL_EPS:
            clusters.append(cur); cur = []
        cur.append(n)
    if cur:
        clusters.append(cur)
    return clusters


def _m_at(t, barlens, bpm):
    starts = N.bar_starts(barlens, bpm)
    for i in range(len(starts)-1):
        if starts[i] <= t < starts[i+1]:
            return i
    return len(barlens)-1


# priority for dropping a hand note when >2 collide (lower = drop first)
_DROP_PRIORITY = [N.HHc, N.HHo, N.RD, N.LC, N.CY, N.HT, N.LT, N.FT, N.SD]

def auto_relax(events, barlens, bpm, allow_doublebass=True, max_passes=3):
    """Best-effort fix: split too-fast kicks to the left foot (if allowed) and
    drop the lowest-priority note where >2 hands collide. Returns (events, report)."""
    from . import humanize
    report_before = analyze(events, barlens, bpm)
    for _ in range(max_passes):
        rep = analyze(events, barlens, bpm)
        if rep["issue_count"] == 0:
            break
        changed = False
        # fix too-many-hands by dropping lowest-priority simultaneous note
        flat = N.flatten(events)
        for n in flat:
            n["t"] = N.abs_time(n["m"], n["pos"], barlens, bpm)
        clusters = _cluster(sorted((n for n in flat if _limb_of(n["ch"]) == "H"),
                                   key=lambda n: n["t"]))
        for c in clusters:
            if len(c) > 2:
                drop = sorted(c, key=lambda n: _DROP_PRIORITY.index(n["ch"])
                              if n["ch"] in _DROP_PRIORITY else 99)[:len(c)-2]
                for d in drop:
                    events[d["m"]].get(d["ch"], {}).pop(d["pos"], None)
                    if events[d["m"]].get(d["ch"]) == {}:
                        events[d["m"]].pop(d["ch"], None)
                    changed = True
        # fix foot-too-fast by moving alternate kicks to left foot
        if allow_doublebass:
            before = analyze(events, barlens, bpm)["by_type"].get("foot_too_fast", 0)
            if before:
                events, _n = humanize.apply_double_bass(events, barlens, bpm, True)
                changed = True
        if not changed:
            break
    report_after = analyze(events, barlens, bpm)
    return events, {"before": report_before, "after": report_after}
