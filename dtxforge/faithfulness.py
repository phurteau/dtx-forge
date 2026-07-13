"""Faithfulness metric: compare the final chart against the originally-transcribed
tab to report how faithful the output is (100% = the tab is untouched).

A note is identified by (measure, position, lane). Relative to the original tab:
  * kept    - same note still on the same lane at the same spot
  * moved   - same spot, but the lane changed (e.g. a kick reassigned to the
              left foot for a double-kick: RLR/LRL)
  * dropped - the note is gone (e.g. removed by the playability relaxer)
  * added   - a brand-new note not in the tab (e.g. hi-hat foot / left-pedal)

percent = kept / original_notes * 100  (additions don't reduce it - they're extra,
not a change TO what the tab specified; they're reported separately).
"""


def _keyset(events):
    s = set()
    for mi, chan in enumerate(events):
        for ch, slots in chan.items():
            for pos in slots:
                s.add((mi, float(pos), ch))
    return s


def compare(original_events, final_events):
    orig = _keyset(original_events)
    fin = _keyset(final_events)
    kept = orig & fin
    gone = orig - fin                    # original notes no longer at same lane+spot
    added_raw = fin - orig               # notes present now but not in the tab

    fin_positions = {(m, p) for (m, p, c) in fin}
    moved = {(m, p, c) for (m, p, c) in gone if (m, p) in fin_positions}
    dropped = gone - moved
    # a move's destination shows up in added_raw; don't double-count it as "added"
    moved_pos = {(m, p) for (m, p, c) in moved}
    added = {(m, p, c) for (m, p, c) in added_raw if (m, p) not in moved_pos}

    n_orig = len(orig)
    pct = 100.0 if n_orig == 0 else round(100.0 * len(kept) / n_orig, 1)
    return {
        "percent": pct,
        "original_notes": n_orig,
        "kept": len(kept),
        "moved": len(moved),
        "dropped": len(dropped),
        "added": len(added),
    }


def summary_line(f):
    bits = []
    if f["moved"]:
        bits.append(f"{f['moved']} moved to left foot")
    if f["dropped"]:
        bits.append(f"{f['dropped']} dropped")
    if f["added"]:
        bits.append(f"{f['added']} foot notes added")
    detail = ("; ".join(bits)) if bits else "tab untouched"
    return f"Tab faithfulness: {f['percent']:.1f}% ({detail})."
