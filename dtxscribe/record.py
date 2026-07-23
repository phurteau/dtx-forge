"""Live e-drum capture backend for DTXScribe's Record mode.

A drummer's performance arrives as a stream of timestamped ``(time_s, gm_midi)`` note-ons
(from the Web MIDI API in the shipped app, or a simulated source in dev/tests). This module
turns that raw stream into a clean, playable chart, reusing the same adaptive quantizer as
audio transcription -- so Record and Generate produce charts of the same shape.

Pure and hardware-free: every function takes a plain hit list, so the whole pipeline is
unit-testable by synthesizing a performance (see tools/edrum_grounded_test.py). The only
thing that genuinely needs real hardware is measuring a module's input/output latency, which
is why calibration is a single signed offset applied here rather than something we can infer.

Key difference from audio transcription: the grid is anchored to the KNOWN musical downbeat
(the count-in establishes bar 1), not to the first detected hit -- so a late or syncopated
first note doesn't drag the whole chart off the beat.
"""
from fractions import Fraction
from collections import Counter

from . import dtx, standardize


# ---------------------------------------------------------------- brand note-map profiles
# A profile REMAPS a module's raw note numbers onto the canonical General MIDI notes that
# dtx.MAP already understands, so there is ONE source of truth for note->lane (dtx.MAP) and
# each brand only needs a thin override for the pads it sends on non-GM numbers.
#
# Most mainstream modules send the CORE kit (kick/snare/toms/hi-hat/crash/ride) on standard
# GM channel-10 notes, so the GM baseline (empty remap) already covers them. Per-brand
# entries below hold only VERIFIED non-standard extras; anything unknown is captured by the
# learn-my-kit wizard. (Numbers must come from the maker's data sheet or a learn capture --
# never guessed.)
GM_BASELINE = {}   # identity: notes already in dtx.MAP pass straight through

BRAND_PROFILES = {
    # displayName: {raw_note: canonical_gm_note}
    "General MIDI (default)": dict(GM_BASELINE),
    # Placeholders kept intentionally minimal until verified against each data sheet /
    # a real learn capture. The mechanism is exercised by tests via custom profiles.
    "Yamaha DTX": dict(GM_BASELINE),
    "Roland TD": dict(GM_BASELINE),
    "Alesis": dict(GM_BASELINE),
    "2Box": dict(GM_BASELINE),
    "ATV": dict(GM_BASELINE),
}


def apply_profile(hits, note_remap=None):
    """Remap raw module notes onto canonical GM notes. Notes absent from the remap pass
    through unchanged (the GM core), so dtx.MAP then resolves every known note to its lane."""
    if not note_remap:
        return list(hits)
    return [(t, note_remap.get(n, n), *rest) for (t, n, *rest) in hits]


def apply_calibration(hits, calibration_ms=0.0):
    """Shift every hit by a signed latency offset (ms). Positive nudges hits LATER, negative
    earlier -- used to cancel the constant audio-out + MIDI-in lag measured at calibration.
    Preserves any extra per-hit fields (velocity)."""
    if not calibration_ms:
        return list(hits)
    off = calibration_ms / 1000.0
    return [(t + off, n, *rest) for (t, n, *rest) in hits]


def debounce(hits, gap_ms=18.0):
    """Suppress double-triggers: real e-drum pads sometimes fire ONE strike as two very close
    note-ons ("machine-gunning"). Drop a hit on the SAME note within gap_ms of the previous
    one kept. Per-note refractory so a fast alternation between two pads is untouched. Keeps
    the FIRST (the true strike); the ringing retrigger follows. Preserves extra fields."""
    if gap_ms <= 0:
        return list(hits)
    gap = gap_ms / 1000.0
    last = {}
    out = []
    for hit in sorted(hits, key=lambda h: h[0]):
        t, n = hit[0], hit[1]
        if n in last and (t - last[n]) < gap:
            continue
        last[n] = t
        out.append(hit)
    return out


