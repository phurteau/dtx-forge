# tools - corpus grounding & calibration

These scripts derive and verify the numbers the DTXMania cleanup runs on, straight from the real
GITADORA/DrumMania chart corpus. They are how the thresholds in `dtxscribe/` are *chosen* and kept
honest - not hand-picked.

Point them at a local corpus mirror via env vars (defaults shown):

```
DTX_CORPUS      = ~/.scout/_gitadora_corpus/gitadora_all/charts
DTX_CORPUS_REAL = ~/.scout/_gitadora_corpus/realdtx
```

| Script | What it does | Produces |
|--------|--------------|----------|
| `mine_all_charts.py` | Full per-tier profile of both corpus sets (deduplicated): subdivisions, off-beat frequency, triplet/odd-meter prevalence, hat-repeat, de-flam ms, density | `drum_facts_all.json` + report |
| `mine_drum_facts.py` | Single-set per-lane facts | `drum_facts.json` + report |
| `mine_flam_ms.py` | Same-lane spacing in milliseconds (grounds `FLAM_MS`) | report |
| `calibrate_keep_pct.py` | **Empirically chooses `KEEP_PCT_BY_TIER`** by recovering real charts from synthetic transcription noise (F1-optimal per tier) | report |
| `test_grounding.py` | Regression: fails if the shipped thresholds drift off the data-optimal plateau, or if the per-lane grids stop matching corpus subdivision usage | pass/fail |

The measured facts and methodology are written up in [`docs/drum-corpus-facts.md`](../docs/drum-corpus-facts.md)
(machine-readable in `docs/drum_facts*.json`).

**The corpus itself is not committed** (it's large and third-party). These scripts only read it; the
distilled facts and the derived constants are what ship.
