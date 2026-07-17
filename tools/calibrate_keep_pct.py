"""RIGOROUS grounding: calibrate the hi-hat/ride cleanup threshold (KEEP_PCT) EMPIRICALLY
against the real corpus, per tier.

Method (closed-loop, corpus = ground truth):
  1. take real charts (clean, correct) and read their hi-hat/ride timekeeping as GROUND TRUTH;
  2. inject synthetic transcription noise into the timekeeping -- BLEED ghosts (spurious extra
     hits, the false positives real de-bleed must remove) and DROPS (missed onsets) -- the two
     dominant audio-transcription error modes;
  3. run the cleaner (pattern_match.snap_sections) at each candidate KEEP_PCT;
  4. score how well the cleaned output RECOVERS the original real chart (F1 over hat 1/16 slots);
  5. the KEEP_PCT with the best mean F1 per tier is the DATA-CHOSEN threshold.

This picks the thresholds by recovering thousands of real charts from noise, not by hand.
"""
import os, re, glob, codecs, sys, random
from fractions import Fraction
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dtxforge import pattern_match as PM

CORPUS = os.environ.get("DTX_CORPUS", os.path.join(os.path.expanduser("~"), ".scout", "_gitadora_corpus", "gitadora_all", "charts"))
PER_TIER = 160          # charts sampled per tier
CANDIDATES = [20, 25, 30, 35, 38, 40, 45, 50, 55]
P_BLEED = 0.35          # prob a bar gets a spurious extra hat/ride (bleed ghost)
P_DROP = 0.12           # prob each real hat/ride hit is dropped (missed onset)
JITTER = 0.10           # prob a hit is nudged to an adjacent 1/16 (quantization jitter)
random.seed(1234)
GRID = 16


def tier_of(fn):
    f = fn.lower()
    if "mas" in f or "mst" in f: return "master"
    if "ext" in f: return "extreme"
    if "adv" in f: return "advanced"
    if "bas" in f or "bsc" in f: return "basic"
    return "other"


def read(p):
    for enc in ("shift_jis","cp932","utf-8"):
        try: return codecs.open(p, encoding=enc).read()
        except Exception: pass
    return None


def parse_events(txt):
    """-> (events list, barlens list). Only drum channels; 16-grid-friendly."""
    bars = defaultdict(lambda: defaultdict(dict)); meters = {}
    for line in txt.splitlines():
        m = re.match(r'#(\d\d\d)([0-9A-Fa-f]{2}):\s*([0-9A-Za-z.]+)', line.strip())
        if not m: continue
        bi = int(m.group(1)); ch = m.group(2).upper(); data = m.group(3)
        if ch == "02":
            try: meters[bi] = Fraction(str(float(data))).limit_denominator(64)
            except Exception: pass
            continue
        if ch not in {"11","12","13","14","15","16","17","18","19","1A","1B","1C"}: continue
        cells = [data[i:i+2] for i in range(0, len(data)-1, 2)]; n = len(cells)
        for idx, c in enumerate(cells):
            if c != "00": bars[bi][ch][Fraction(idx, n)] = c
    if not bars: return None, None
    hi = max(bars)
    events = []; barlens = []
    for i in range(hi + 1):
        events.append({ch: dict(sm) for ch, sm in bars.get(i, {}).items()})
        barlens.append(meters.get(i, Fraction(1)))
    return events, barlens


def hat16(bar, ch):
    """set of 1/16 slots for a lane, only if all its hits sit on the 1/16 grid (else None)."""
    sm = bar.get(ch)
    if not sm: return set()
    slots = set()
    for p in sm:
        if p.denominator == 0 or 16 % p.denominator != 0:
            return None                       # finer/triplet -> skip this bar for scoring
        slots.add(int(round(float(p) * 16)) % 16)
    return slots


def add_noise(events):
    """Copy events; corrupt ONLY hat(11)/ride(19) with bleed ghosts + drops + jitter."""
    out = []
    for bar in events:
        nb = {ch: dict(sm) for ch, sm in bar.items()}
        for ch in ("11", "19"):
            sm = nb.get(ch)
            if not sm: continue
            # drops + jitter
            new = {}
            for p, v in sm.items():
                if random.random() < P_DROP:
                    continue
                if random.random() < JITTER and p.denominator and 16 % p.denominator == 0:
                    s = (int(round(float(p) * 16)) + random.choice((-1, 1))) % 16
                    new[Fraction(s, 16)] = v
                else:
                    new[p] = v
            # bleed ghost
            if random.random() < P_BLEED:
                s = random.randrange(16)
                new[Fraction(s, 16)] = PM._CANON.get(ch, "01")
            if new: nb[ch] = new
            else: nb.pop(ch, None)
        out.append(nb)
    return out


def score(cleaned, truth):
    """F1 over hat(11)+ride(19) 1/16 slots vs the ground-truth chart."""
    tp = fp = fn = 0
    for cb, tb in zip(cleaned, truth):
        for ch in ("11", "19"):
            g = hat16(tb, ch)
            if g is None: continue            # truth off-grid -> skip
            c = hat16(cb, ch)
            if c is None: c = set()
            tp += len(c & g); fp += len(c - g); fn += len(g - c)
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    return (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0


import copy
files_by_tier = defaultdict(list)
for f in glob.glob(os.path.join(CORPUS, "*", "*", "*.dtx")):
    files_by_tier[tier_of(os.path.basename(f))].append(f)

SEEDS = [1234, 777, 2026]        # average over several noise draws for a robust optimum
print("Calibrating KEEP_PCT by recovering real charts from synthetic transcription noise")
print(f"(averaged over {len(SEEDS)} noise seeds, {PER_TIER} charts/tier)\n")
print("tier      " + "".join(f"{c:>7}" for c in CANDIDATES) + "   -> best")
best_by_tier = {}
for tier in ("basic", "advanced", "extreme", "master"):
    fs = files_by_tier.get(tier, [])
    random.seed(42); random.shuffle(fs); fs = fs[:PER_TIER]
    sums = {c: 0.0 for c in CANDIDATES}; nrun = 0
    for seed in SEEDS:
        random.seed(seed)
        for path in fs:
            txt = read(path)
            if not txt: continue
            ev, bl = parse_events(txt)
            if not ev or len(ev) < 8: continue
            if sum(len(b.get("11", {})) + len(b.get("19", {})) for b in ev) < 16: continue
            noisy = add_noise(ev)
            nrun += 1
            for c in CANDIDATES:
                PM.KEEP_PCT = c
                cleaned, _ = PM.snap_sections(copy.deepcopy(noisy), bl, 150.0, "__cal__")
                sums[c] += score(cleaned, ev)
    if not nrun: continue
    means = {c: sums[c] / nrun for c in CANDIDATES}
    best = max(means, key=means.get)
    best_by_tier[tier] = best
    row = "".join(f"{means[c]*100:7.1f}" for c in CANDIDATES)
    print(f"{tier:9s}{row}   -> {best}  (F1 {means[best]*100:.1f}%, runs={nrun})")

print("\nDATA-CHOSEN KEEP_PCT_BY_TIER =", {t: best_by_tier.get(t) for t in ("basic","advanced","extreme","master")})
print("(prior hand-picked = {'basic':50,'advanced':45,'extreme':38,'master':32})")
