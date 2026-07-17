"""Learn from ALL charts: both corpus sets (gitadora_all + realdtx, ~6,740 files), deduplicated
by drum-content hash, broken down PER DIFFICULTY TIER. Produces the full profile the app can use
for tier-aware calibration. Outputs a report + drum_facts_all.json.

Per tier and overall: chart count, per-lane subdivision %, per-lane off-beat %, triplet-bar %,
odd-meter %, hi-hat bar-to-bar repeat %, density (notes/bar, notes/chart), lane-usage %, and
same-lane <70ms spacing (bleed) per lane.
"""
import os, re, glob, codecs, json, sys, hashlib
from fractions import Fraction
from collections import Counter, defaultdict

ROOTS = [os.environ.get("DTX_CORPUS", os.path.join(os.path.expanduser("~"), ".scout", "_gitadora_corpus", "gitadora_all", "charts")),
         os.environ.get("DTX_CORPUS_REAL", os.path.join(os.path.expanduser("~"), ".scout", "_gitadora_corpus", "realdtx"))]
DRUM = {"11","12","13","14","15","16","17","18","19","1A","1B","1C"}
LN = {"11":"closed-hat","12":"snare","13":"kick","14":"hi-tom","15":"low-tom","16":"crash",
      "17":"floor-tom","18":"open-hat","19":"ride","1A":"left-crash","1B":"left-pedal","1C":"left-bass"}
ORDER = ["quarter+","8th","16th","triplet","32nd","64th+","other"]
QUARTERS = {Fraction(0,1), Fraction(1,4), Fraction(1,2), Fraction(3,4)}
TIERS = ["basic","advanced","extreme","master","other"]


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
    bars = defaultdict(lambda: defaultdict(dict)); meters = {}; bpm = None
    m = re.search(r'#BPM[:\s]+([0-9.]+)', txt)
    if m:
        try: bpm = float(m.group(1))
        except Exception: pass
    for line in txt.splitlines():
        mm = re.match(r'#(\d\d\d)([0-9A-Fa-f]{2}):\s*([0-9A-Za-z.]+)', line.strip())
        if not mm: continue
        bi = int(mm.group(1)); ch = mm.group(2).upper(); data = mm.group(3)
        if ch == "02":
            try: meters[bi] = Fraction(str(float(data))).limit_denominator(64)
            except Exception: pass
            continue
        if ch not in DRUM: continue
        cells = [data[i:i+2] for i in range(0, len(data)-1, 2)]; n = len(cells)
        for idx, c in enumerate(cells):
            if c != "00": bars[bi][ch][Fraction(idx, n)] = c
    return bars, meters, bpm


def content_key(bars):
    """Stable hash of the drum content, for dedup across the two corpus sets."""
    h = hashlib.md5()
    for bi in sorted(bars):
        for ch in sorted(bars[bi]):
            h.update(f"{bi}:{ch}:".encode())
            h.update(",".join(f"{p.numerator}/{p.denominator}" for p in sorted(bars[bi][ch])).encode())
    return h.hexdigest()


def blank():
    return {"charts":0, "bars":0, "sub":defaultdict(Counter), "off":defaultdict(lambda:[0,0]),
            "trip":[0,0], "odd":[0,0], "hrep":[0,0], "notes":0,
            "lane_bars":Counter(), "flam":defaultdict(lambda:[0,0])}   # flam:[under70,total_pairs]

per = {t: blank() for t in TIERS}
overall = blank()
seen = set()
files = []
for r in ROOTS:
    files += glob.glob(os.path.join(r, "**", "*.dtx"), recursive=True)
print(f"found {len(files)} chart files across {len(ROOTS)} sets", file=sys.stderr)

