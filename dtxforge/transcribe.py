"""Transcription paths -> (events, barlens, bpm). All produce the same event
structure consumed by dtx.emit_dtx, so no manual notation is ever required."""
import os, re, wave, numpy as np
from fractions import Fraction
from . import dtx

# ---------------- Tab: Songsterr ----------------
def from_songsterr(measures):
    events, barlens = dtx.events_from_tab(measures)
    return events, barlens


# ---------------- Tab: MIDI upload ----------------
def from_midi(path, default_bpm=120):
    """Parse a MIDI drum track (channel 9 / GM percussion) -> events, barlens, bpm."""
    import mido
    mid = mido.MidiFile(path)
    tpb = mid.ticks_per_beat
    # gather tempo + time-sig + drum note-ons on absolute ticks
    tempo = mido.bpm2tempo(default_bpm); bpm = default_bpm
    sig = (4, 4)
    notes = []  # (abs_tick, midi_note)
    for track in mid.tracks:
        t = 0
        for msg in track:
            t += msg.time
            if msg.type == "set_tempo":
                tempo = msg.tempo; bpm = mido.tempo2bpm(tempo)
            elif msg.type == "time_signature":
                sig = (msg.numerator, msg.denominator)
            elif msg.type == "note_on" and msg.velocity > 0 and getattr(msg, "channel", 9) == 9:
                notes.append((t, msg.note))
    if not notes:
        raise RuntimeError("No GM drum (channel 10) note-ons found in this MIDI.")
    ticks_per_bar = tpb * 4 * sig[0] / sig[1]
    n_bars = int(max(t for t, _ in notes) // ticks_per_bar) + 1
    events = [dict() for _ in range(n_bars)]
    bar_slots = max(1, round(float(Fraction(sig[0], sig[1])) * dtx.GRID))
    for tick, note in notes:
        if note not in dtx.MAP:
            continue
        mi = int(tick // ticks_per_bar)
        frac_in_bar = (tick - mi * ticks_per_bar) / ticks_per_bar  # 0..1
        slot = int(round(frac_in_bar * bar_slots))
        if slot >= bar_slots:
            slot = bar_slots - 1
        ch, lab = dtx.MAP[note]
        events[mi].setdefault(ch, {}).setdefault(Fraction(slot, bar_slots), dtx.LABEL2SLOT[lab])
    barlens = [Fraction(sig[0], sig[1])] * n_bars
    return events, barlens, round(bpm, 3)


# ---------------- Tab: Guitar Pro (.gp3/.gp4/.gp5/.gpx/.gp) ----------------
def from_guitarpro(path):
    """Parse a Guitar Pro file's drum/percussion track -> events, barlens, bpm.
    Percussion tracks store the GM MIDI drum number as note.value, so the same
    GM->lane MAP used for Songsterr applies directly."""
    import guitarpro
    song = guitarpro.parse(path)
    bpm = float(song.tempo or 120)
    # choose the drum track: explicit percussion flag, else GM drum channel (9), else first
    track = None
    for t in song.tracks:
        if getattr(t, "isPercussionTrack", False):
            track = t; break
    if track is None:
        for t in song.tracks:
            ch = getattr(t, "channel", None)
            if ch is not None and getattr(ch, "channel", None) == 9:
                track = t; break
    if track is None:
        track = song.tracks[0]

    events, barlens = [], []
    for m in track.measures:
        ts = m.header.timeSignature
        sig = (ts.numerator, ts.denominator.value)
        nominal = Fraction(sig[0], sig[1])
        bar_slots = max(1, round(float(nominal) * dtx.GRID))
        chan = {}
        # a measure may have multiple voices; merge them onto the same grid
        for v in m.voices:
            cum = Fraction(0)
            for b in v.beats:
                d = b.duration
                dur = Fraction(1, d.value)
                if getattr(d, "isDotted", False):
                    dur *= Fraction(3, 2)
                tup = getattr(d, "tuplet", None)
                if tup is not None and (tup.enters, tup.times) != (1, 1):
                    dur *= Fraction(tup.times, tup.enters)
                status = str(getattr(b, "status", ""))
                if "empty" not in status and "rest" not in status:
                    slot = int(round(float(cum) * dtx.GRID))
                    if slot >= bar_slots:
                        slot = bar_slots - 1
                    pos = Fraction(slot, bar_slots)
                    for n in b.notes:
                        val = getattr(n, "value", None)
                        if val in dtx.MAP:
                            ch, lab = dtx.MAP[val]
                            chan.setdefault(ch, {}).setdefault(pos, dtx.LABEL2SLOT[lab])
                cum += dur
        events.append(chan)
        barlens.append(nominal)
    if not any(events):
        raise RuntimeError("No drum notes found in this Guitar Pro file "
                           "(is there a percussion track?).")
    return events, barlens, round(bpm, 3)


# ---------------- Tab: generic ASCII drum tab ----------------
# maps common ASCII drum-tab row labels -> GM MIDI drum number
_ASCII_LANES = {
    "cc": 49, "c": 49, "cr": 49, "cra": 49, "crash": 49, "cy": 49,
    "rd": 51, "ri": 51, "ride": 51, "r": 51,
    "hh": 42, "h": 42, "hc": 42, "hi-hat": 42, "hihat": 42, "hats": 42, "hat": 42,
    "ho": 46, "oh": 46, "open": 46,
    "hf": 44, "fh": 44, "hhf": 44, "pedal": 44,
    "sd": 38, "s": 38, "sn": 38, "snare": 38, "sr": 38,
    "t1": 48, "t2": 47, "t3": 45, "ht": 48, "mt": 47, "lt": 45,
    "tom": 47, "tt": 48, "rack": 48,
    "ft": 41, "f": 41, "floor": 41, "flt": 41,
    "bd": 36, "b": 36, "k": 36, "kick": 36, "bass": 36, "kd": 36,
}
# characters that count as a hit
_HIT_CHARS = set("xXoOgGdDbBfF#@*")


def from_ascii_tab(text, bpm=120, beats_per_measure=4):
    """Parse a generic ASCII drum tab (rows like 'HH|x-x-x-x-|') into events.
    Groups consecutive labelled rows into staff blocks; each block is one line of
    music read left→right. Column count per block sets the subdivision."""
    lines = text.replace("\r", "").split("\n")
    blocks = []          # list of list[(label,row)]
    cur = []
    for ln in lines:
        mrow = re.match(r"\s*([A-Za-z][A-Za-z0-9#\-]{0,6})\s*[|:]", ln)
        if mrow and "|" in ln:
            label = mrow.group(1).strip().lower().rstrip("-")
            body = ln[ln.index(mrow.group(1)) + len(mrow.group(1)):]
            # take content between first and last bar marker
            body = body[body.index("|") if "|" in body else 0:]
            cur.append((label, body))
        else:
            if cur:
                blocks.append(cur); cur = []
    if cur:
        blocks.append(cur)
    if not blocks:
        raise RuntimeError("No ASCII drum-tab rows found (expected lines like 'HH|x-x-x-x-|').")

    events, barlens = [], []
    nominal = Fraction(beats_per_measure, 4)
    for block in blocks:
        # normalize: strip bar chars, keep hit columns; align to max width
        rows = []
        for label, body in block:
            cells = [c for c in body if c not in " "]
            # split into measures on '|'
            rows.append((label, body))
        # determine columns from the longest row's non-bar length
        # build a merged column timeline using '|' as measure boundaries from first row
        ref = block[0][1]
        # positions of characters that are not bar lines
        # We treat each measure (between |) separately.
        # Build measure segments from ref row.
        def segments(s):
            segs, cur = [], ""
            started = False
            for ch in s:
                if ch == "|":
                    if started:
                        segs.append(cur)
                    cur = ""; started = True
                else:
                    cur += ch
            return [seg for seg in segs if seg.strip("-") != "" or True]
        seg_lists = {label: segments(body) for label, body in block}
        nseg = max(len(v) for v in seg_lists.values())
        for si in range(nseg):
            width = max((len(seg_lists[l][si]) for l in seg_lists if si < len(seg_lists[l])), default=0)
            if width == 0:
                continue
            bar_slots = max(1, round(float(nominal) * dtx.GRID))
            chan = {}
            for label, segs in seg_lists.items():
                if si >= len(segs):
                    continue
                seg = segs[si]
                midi = _ASCII_LANES.get(label)
                if midi is None or midi not in dtx.MAP:
                    continue
                ch, lab = dtx.MAP[midi]
                for col, chx in enumerate(seg):
                    if chx in _HIT_CHARS:
                        frac = col / width
                        slot = int(round(frac * bar_slots))
                        if slot >= bar_slots:
                            slot = bar_slots - 1
                        chan.setdefault(ch, {}).setdefault(Fraction(slot, bar_slots), dtx.LABEL2SLOT[lab])
            events.append(chan)
            barlens.append(nominal)
    if not any(events):
        raise RuntimeError("ASCII tab parsed but no recognizable drum hits were found.")
    return events, barlens, round(float(bpm), 3)


# ---------------- Audio-only (beta) ----------------
def _read_mono(path):
    with wave.open(path, "r") as w:
        sr = w.getframerate(); ch = w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0
    if ch == 2:
        x = x.reshape(-1, 2).mean(axis=1)
    return x, sr

def _onset_env(x, sr, hop=256, win=1024):
    wnd = np.hanning(win); nfr = (len(x) - win) // hop
    prev = None; onset = np.zeros(nfr)
    for i in range(nfr):
        mag = np.abs(np.fft.rfft(x[i*hop:i*hop+win] * wnd))
        if prev is not None:
            d = mag - prev; onset[i] = np.sum(d[d > 0])
        prev = mag
    onset /= (onset.max() or 1)
    return onset, sr / hop

def _estimate_bpm(onset, fps, lo=70, hi=200):
    env = onset - onset.mean()
    ac = np.correlate(env, env, "full")[len(env)-1:]
    best = (0, None)
    for bpm in np.arange(lo, hi, 0.25):
        lag = 60.0 / bpm * fps
        i = int(round(lag))
        if 1 <= i < len(ac) and ac[i] > best[0]:
            best = (ac[i], bpm)
    return best[1] or 120.0

def _classify(seg, sr):
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    freqs = np.fft.rfftfreq(len(seg), 1/sr)
    tot = X.sum() + 1e-9
    low = X[(freqs >= 20) & (freqs < 150)].sum() / tot
    mid = X[(freqs >= 150) & (freqs < 2000)].sum() / tot
    high = X[freqs >= 6000].sum() / tot
    centroid = (freqs * X).sum() / tot
    if low > 0.35 and centroid < 800:
        return 36  # kick
    if high > 0.30:
        # bright: hat vs cymbal by decay length (approx via energy spread)
        return 42 if mid < 0.25 else 49
    return 38  # snare-ish default

def from_audio_drums(drum_wav, bpm=None, progress=None):
    """Detect + classify drum onsets from an isolated drum stem. Beta quality."""
    if progress: progress("Analyzing drum stem (audio-only transcription, beta)...")
    x, sr = _read_mono(drum_wav)
    onset, fps = _onset_env(x, sr)
    if bpm is None:
        bpm = _estimate_bpm(onset, fps)
    # peak pick
    nfr = len(onset); gap = int(0.07 * fps)
    mov = np.convolve(onset, np.ones(int(0.2*fps))/int(0.2*fps), mode="same")
    peaks = []; i = 1
    while i < nfr - 1:
        if onset[i] > onset[i-1] and onset[i] >= onset[i+1] and onset[i] > mov[i]+0.04 and onset[i] > 0.06:
            peaks.append(i); i += gap
        else:
            i += 1
    bar_time = 4 * 60.0 / bpm
    anchor = peaks[0] / fps if peaks else 0.0   # first onset = bar 1 downbeat
    hop_n = int(0.04 * sr)
    ev = {}
    for p in peaks:
        t = p / fps - anchor
        if t < 0: continue
        mi = int(t // bar_time)
        pos_frac = (t - mi * bar_time) / bar_time
        slot = int(round(pos_frac * dtx.GRID))
        if slot >= dtx.GRID: slot = dtx.GRID - 1
        s0 = int((p/fps) * sr)
        seg = x[s0:s0 + hop_n]
        if len(seg) < 32: continue
        midi = _classify(seg, sr)
        ch, lab = dtx.MAP[midi]
        ev.setdefault(mi, {}).setdefault(ch, {}).setdefault(Fraction(slot, dtx.GRID), dtx.LABEL2SLOT[lab])
    n_bars = (max(ev) + 1) if ev else 1
    events = [ev.get(i, {}) for i in range(n_bars)]
    barlens = [Fraction(1)] * n_bars
    # add a small lead-in bar so the first hit isn't at t=0 (BGM starts at 0)
    return events, barlens, round(bpm, 3), anchor
