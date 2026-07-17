"""Deep drum-corpus miner: extract ACTIONABLE drumming facts from the full GITADORA corpus
(6,740 real charts) to ground the neatening logic. Outputs a human report + a machine-readable
JSON (drum_facts.json) that the app can ingest to calibrate thresholds.

Facts mined:
  A. per-lane subdivision distribution (do cymbals really cap at 1/16? do kicks reach 1/32?)
  B. per-lane OFF-BEAT frequency (are off-beats real, and on which lanes?)
  C. triplet/swing bar prevalence (how much of the corpus needs the swing guard?)
  D. odd-meter prevalence (non-4/4 bars, from channel 02)
  E. bar-to-bar hi-hat repetition rate (calibrates KEEP_PCT / the 'neat' target)
  F. same-lane min spacing per lane (grounds the de-flam / bleed threshold)
  G. simultaneous-lane co-occurrence (which lanes idiomatically stack)
"""
import os, re, glob, codecs, json, sys
from fractions import Fraction
from collections import Counter, defaultdict

CORPUS = os.environ.get("DTX_CORPUS", os.path.join(os.path.expanduser("~"), ".scout", "_gitadora_corpus", "gitadora_all", "charts"))
DRUM = {"11","12","13","14","15","16","17","18","19","1A","1B","1C"}
LANE_NAME = {"11":"closed-hat","12":"snare","13":"kick","14":"hi-tom","15":"low-tom",
             "16":"crash","17":"floor-tom","18":"open-hat","19":"ride","1A":"left-crash",
             "1B":"left-pedal","1C":"left-bass"}
METER_CH = "02"     # measure-length multiplier (odd meter)
BPM_CH = "08"       # extended BPM ref (we mainly use header #BPM)


def difficulty(fn):
    f = fn.lower()
    if "mas" in f or "mst" in f: return "master"
    if "ext" in f: return "extreme"
    if "adv" in f: return "advanced"
    if "bas" in f or "bsc" in f: return "basic"
    return "other"


def read(path):
    for enc in ("shift_jis","cp932","utf-8"):
        try: return codecs.open(path, encoding=enc).read()
        except Exception: pass
    return None


def sub_bucket(fr):
    d = fr.denominator
    if d in (1,2,4): return "quarter+"
    if d == 8: return "8th"
    if d == 16: return "16th"
    if d == 32: return "32nd"
    if d >= 64: return "64th+"
    if d % 3 == 0: return "triplet"
    return "other"


def parse(txt):
    """-> (bars dict {bar:{ch:{Fraction:val}}}, meters {bar:Fraction}, bpm float|None)."""
    bars = defaultdict(lambda: defaultdict(dict))
    meters = {}
    bpm = None
    mh = re.search(r'#BPM[:\s]+([0-9.]+)', txt)
    if mh:
        try: bpm = float(mh.group(1))
        except Exception: pass
    for line in txt.splitlines():
        m = re.match(r'#(\d\d\d)([0-9A-Fa-f]{2}):\s*([0-9A-Za-z.]+)', line.strip())
        if not m: continue
        bi = int(m.group(1)); ch = m.group(2).upper(); data = m.group(3)
        if ch == METER_CH:
            try: meters[bi] = Fraction(str(float(data))).limit_denominator(64)
            except Exception: pass
            continue
        if ch not in DRUM: continue
        cells = [data[i:i+2] for i in range(0, len(data)-1, 2)]
        n = len(cells)
        if not n: continue
        for idx, c in enumerate(cells):
            if c != "00":
                bars[bi][ch][Fraction(idx, n)] = c
    return bars, meters, bpm


# accumulators
sub_by_lane = defaultdict(Counter)                 # A
offbeat = defaultdict(lambda: [0, 0])              # B: [offbeat_hits, total_hits]
triplet_bars = [0, 0]                              # C: [triplet_bars, total_bars]
odd_meter = [0, 0]                                 # D: [nonwhole_bars, total_bars]
hat_repeat = [0, 0]                                # E: [identical_adjacent, adjacent_pairs]
lane_spacing = defaultdict(Counter)               # F: same-lane consecutive gap (in beats) hist
cooccur = Counter()                                # G: frozenset of lanes sharing a tick
charts = 0

QUARTERS = {Fraction(0,1), Fraction(1,4), Fraction(1,2), Fraction(3,4)}

