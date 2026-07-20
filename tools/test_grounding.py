"""GROUNDING TEST: assert the shipped thresholds are the ones the DATA supports, so they can't
silently drift away from the corpus. Two checks:

  1. KEEP_PCT_BY_TIER is on the F1-optimal plateau -- re-run a fast mini-calibration (recover real
     charts from synthetic transcription noise) and assert each shipped per-tier value scores within
     TOL of that tier's best candidate.
  2. The per-lane note grids match corpus subdivision usage (from the shipped docs/drum_facts_all.json):
     cymbal/hat/ride grids must NOT admit 1/32 (corpus ~0%), tom grid MUST admit 1/32 (corpus >0.5%).

Requires the local corpus mirror for check 1; check 2 uses only the repo's shipped facts JSON.
"""
import os, re, glob, codecs, sys, random, json, copy
from fractions import Fraction
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.environ.get("DTX_CORPUS", os.path.join(os.path.expanduser("~"), ".scout", "_gitadora_corpus", "gitadora_all", "charts"))
sys.path.insert(0, REPO)
from dtxscribe import pattern_match as PM
from dtxscribe import dtxmania_style as S

TOL = 1.5               # shipped KEEP_PCT must be within this many F1 points of the tier's best
PER_TIER = 60           # small sample for a fast test
CANDIDATES = [20, 25, 30, 35, 40, 45, 50]
P_BLEED, P_DROP, JITTER = 0.35, 0.12, 0.10
ok = True


def fail(msg):
    global ok; ok = False; print("[FAIL]", msg)


def passed(msg):
    print("[PASS]", msg)


# ---------- check 2: grids vs shipped corpus facts ----------
facts_path = os.path.join(REPO, "docs", "drum_facts_all.json")
if os.path.exists(facts_path):
    facts = json.load(open(facts_path))
    sub = facts["overall"]["subdivision_pct"]

    def frac32(lane):
        # share of hits at 1/32 resolution specifically -- the grid decision is whether to
        # preserve 1/32. (The even-finer 64th+ tail is out of scope for a max-1/32 grid.)
        return sub.get(lane, {}).get("32nd", 0.0)

    cym_32 = max(frac32("closed-hat"), frac32("ride"), frac32("crash"))
    tom_32 = max(frac32("hi-tom"), frac32("low-tom"), frac32("floor-tom"))
    cym_admits32 = any(g >= 24 for g in S._CYM_GRIDS)
    tom_admits32 = any(g >= 24 for g in S._TOM_GRIDS)
    if cym_32 < 0.2 and not cym_admits32:
        passed(f"cymbal grid {S._CYM_GRIDS} excludes 1/32, matching corpus (cymbal 1/32={cym_32:.1f}%)")
    else:
        fail(f"cymbal grid/32nd mismatch: grid={S._CYM_GRIDS} corpus 1/32={cym_32:.1f}%")
    if tom_32 >= 0.2 and tom_admits32:
        passed(f"tom grid {S._TOM_GRIDS} admits 1/32, matching corpus (tom 1/32={tom_32:.1f}%)")
    else:
        fail(f"tom grid/32nd mismatch: grid={S._TOM_GRIDS} corpus 1/32={tom_32:.1f}%")
else:
    fail(f"missing shipped facts {facts_path}")


# ---------- check 1: KEEP_PCT on the data-optimal plateau ----------
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
    return ([{ch: dict(sm) for ch, sm in bars.get(i, {}).items()} for i in range(hi+1)],
            [meters.get(i, Fraction(1)) for i in range(hi+1)])


def h16(bar, ch):
    sm = bar.get(ch)
    if not sm: return set()
    s = set()
    for p in sm:
        if p.denominator == 0 or 16 % p.denominator != 0: return None
        s.add(int(round(float(p)*16)) % 16)
    return s


def add_noise(events):
    out = []
    for bar in events:
        nb = {ch: dict(sm) for ch, sm in bar.items()}
        for ch in ("11","19"):
            sm = nb.get(ch)
            if not sm: continue
            new = {}
            for p, v in sm.items():
                if random.random() < P_DROP: continue
                if random.random() < JITTER and p.denominator and 16 % p.denominator == 0:
                    s = (int(round(float(p)*16)) + random.choice((-1,1))) % 16
                    new[Fraction(s,16)] = v
                else:
                    new[p] = v
            if random.random() < P_BLEED:
                new[Fraction(random.randrange(16),16)] = PM._CANON.get(ch,"01")
            if new: nb[ch] = new
            else: nb.pop(ch, None)
        out.append(nb)
    return out


def f1(cleaned, truth):
    tp=fp=fn=0
    for cb, tb in zip(cleaned, truth):
        for ch in ("11","19"):
            g = h16(tb, ch)
            if g is None: continue
            c = h16(cb, ch) or set()
            tp += len(c & g); fp += len(c - g); fn += len(g - c)
    pr = tp/(tp+fp) if tp+fp else 1.0
    rc = tp/(tp+fn) if tp+fn else 1.0
    return 200*pr*rc/(pr+rc) if pr+rc else 0.0


if os.path.isdir(CORPUS):
    by_tier = defaultdict(list)
    for f in glob.glob(os.path.join(CORPUS,"*","*","*.dtx")):
        by_tier[tier_of(os.path.basename(f))].append(f)
    for tier in ("basic","advanced","extreme","master"):
        fs = by_tier.get(tier, [])
        random.seed(42); random.shuffle(fs); fs = fs[:PER_TIER]
        sums = {c:0.0 for c in CANDIDATES}; nn=0
        random.seed(99)
        for path in fs:
            txt = read(path)
            if not txt: continue
            ev, bl = parse_events(txt)
            if not ev or len(ev) < 8: continue
            if sum(len(b.get("11",{}))+len(b.get("19",{})) for b in ev) < 16: continue
            noisy = add_noise(ev); nn += 1
            for c in CANDIDATES:
                PM.KEEP_PCT = c
                cl,_ = PM.snap_sections(copy.deepcopy(noisy), bl, 150.0, "__cal__")
                sums[c] += f1(cl, ev)
        if not nn: continue
        means = {c: sums[c]/nn for c in CANDIDATES}
        best_c = max(means, key=means.get); best = means[best_c]
        shipped = PM.KEEP_PCT_BY_TIER[tier]
        # score the shipped value (may not be a candidate) by re-running it
        PM.KEEP_PCT = shipped
        s2=0.0
        random.seed(99)
        for path in fs:
            txt=read(path)
            if not txt: continue
            ev,bl=parse_events(txt)
            if not ev or len(ev)<8: continue
            if sum(len(b.get("11",{}))+len(b.get("19",{})) for b in ev) < 16: continue
            noisy=add_noise(ev)
            cl,_=PM.snap_sections(copy.deepcopy(noisy),bl,150.0,"__cal__")
            s2+=f1(cl,ev)
        shipped_f1 = s2/nn
        if shipped_f1 >= best - TOL:
            passed(f"{tier}: KEEP_PCT={shipped} on plateau (F1 {shipped_f1:.1f} vs best {best:.1f}@{best_c}, n={nn})")
        else:
            fail(f"{tier}: KEEP_PCT={shipped} OFF plateau (F1 {shipped_f1:.1f} vs best {best:.1f}@{best_c})")
else:
    print(f"[SKIP] corpus not found at {CORPUS} -- KEEP_PCT plateau check skipped (grid check still ran)")

print("\nRESULT:", "GROUNDING OK" if ok else "GROUNDING DRIFT")
sys.exit(0 if ok else 1)
