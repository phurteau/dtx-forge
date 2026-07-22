"""Faithfulness metric: compare the final chart against the notation baseline that
was snapshotted right after transcription - the TAB when one was supplied, or what
the audio detector HEARD in audio-only mode (100% = that baseline is untouched).

Note: in audio-only mode this scores fidelity to the transcription, NOT how
accurately the transcription captured the real song (which is unmeasurable here).

A note is identified by (measure, position, lane). Relative to the baseline:
  * kept    - same note still on the same lane at the same spot
  * moved   - same spot, but the lane changed (e.g. a kick reassigned to the
              left foot for a double-kick: RLR/LRL)
  * dropped - the note is gone (e.g. removed by the playability relaxer)
  * added   - a brand-new note not in the baseline (e.g. hi-hat foot / left-pedal)

percent = kept / original_notes * 100  (additions don't reduce it - they're extra,
not a change TO what the baseline specified; they're reported separately).
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


def summary_line(f, source="tab"):
    """source: 'tab' or 'audio' - names the baseline the score is measured against.
    In audio-only mode we don't present a faithfulness % (there's no reference chart to be
    'faithful' to) - only how many notes the post-transcription passes (de-flam, de-jitter,
    groove snap, foot technique, thinning) changed. Labels are neutral because the diff
    itself doesn't distinguish a cleanup reposition from a foot-technique move."""
    bits = []
    if f["moved"]:
        bits.append(f"{f['moved']} repositioned")
    if f["dropped"]:
        bits.append(f"{f['dropped']} removed")
    if f["added"]:
        bits.append(f"{f['added']} added")
    if source == "audio":
        if bits:
            return "Transcribed from audio (beta), cleanup changes: " + "; ".join(bits) + "."
        return "Transcribed from audio (beta), notes exactly as detected."
    detail = ("; ".join(bits)) if bits else "tab untouched"
    return f"Tab faithfulness: {f['percent']:.1f}% ({detail})."
