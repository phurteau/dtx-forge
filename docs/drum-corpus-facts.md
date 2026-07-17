# Drum-corpus facts

Actionable drumming statistics mined from the **full corpus of 6,621 unique real GITADORA/
DrumMania charts** (both local sets, deduplicated by drum-content hash), used to ground the
DTXMania neatening logic in real data rather than assumption. Regenerate with `mine_all_charts.py`
(per-tier report + `drum_facts_all.json`), `mine_drum_facts.py`, and `mine_flam_ms.py` (timing).

## Why this exists

The DTXMania "Chart Style" cleans an audio transcription toward how real charts read. Every
threshold that decides *what to keep vs. remove* is calibrated from the numbers below, so the
cleanup never assumes plain 4/4 pop and never treats legitimate drumming as noise.

## Complexity scales HARD with difficulty (per-tier, 6,621 charts)

| Tier | charts | notes/bar | off-beat hats | triplet bars | hat 16th | tom <70ms | hat repeat |
|------|-------:|----------:|--------------:|-------------:|---------:|----------:|-----------:|
| Basic    | 1673 |  3.9 | 17.8% |  5.6% |  1.2% |  0.3% | 7.7% |
| Advanced | 1659 |  7.3 | 29.0% |  9.4% |  1.9% |  1.3% | 10.3% |
| Extreme  | 1660 | 11.1 | 47.4% | 14.4% |  6.1% |  5.4% | 10.0% |
| Master   | 1173 | 13.5 | 54.6% | 17.8% | 10.5% | 12.2% | 7.8% |

**A Master chart is 3.5× denser than Basic, is off-beat over half the time, and plays triplets in
~1 in 5 bars** - so it is almost entirely intentional playing and must be cleaned GENTLY, while a
Basic chart is simple and tolerates firmer cleanup. This drives the **tier-aware** cleanup strength
`KEEP_PCT_BY_TIER` (higher tier → lower threshold → keep more).

## Empirically calibrated thresholds (the corpus chooses, not us)

`KEEP_PCT_BY_TIER` is not hand-picked - it is chosen by a closed-loop calibration against the real
charts (`calibrate_keep_pct.py`):

1. take real charts (clean, correct **ground truth**) and read their hi-hat/ride timekeeping;
2. inject synthetic transcription noise - bleed ghosts (false positives) + dropped/jittered hits
   (false negatives) - the two dominant audio-transcription error modes;
3. run the cleaner at each candidate threshold;
4. score how well the output **recovers the original real chart** (F1 over 1/16 timekeeping slots);
5. the F1-maximising threshold per tier is the data-chosen value.

Averaged over 3 noise seeds × 160 charts/tier (≈1,830 runs), the recovery F1 peaks at:

| Tier | data-optimal KEEP_PCT | peak recovery F1 |
|------|----------------------:|-----------------:|
| Basic    | 35 | ~77% |
| Advanced | 30 | ~79% |
| Extreme  | 30 | ~80% |
| Master   | 30 | ~79% |

so **`KEEP_PCT_BY_TIER = {basic:35, advanced:30, extreme:30, master:30}`**. The F1 curve is a broad
plateau from ~25–40 that falls off sharply above ~45 - the earlier hand-picked 50/45/38/32 sat past
the plateau and over-cleaned (which is the over-deletion that motivated this calibration).
`test_grounding.py` re-runs a mini calibration and FAILS if the shipped values ever drift off the
plateau, and asserts the per-lane grids still match the corpus subdivision usage - so the code can
never quietly diverge from the data.

## A. Subdivision usage per lane (% of that lane's hits, overall)

| Lane | quarter+ | 8th | 16th | triplet | 32nd | 64th+ |
|------|---------:|----:|-----:|--------:|-----:|------:|
| kick        | 59.3 | 28.1 |  6.7 |  4.0 | 0.1 | 0.3 |
| snare       | 59.0 | 21.2 | 11.5 |  5.3 | 0.3 | 0.6 |
| closed-hat  | 58.4 | 30.1 |  5.8 |  3.7 | 0.0 | 0.4 |
| ride        | 67.7 | 24.0 |  2.3 |  5.2 | 0.0 | 0.1 |
| crash       | 67.4 | 20.7 |  3.3 |  5.2 | 0.0 | 0.6 |
| hi-tom      | 35.3 | 26.9 | 19.2 | 12.3 | 0.9 | 2.2 |
| left-bass (double-kick) | 4.7 | 11.5 | **66.4** | 11.5 | 2.0 | 0.8 |

**Implications**
- **Cymbals/hats/ride cap at 1/16** (32nd ≈ 0.0%). `_regularize_cymbals` grid `[4, 8, 12, 16]`.
- **Toms reach 1/32 and triplets.** `_regularize_toms` grid `[4, 8, 12, 16, 24, 32]`.
- **Double-bass is two-thirds 16ths** - never thin it.

## B. Off-beat frequency (% of hits NOT on a quarter beat), overall

closed-hat 41.6 · kick 40.7 · snare 41.0 · ride 32.3 - **off-beats are ~40% of hits** (and up to
55% at Master). Timekeeping consensus uses ONE symmetric threshold for on-beat and off-beat slots
alike; off-beat drumming is never treated as suspect.

## C. Feel / meter prevalence (overall)

- **Triplet/swing bars: 11.3%** (5.6% Basic → 17.8% Master). Swing guard (`_tripletish`) skips them.
- **Odd-meter bars: 1.3%** - non-4/4. Neatening only runs on 4/4 bars, so odd meters pass through.

## D. Consistency target

- **Hi-hat bar-to-bar repeat: 9.3% overall** (7.7–10.3% by tier). Real charts vary a lot; they are
  NOT highly repetitive. Cleanup aims to land near this, neat but not flattened.

## E. De-flam / bleed threshold - same-lane consecutive spacing under 70 ms

closed-hat 0.4% · crash 0.4% (bleed) vs snare 1.9% · hi-tom 6.5% (real fast fills). **`FLAM_MS = 70`
sits in the valley**; de-flam runs on cymbal lanes only. (Note: at Master, tom <70ms hits 12.2% -
even more reason never to de-flam toms.)

## F. Idiomatic simultaneous-lane stacks (top co-occurrences)

closed-hat+kick · closed-hat+snare · crash+kick · crash+snare · kick+left-crash · kick+snare.
Crashes land WITH kick/snare (accents), so crashes are preserved and never collapsed to one-per-bar.