def quantize_live(hits, bpm, *, calibration_ms=0.0, start_time=0.0, count_in_bars=0,
                  profile=None, max_hand_voices=2, pre_roll_tol=0.25, time_sig=(4, 4),
                  debounce_ms=18.0):
    """Turn a live note-on stream into (events, barlens, n_bars).

    hits           : iterable of (time_s, raw_midi_note[, velocity]); wall-clock seconds on
                     the master clock (performance clock for freeplay, song playhead for
                     play-along). Velocity is preserved through profile/calibration/debounce
                     and available on the saved raw take, even though the current chart model
                     does not yet encode it.
    bpm            : chart tempo (known -- the user set it or it came from the track)
    calibration_ms : signed latency offset to cancel input/output lag
    start_time     : master-clock time the take (count-in) began; maps toward musical zero
    count_in_bars  : lead-in bars before bar 1 -- the downbeat is start_time + count_in bars
    profile        : optional {raw_note: gm_note} remap for a specific module
    max_hand_voices: simultaneity cap per grid cell (two hands); feet exempt
    pre_roll_tol   : fraction of a bar a hair-early hit may sit before the downbeat and still
                     be pulled onto bar 1, instead of being dropped as pre-roll
    time_sig       : (num, den) meter chosen by the user -- drives bar length and grid
    debounce_ms    : per-pad double-trigger suppression window (0 disables)

    The grid is anchored to the musical downbeat (start_time + count_in_bars*bar), NOT the
    first hit, so syncopated or late entrances stay on the beat.
    """
    hits = list(hits)
    num, den = int(time_sig[0]), int(time_sig[1])
    bar_whole = Fraction(num, den) if (num > 0 and den > 0) else Fraction(1)
    if not hits or not bpm:
        return [dict()], [bar_whole], 0
    bar_time = float(bar_whole) * 4 * 60.0 / bpm
    if bar_time <= 0:
        return [dict()], [bar_whole], 0

    hits = apply_profile(hits, profile)
    hits = apply_calibration(hits, calibration_ms)
    hits = debounce(hits, debounce_ms)

    anchor = start_time + count_in_bars * bar_time     # musical t=0 (bar 1 downbeat)

    # Keep a hair-early hit: pull anything within pre_roll_tol of a bar just before the
    # downbeat up onto the anchor, so a slightly-rushed first note isn't discarded.
    tol = pre_roll_tol * bar_time
    snapped = []
    for hit in hits:
        t, n = hit[0], hit[1]
        if anchor - tol <= t < anchor:
            t = anchor
        snapped.append((t, n))

    events, barlens, _ = standardize.build_events(
        snapped, bpm, adaptive=True, max_hand_voices=max_hand_voices, anchor=anchor,
        time_sig=(num, den))
    return events, barlens, len(events)


def re_quantize(raw_hits, bpm, **kw):
    """Re-quantize a SAVED raw take at a different bpm / downbeat / meter WITHOUT replaying.
    The play-along safety net: if the detected tempo or downbeat was wrong, fix it in one
    call instead of re-recording. Thin wrapper over quantize_live for intent-clarity."""
    return quantize_live(raw_hits, bpm, **kw)


# ------------------------------------------------------------------- learn-my-kit helpers
def dominant_note(note_ons):
    """Given the notes captured while the user hit ONE pad, return the note that pad sends
    (the mode -- robust to a stray double-trigger or bleed cross-hit). None if empty."""
    notes = [n for n in note_ons if n is not None]
    if not notes:
        return None
    return Counter(notes).most_common(1)[0][0]


def build_profile_from_captures(captures):
    """captures: {lane_key: note_or_None} from the learn wizard -> a {raw_note: gm_note}
    remap plus the set of skipped lanes (which fall back to GM defaults).

    lane_key is a canonical GM note the app prompts for (e.g. 36 kick, 38 snare, 49 crash);
    the captured raw note from THIS module is remapped onto it. A None capture = skipped."""
    remap, skipped = {}, []
    for lane_gm, raw in captures.items():
        if raw is None:
            skipped.append(lane_gm)
            continue
        if raw != lane_gm:
            remap[raw] = lane_gm       # module sent `raw` for what is canonically `lane_gm`
    return remap, skipped