dups = 0
for k, path in enumerate(files):
    if k % 1000 == 0: print(f"  {k}/{len(files)}  (dups so far {dups})", file=sys.stderr)
    txt = read(path)
    if not txt: continue
    bars, meters, bpm = parse(txt)
    if not bars: continue
    key = content_key(bars)
    if key in seen:
        dups += 1; continue
    seen.add(key)
    t = tier_of(os.path.basename(path))
    for acc in (per[t], overall):
        acc["charts"] += 1
    whole_ms = (4*60000.0/bpm) if bpm and bpm > 0 else None
    hat_sigs = []
    for bi in sorted(bars):
        chans = bars[bi]; bl = meters.get(bi, Fraction(1))
        for acc in (per[t], overall):
            acc["bars"] += 1
            acc["odd"][1] += 1
            if bl != Fraction(1): acc["odd"][0] += 1
        bar_trip = False
        for ch, sm in chans.items():
            for acc in (per[t], overall):
                acc["lane_bars"][ch] += 0  # ensure key
            for p in sm:
                b = sub_bucket(p)
                for acc in (per[t], overall):
                    acc["sub"][ch][b] += 1
                    acc["off"][ch][1] += 1
                    if p not in QUARTERS: acc["off"][ch][0] += 1
                    acc["notes"] += 1
                if p.denominator % 3 == 0: bar_trip = True
            for acc in (per[t], overall): acc["lane_bars"][ch] += 1
            # flam ms
            if whole_ms:
                ps = sorted(sm); blf = float(bl)
                for a, c in zip(ps, ps[1:]):
                    gap = float(c - a) * blf * whole_ms
                    for acc in (per[t], overall):
                        acc["flam"][ch][1] += 1
                        if gap < 70.0: acc["flam"][ch][0] += 1
        for acc in (per[t], overall):
            acc["trip"][1] += 1
            if bar_trip: acc["trip"][0] += 1
        hat_sigs.append(tuple(sorted(str(p) for p in chans.get("11", {}))))
    for a, b in zip(hat_sigs, hat_sigs[1:]):
        for acc in (per[t], overall):
            if a and a == b: acc["hrep"][0] += 1
            acc["hrep"][1] += 1

def pct(n, d): return round(100.0*n/d, 1) if d else 0.0

def report(name, a):
    if not a["charts"]: return
    print(f"\n{'-'*66}\n{name.upper()}  ({a['charts']} unique charts, {a['bars']} bars, "
          f"{round(a['notes']/max(1,a['bars']),1)} notes/bar)\n{'-'*66}")
    print("  subdivision % (kick / snare / hat / ride / crash / hi-tom):")
    for ch in ["13","12","11","19","16","14"]:
        c = a["sub"].get(ch)
        if not c: continue
        tot = sum(c.values())
        row = " ".join(f"{b}:{pct(c[b],tot)}" for b in ORDER if c[b])
        print(f"    {LN[ch]:11s} {row}")
    ob = " ".join(f"{LN[ch]}:{pct(a['off'][ch][0],a['off'][ch][1])}" for ch in ["11","19","13","12"] if a['off'][ch][1])
    print(f"  off-beat %: {ob}")
    print(f"  triplet bars: {pct(a['trip'][0],a['trip'][1])}%   odd-meter: {pct(a['odd'][0],a['odd'][1])}%   "
          f"hat repeat: {pct(a['hrep'][0],a['hrep'][1])}%")
    fl = " ".join(f"{LN[ch]}:{pct(a['flam'][ch][0],a['flam'][ch][1])}" for ch in ["11","16","12","14"] if a['flam'][ch][1])
    print(f"  same-lane <70ms %: {fl}")

print(f"\n{'='*66}\nLEARNED ALL CHARTS  (unique {len(seen)}, deduped {dups})\n{'='*66}")
report("OVERALL", overall)
for t in ["basic","advanced","extreme","master"]:
    report(t, per[t])

# machine-readable, per tier + overall
def dump(a):
    return {
        "charts": a["charts"], "bars": a["bars"],
        "notes_per_bar": round(a["notes"]/max(1,a["bars"]),2),
        "subdivision_pct": {LN[ch]: {b: pct(c[b], sum(c.values())) for b in ORDER if c[b]} for ch,c in a["sub"].items()},
        "offbeat_pct": {LN[ch]: pct(o[0],o[1]) for ch,o in a["off"].items() if o[1]},
        "triplet_bar_pct": pct(a["trip"][0],a["trip"][1]),
        "odd_meter_pct": pct(a["odd"][0],a["odd"][1]),
        "hat_repeat_pct": pct(a["hrep"][0],a["hrep"][1]),
        "flam_under70ms_pct": {LN[ch]: pct(f[0],f[1]) for ch,f in a["flam"].items() if f[1]},
    }
out = {"unique_charts": len(seen), "deduped": dups, "overall": dump(overall),
       "by_tier": {t: dump(per[t]) for t in TIERS if per[t]["charts"]}}
dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drum_facts_all.json")
json.dump(out, open(dest,"w"), indent=2)
print(f"\nsaved -> {dest}")
