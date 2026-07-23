"""GROUNDED e-drum accuracy test (no hardware).

Proves the Record-mode capture->quantize->emit pipeline recovers a HUMAN performance
faithfully, by turning a real corpus chart into a simulated drummer's MIDI stream and
scoring what we recover against the original chart:

  real chart (.dtx)  ->  timestamped GM note-on stream  ->  + human imperfection
  (timing jitter, constant input latency, occasional missed / extra hits)  ->
  record.quantize_live  ->  emitted .dtx  ->  score vs the original (score_dtx)

Two passes per song:
  * PERFECT  (no jitter/latency/errors) -> recovery must be ~1.0 (pipeline is lossless on
             clean input; anything less is a real bug in quantize/emit).
  * HUMAN    (realistic jitter + latency + a few missed/extra hits) -> the honest number.

Run:  python tools/edrum_grounded_test.py
"""
import os, sys, glob, random, tempfile
from fractions import Fraction

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(os.path.expanduser("~"), ".scout", "_dtx_eval")
CORPUS = os.path.join(os.path.expanduser("~"), ".scout", "_gitadora_corpus", "gitadora_all", "charts")
sys.path.insert(0, REPO)
sys.path.insert(0, EVAL)
from dtxscribe import record, dtx            # noqa: E402
import score_dtx                             # noqa: E402

# score_dtx lane label -> a representative GM note to synthesize (group-robust)
LANE2GM = {
    "bd": 36, "lbd": 36, "sd": 38,
    "hh": 42, "ho": 46, "lp": 44,
    "ht": 48, "lt": 45, "ft": 41,
    "cy": 49, "lc": 57, "rd": 51,
}

SONGS = {
    "infinite":    r"07_drummania_7thMIX\Infinite\ext.dtx",
    "onion_ninja": r"29_GITADORA_FUZZUP\Onion_Ninja\ext.dtx",
    "rabbit_hole": r"31_GITADORA_GALAXY_WAVE_DELTA\Rabbit_Hole\ext.dtx",
    "telecaster":  r"29_GITADORA_FUZZUP\Telecaster_B_Boy\ext.dtx",
    "truare":      r"27_GITADORA_NEXAGE\Truare\ext.dtx",
    "meikyou":     r"10_drummania_10thMIX\Meikyou Shisui\ext.dtx",
}


def synth_performance(parsed, *, jitter_ms=0.0, latency_ms=0.0, miss_rate=0.0,
                      extra_rate=0.0, seed=0):
    """Turn a parsed GT chart (lane -> [abs_times]) into a played (time_s, gm_note) stream
    with human imperfection. jitter = gaussian timing error; latency = constant offset a
    real module+player adds; miss = notes dropped; extra = stray ghost hits inserted."""
    rng = random.Random(seed)
    hits = []
    for lane, times in parsed["lanes"].items():
        gm = LANE2GM.get(lane)
        if gm is None:
            continue
        for t in times:
            if miss_rate and rng.random() < miss_rate:
                continue
            jt = rng.gauss(0, jitter_ms / 1000.0) if jitter_ms else 0.0
            hits.append((t + jt + latency_ms / 1000.0, gm))
            if extra_rate and rng.random() < extra_rate:
                # a stray double/ghost a 16th-ish away on the same drum
                hits.append((t + jt + latency_ms / 1000.0 + rng.uniform(0.04, 0.12), gm))
    hits.sort()
    return hits


def recover(hits, bpm, calibration_ms=0.0):
    events, barlens, _ = record.quantize_live(
        hits, bpm, calibration_ms=calibration_ms, start_time=0.0, count_in_bars=0)
    meta = dict(title="rec", artist="x", bpm=round(bpm, 3), dlevel=500, comment="", bgm="b.ogg")
    return dtx.emit_dtx(events, barlens, meta)


def score_pass(name, gt_path, synth_kwargs, calibration_ms=0.0):
    parsed = score_dtx.parse_dtx(gt_path)
    bpm = parsed["bpm"] or 120.0
    hits = synth_performance(parsed, **synth_kwargs)
    txt = recover(hits, bpm, calibration_ms=calibration_ms)
    tf = os.path.join(tempfile.gettempdir(), f"edrum_{name}.dtx")
    open(tf, "w", encoding="utf-8").write(txt)
    res = score_dtx.score(gt_path, tf, tol=0.05)
    g = res["per_group"]
    return res["timing_overall"]["f1"], {k: g[k]["f1"] for k in ("kick", "snare", "hihat", "tom", "cymbal")}, \
        parsed["n_notes"], res["blind"]["n_notes"]


def gt(song):
    p = os.path.join(CORPUS, SONGS[song])
    hits = glob.glob(p)
    return hits[0] if hits else None


def run():
    songs = [s for s in SONGS if gt(s)]
    print(f"songs available: {len(songs)}/{len(SONGS)}\n")

    # human-performance profile: 20ms jitter (a solid amateur), 12ms latency, 3% missed, 2% extra
    HUMAN = dict(jitter_ms=20.0, latency_ms=12.0, miss_rate=0.03, extra_rate=0.02, seed=7)
    PERFECT = dict(jitter_ms=0.0, latency_ms=0.0, miss_rate=0.0, extra_rate=0.0, seed=0)

    for label, kw, cal in [("PERFECT (clean input -> must be ~1.0)", PERFECT, 0.0),
                           ("HUMAN (20ms jitter, 12ms latency, 3% miss, 2% extra; calibrated)", HUMAN, 12.0)]:
        print(f"===== {label} =====")
        print(f"  {'song':13} {'tim':>5} {'kick':>5} {'snr':>5} {'hh':>5} {'tom':>5} {'cym':>5}")
        agg = {k: [] for k in ("timing", "kick", "snare", "hihat", "tom", "cymbal")}
        for s in songs:
            tim, gf, gtn, bln = score_pass(s + label[:4], gt(s), kw, calibration_ms=cal)
            agg["timing"].append(tim)
            for k in ("kick", "snare", "hihat", "tom", "cymbal"):
                agg[k].append(gf[k])
            print(f"  {s:13} {tim:5.2f} {gf['kick']:5.2f} {gf['snare']:5.2f} {gf['hihat']:5.2f} {gf['tom']:5.2f} {gf['cymbal']:5.2f}")
        n = len(songs)
        m = {k: sum(v) / n for k, v in agg.items()}
        print(f"  {'MEAN':13} {m['timing']:5.2f} {m['kick']:5.2f} {m['snare']:5.2f} {m['hihat']:5.2f} {m['tom']:5.2f} {m['cymbal']:5.2f}\n")


if __name__ == "__main__":
    run()