# --------------------------------------------------------------------- streaming recorder
class LiveRecorder:
    """Accumulates timestamped note-ons during a take. The shipped app feeds it from Web
    MIDI; dev/tests feed it from a simulated source. Purely an ordered buffer -- all the
    musical decisions happen in quantize_live on stop()."""

    def __init__(self):
        self._hits = []
        self._t0 = None
        self.recording = False

    def start(self, t0=0.0):
        self._hits = []
        self._t0 = t0
        self.recording = True

    def note_on(self, t, note, velocity=127):
        """Record a struck pad as (time, note, velocity). Ignored unless recording and it's
        an actual strike (velocity > 0). Velocity is kept for the raw take (future accents /
        ghost notes) even though the current chart model doesn't yet encode it. Time is on
        the same clock as start()/the audio playhead."""
        if self.recording and velocity > 0:
            self._hits.append((float(t), int(note), int(velocity)))

    def stop(self):
        self.recording = False
        return list(self._hits)

    @property
    def count(self):
        return len(self._hits)

    @property
    def is_empty(self):
        """True if no strikes were captured -- the app guards Stop against an empty take."""
        return len(self._hits) == 0


# --------------------------------------------------------------- persistent settings store
# A single JSON file under the app's data dir holds named learn-my-kit profiles and per-device
# input-latency calibration, so a returning drummer keeps their mapping and timing without
# re-teaching. The store is intentionally tiny and hand-editable.
#
#   { "profiles":    { "<name>": {"remap": {raw: gm}, "skipped": [gm, ...], "device": "..."} },
#     "calibration": { "<device-name>": <signed ms> },
#     "last_profile": "<name>" }

def _store_dir():
    import os
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    d = os.path.join(base, "DTXScribe")
    os.makedirs(d, exist_ok=True)
    return d


def _store_path():
    import os
    return os.path.join(_store_dir(), "record.json")


def load_store():
    """Read the record settings store, always returning a well-formed dict."""
    import json
    base = {"profiles": {}, "calibration": {}, "last_profile": None}
    try:
        with open(_store_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            base.update({k: data.get(k, base[k]) for k in base})
            if not isinstance(base["profiles"], dict):
                base["profiles"] = {}
            if not isinstance(base["calibration"], dict):
                base["calibration"] = {}
    except Exception:
        pass
    return base


def save_store(store):
    """Write the store atomically (temp + replace) so a crash can't truncate it."""
    import json, os
    p = _store_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)
    os.replace(tmp, p)


def save_profile(name, remap, skipped=None, device=None):
    """Persist a named learn-my-kit profile and mark it the most recently used."""
    store = load_store()
    store["profiles"][name] = {
        "remap": {str(k): int(v) for k, v in (remap or {}).items()},
        "skipped": [int(x) for x in (skipped or [])],
        "device": device or "",
    }
    store["last_profile"] = name
    save_store(store)
    return store["profiles"][name]


def delete_profile(name):
    store = load_store()
    existed = store["profiles"].pop(name, None) is not None
    if store.get("last_profile") == name:
        store["last_profile"] = None
    save_store(store)
    return existed


def profile_remap(name):
    """Return a {raw_note: gm_note} int-keyed remap for a saved profile (empty if unknown)."""
    prof = load_store()["profiles"].get(name) or {}
    return {int(k): int(v) for k, v in (prof.get("remap") or {}).items()}


def set_calibration(device, ms):
    store = load_store()
    store["calibration"][device or "default"] = float(ms)
    save_store(store)
    return store["calibration"]


def get_calibration(device):
    return float(load_store()["calibration"].get(device or "default", 0.0))


# ------------------------------------------------------------------------- tempo detection
def detect_bpm(wav_path):
    """Estimate a song's tempo from a decoded mono WAV, reusing the transcription tempo
    tracker (autocorrelation over kick+snare onset envelopes with octave correction). The
    user confirms or overrides this before recording, so a near miss is harmless."""
    from . import transcribe as T
    x, sr = T._read_mono(wav_path)
    envs, fps = T._band_envs(x, sr, [(30, 120), (200, 1600)])
    bpm = T._estimate_bpm(envs[0] + envs[1], fps)
    return round(float(bpm), 1)