files = sorted(glob.glob(os.path.join(CORPUS, "*", "*", "*.dtx")))
print(f"scanning {len(files)} charts...", file=sys.stderr)
for k, path in enumerate(files):
    if k % 500 == 0:
        print(f"  {k}/{len(files)}", file=sys.stderr)
    txt = read(path)
    if not txt: continue
    bars, meters, bpm = parse(txt)
    if not bars: continue
    charts += 1
    idxs = sorted(bars)
    hat_sigs = []
    for bi in idxs:
        chans = bars[bi]
        bl = meters.get(bi, Fraction(1))
        odd_meter[1] += 1
        if bl != Fraction(1): odd_meter[0] += 1
        # per-lane facts
        bar_is_triplet = False
        # co-occurrence: group hits by tick
        tick_lanes = defaultdict(set)
        for ch, sm in chans.items():
            for p, v in sm.items():
                sub_by_lane[ch][sub_bucket(p)] += 1
                offbeat[ch][1] += 1
                if p not in QUARTERS: offbeat[ch][0] += 1
                if p.denominator % 3 == 0: bar_is_triplet = True
                tick_lanes[p].add(ch)
            # same-lane spacing (in fraction-of-whole; *4 = beats)
            ps = sorted(sm)
            for a, b in zip(ps, ps[1:]):
                gap = b - a
                lane_spacing[ch][gap] += 1
        for lanes in tick_lanes.values():
            if len(lanes) >= 2:
                cooccur[frozenset(lanes)] += 1
        triplet_bars[1] += 1
        if bar_is_triplet: triplet_bars[0] += 1
        # hi-hat repetition signature
        hat_sigs.append(tuple(sorted(str(p) for p in chans.get("11", {}))))
    for a, b in zip(hat_sigs, hat_sigs[1:]):
        if a and a == b:
            hat_repeat[0] += 1
        hat_repeat[1] += 1

# ---- report ----
def pct(n, d): return round(100.0 * n / d, 1) if d else 0.0

print(f"\n{'='*70}\nDEEP DRUM-CORPUS FACTS  ({charts} charts parsed)\n{'='*70}")

print("\n[A] SUBDIVISION USAGE PER LANE (% of that lane's hits)")
order = ["quarter+","8th","16th","triplet","32nd","64th+","other"]
for ch in ["13","12","11","19","18","16","1A","14","15","17","1B","1C"]:
    c = sub_by_lane.get(ch)
    if not c: continue
    tot = sum(c.values())
    row = "  ".join(f"{b}:{pct(c[b],tot)}" for b in order if c[b])
    print(f"  {LANE_NAME[ch]:12s} ({tot:6d})  {row}")

print("\n[B] OFF-BEAT FREQUENCY PER LANE (% of hits NOT on a quarter 1/2/3/4)")
for ch in ["11","19","18","13","12","16"]:
    o = offbeat.get(ch)
    if o and o[1]:
        print(f"  {LANE_NAME[ch]:12s}  {pct(o[0],o[1])}%  ({o[0]}/{o[1]})")

print(f"\n[C] SWING/TRIPLET bars: {pct(triplet_bars[0],triplet_bars[1])}%  "
      f"({triplet_bars[0]}/{triplet_bars[1]} bars contain a triplet-grid hit)")
print(f"[D] ODD-METER bars:    {pct(odd_meter[0],odd_meter[1])}%  "
      f"({odd_meter[0]}/{odd_meter[1]} bars are non-4/4)")
print(f"[E] HI-HAT bar-to-bar REPEAT: {pct(hat_repeat[0],hat_repeat[1])}%  "
      f"(adjacent bars with identical hat pattern)")

print("\n[F] SAME-LANE SPACING - smallest gaps (fraction of a whole note; 1/16=0.0625)")
for ch in ["11","19","16","12","13"]:
    c = lane_spacing.get(ch)
    if not c: continue
    tot = sum(c.values())
    smallest = sorted(c.items())[:5]
    parts = "  ".join(f"{float(g):.4f}:{pct(n,tot)}%" for g, n in smallest)
    print(f"  {LANE_NAME[ch]:12s}  {parts}")

print("\n[G] TOP SIMULTANEOUS-LANE STACKS (lanes sharing a tick)")
for lanes, n in cooccur.most_common(12):
    names = "+".join(sorted(LANE_NAME[l] for l in lanes))
    print(f"  {n:7d}  {names}")

# ---- machine-readable facts for ingestion ----
facts = {
    "charts": charts,
    "subdivision_pct_by_lane": {LANE_NAME[ch]: {b: pct(c[b], sum(c.values())) for b in order if c[b]}
                                 for ch, c in sub_by_lane.items()},
    "offbeat_pct_by_lane": {LANE_NAME[ch]: pct(o[0], o[1]) for ch, o in offbeat.items() if o[1]},
    "triplet_bar_pct": pct(triplet_bars[0], triplet_bars[1]),
    "odd_meter_bar_pct": pct(odd_meter[0], odd_meter[1]),
    "hat_adjacent_repeat_pct": pct(hat_repeat[0], hat_repeat[1]),
    "max_subdivision_by_lane": {LANE_NAME[ch]: max(order.index(b) for b in c if c[b])
                                 for ch, c in sub_by_lane.items()},
}
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drum_facts.json")
json.dump(facts, open(out, "w"), indent=2)
print(f"\nsaved machine-readable facts -> {out}")
