"""Ground the de-flam / bleed threshold: measure same-lane consecutive-hit spacing in
MILLISECONDS across the corpus (using each chart's header BPM). Answers: how often do real
charts place two hits of the SAME cymbal/hat within N ms? That is the bleed-artifact window
the de-flam should clean without touching real playing.
"""
import os, re, glob, codecs, sys
from fractions import Fraction
from collections import defaultdict, Counter

CORPUS = os.environ.get("DTX_CORPUS", os.path.join(os.path.expanduser("~"), ".scout", "_gitadora_corpus", "gitadora_all", "charts"))
CYM = {"11":"closed-hat","16":"crash","19":"ride","18":"open-hat","1A":"left-crash"}
HANDS = {"12":"snare","14":"hi-tom","15":"low-tom","17":"floor-tom"}
KICK = {"13":"kick"}
LANES = {**CYM, **HANDS, **KICK}
BUCKETS = [10, 20, 30, 40, 50, 60, 70, 80, 100, 150]


def read(path):
    for enc in ("shift_jis","cp932","utf-8"):
        try: return codecs.open(path, encoding=enc).read()
        except Exception: pass
    return None


def parse(txt):
    bars = defaultdict(lambda: defaultdict(dict))
    meters = {}
    bpm = None
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
        if ch not in LANES: continue
        cells = [data[i:i+2] for i in range(0, len(data)-1, 2)]
        n = len(cells)
        for idx, c in enumerate(cells):
            if c != "00": bars[bi][ch][Fraction(idx, n)] = c
    return bars, meters, bpm


# per lane: histogram of same-lane gaps by ms bucket, plus total pairs
gap_hist = defaultdict(Counter)
pairs = defaultdict(int)
charts = 0

files = sorted(glob.glob(os.path.join(CORPUS, "*", "*", "*.dtx")))
print(f"scanning {len(files)} charts for same-lane ms spacing...", file=sys.stderr)
for k, path in enumerate(files):
    if k % 800 == 0: print(f"  {k}", file=sys.stderr)
    txt = read(path)
    if not txt: continue
    bars, meters, bpm = parse(txt)
    if not bpm or bpm <= 0 or not bars: continue
    charts += 1
    whole_ms = 4 * 60000.0 / bpm                      # ms per whole note (4 beats)
    for bi in sorted(bars):
        bl = float(meters.get(bi, Fraction(1)))
        for ch, sm in bars[bi].items():
            ps = sorted(sm)
            for a, b in zip(ps, ps[1:]):
                gap_ms = float(b - a) * bl * whole_ms
                pairs[ch] += 1
                for thr in BUCKETS:
                    if gap_ms < thr:
                        gap_hist[ch][thr] += 1
                        break

def pct(n, d): return 100.0 * n / d if d else 0.0

print(f"\n{'='*72}\nSAME-LANE SPACING IN MS  ({charts} charts w/ BPM)\n{'='*72}")
print("cumulative % of same-lane consecutive hits closer than each threshold:\n")
hdr = "lane".ljust(12) + "".join(f"<{t}".rjust(7) for t in BUCKETS)
print(hdr)
for ch in ["11","16","19","18","1A","12","14","15","17","13"]:
    if ch not in pairs: continue
    tot = pairs[ch]
    cum = 0; cells = []
    for t in BUCKETS:
        cum += gap_hist[ch].get(t, 0)
        cells.append(f"{pct(cum,tot):6.2f}")
    print(f"{LANES[ch]:12s}" + "".join(c.rjust(7) for c in cells) + f"   (n={tot})")

print("\nReading: for CYMBALS/HATS a same-lane hit under ~60-70ms is a decay/bleed FLAM")
print("(should be de-flammed); for SNARE/TOMS/KICK sub-70ms is genuine fast playing (rolls,")
print("double-bass) and must be KEPT. Compare the cymbal rows vs the snare/kick rows below it.")
