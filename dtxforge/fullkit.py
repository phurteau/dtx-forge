"""Full-kit audio transcription (beta).

Separates an isolated drum stem into per-instrument sub-stems with a neural model,
then onset-detects each sub-stem and sub-classifies toms (by pitch) and cymbals
(crash/ride/hat) into DTX lanes. This recovers toms and ride - which the single
band-heuristic path (transcribe.from_audio_drums) cannot.

Engines:
  * 'inagoy'  - DrumSep HDemucs, 4 stems (kick/snare/toms/cymbals; hats live in the
                cymbals stem). ~160 MB, loads via the demucs library we already ship.
  * 'larsnet' - 5 stems (kick/snare/toms/hihat/cymbals). ~562 MB, vendored U-Nets.

Model weights are downloaded on first use to %LOCALAPPDATA%/DTXForge/models - they
are NOT bundled or redistributed. Licenses: inagoy DrumSep (unstated; personal use),
LarsNet (CC BY-NC 4.0).
"""
import os, wave, urllib.request, numpy as np
from fractions import Fraction
from . import dtx, transcribe as T


# ----------------------------------------------------------------------------- paths
def models_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    d = os.path.join(base, "DTXForge", "models")
    os.makedirs(d, exist_ok=True)
    return d


def _download(url, dst, progress=None, label="model"):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".part"
    if progress:
        progress(f"Downloading {label} (first use only)...")
    req = urllib.request.Request(url, headers={"User-Agent": "DTXForge"})
    with urllib.request.urlopen(req) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        got = 0; next_mark = 20 * 1024 * 1024
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk); got += len(chunk)
            if progress and got >= next_mark:
                pct = f" ({got*100//total}%)" if total else ""
                progress(f"  {label}: {got//(1024*1024)} MB{pct}")
                next_mark += 20 * 1024 * 1024
    os.replace(tmp, dst)
    if progress:
        progress(f"  {label}: download complete ({got//(1024*1024)} MB).")
    return dst


# ----------------------------------------------------------------------------- audio io
def _read_stereo(path, target_sr=44100):
    """Return (channels=2, samples) float32 at native rate; caller assumes 44100."""
    with wave.open(path, "r") as w:
        sr = w.getframerate(); ch = w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    x = x.reshape(-1, ch).T if ch > 1 else x.reshape(1, -1)
    if x.shape[0] == 1:
        x = np.vstack([x, x])
    return x, sr


# ----------------------------------------------------------------------------- engine: inagoy
INAGOY_URL = ("https://github.com/ZFTurbo/Music-Source-Separation-Training/"
              "releases/download/v1.0.5/model_drumsep.th")
# the checkpoint labels its sources in Spanish
INAGOY_SRCMAP = {"bombo": "kick", "redoblante": "snare", "platillos": "cymbals", "toms": "toms"}


def _separate_inagoy(drum_wav, progress=None):
    import torch
    from demucs.states import load_model
    from demucs.apply import apply_model
    path = os.path.join(models_dir(), "inagoy", "model_drumsep.th")
    if not os.path.exists(path):
        _download(INAGOY_URL, path, progress, "inagoy DrumSep model (~160 MB)")
    if progress:
        progress("Loading inagoy DrumSep...")
    model = load_model(path); model.eval()
    x, sr = _read_stereo(drum_wav)
    mix = torch.from_numpy(x).unsqueeze(0)
    if progress:
        progress("Separating kick / snare / toms / cymbals...")
    with torch.no_grad():
        out = apply_model(model, mix, shifts=1, split=True, overlap=0.25, progress=False)[0]
    stems = {}
    for i, name in enumerate(model.sources):
        canon = INAGOY_SRCMAP.get(str(name).lower(), str(name).lower())
        stems[canon] = out[i].mean(0).cpu().numpy()          # mono
    return stems, sr, False        # has_isolated_hat = False (hats are inside 'cymbals')


# ----------------------------------------------------------------------------- engine: larsnet
def _separate_larsnet(drum_wav, progress=None):
    from . import larsnet_engine
    return larsnet_engine.separate(drum_wav, models_dir(), _download, _read_stereo, progress)


ENGINES = {
    "inagoy": _separate_inagoy,
    "larsnet": _separate_larsnet,
}


# ----------------------------------------------------------------------------- onset + classify
def _onset_times(x, sr, min_gap=0.06, thr_rel=0.05, thr_abs=0.06):
    """Broadband spectral-flux onsets on an isolated sub-stem -> list of (time_s, peak)."""
    envs, fps = T._band_envs(x, sr, [(20, sr / 2)])
    env = envs[0]
    peaks = T._pick(env, fps, min_gap=min_gap, thr_rel=thr_rel, thr_abs=thr_abs)
    return [(p / fps, env[p]) for p in peaks], env, fps


def _fundamental(seg, sr, lo=45, hi=400):
    """Autocorrelation pitch estimate (Hz) for a tom hit; 0 if unclear."""
    seg = seg - seg.mean()
    if len(seg) < 64:
        return 0.0
    ac = np.correlate(seg, seg, "full")[len(seg) - 1:]
    lo_lag = max(1, int(sr / hi)); hi_lag = min(len(ac) - 1, int(sr / lo))
    if hi_lag <= lo_lag:
        return 0.0
    i = int(np.argmax(ac[lo_lag:hi_lag])) + lo_lag
    return sr / i if i > 0 else 0.0


def _tom_lane(freq):
    """Fundamental Hz -> GM tom: floor(41) / low-mid(47) / high(48)."""
    if freq <= 0:
        return 47
    if freq < 110:
        return 41
    if freq < 190:
        return 47
    return 48


def _assign_toms(cands):
    """Toms are isolated so onsets are reliable, but absolute pitch varies by kit.
    Split high/low/floor adaptively by the terciles of THIS song's tom fundamentals;
    if the pitch spread is too small (really one tom), keep them all on low-mid tom."""
    if not cands:
        return []
    freqs = [f for _, f in cands if f > 0]
    if len(freqs) < 6 or (max(freqs) - min(freqs) < 45):
        return [(t, 47) for t, _ in cands]          # not enough spread -> single tom
    lo = float(np.percentile(freqs, 33)); hi = float(np.percentile(freqs, 66))
    out = []
    for t, f in cands:
        if f <= 0:
            lane = 47
        elif f < lo:
            lane = 41                                # lowest pitch -> floor tom
        elif f < hi:
            lane = 47                                # low-mid tom
        else:
            lane = 48                                # highest pitch -> high tom
        out.append((t, lane))
    return out


def _spectral(seg, sr):
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) if len(seg) >= 32 else np.array([1.0])
    freqs = np.fft.rfftfreq(len(seg), 1 / sr) if len(seg) >= 32 else np.array([0.0])
    tot = X.sum() + 1e-9
    centroid = float((freqs * X).sum() / tot)
    return centroid


def _classify_cymbal(x, sr, p_time, isolated_hat):
    """Classify one cymbal-stem hit into a GM midi number.

    isolated_hat=True  (LarsNet): the hi-hat lives in its own stem, so this stem is
        crash + ride only -> split crash (long wash) vs ride (shorter metallic ping).
    isolated_hat=False (inagoy): this stem is hi-hat + crash + ride mixed. We can only
        reliably pull out the loud, long crashes; the rest read as closed hi-hat.
        Ride is NOT separable here (documented limitation of the lite engine)."""
    s0 = int(p_time * sr)
    seg = x[s0:s0 + int(0.05 * sr)]
    if len(seg) < 32:
        return 42 if not isolated_hat else 49
    tail = x[s0 + int(0.08 * sr): s0 + int(0.40 * sr)]
    peak = float(np.max(np.abs(x[s0:s0 + int(0.03 * sr)])) or 1e-9)
    sustain = float(np.sqrt((tail ** 2).mean())) / peak if tail.size else 0.0
    if isolated_hat:
        # crash = long sustained wash; ride = shorter, more periodic ping
        return 49 if sustain > 0.33 else 51
    # inagoy combined stem: conservative crash gate (from First Date feature analysis:
    # sustain>0.35 & peak>0.08 -> ~4% of hits, matching real crash frequency).
    if sustain > 0.35 and peak > 0.08:
        return 49                       # crash
    return 42                           # closed hi-hat


def transcribe_stems(stems, sr, bpm=None, progress=None, has_isolated_hat=False, standardize=True):
    """Per-stem onset detection + sub-classification -> (events, barlens, bpm, anchor).
    Same event structure as transcribe.from_audio_drums so the pipeline is unchanged."""
    hits = []   # (time_s, GM-midi)
    tom_cands = []   # (time_s, fundamental_hz) resolved to lanes after collection

    def add(stem, midi_fixed=None, kind=None):
        x = stems.get(stem)
        if x is None or not np.any(x):
            return
        # refractory gap + detection floor per stem. Toms and cymbals bleed from the
        # louder drums, so they get a longer refractory and a higher floor to suppress
        # phantom hits (the "impossible tom run" cause) before standardize runs.
        gaps = {"kick": 0.09, "snare": 0.08, "toms": 0.11, "hihat": 0.05, "cymbals": 0.06}
        thr = {"toms": (0.07, 0.10), "cymbals": (0.06, 0.09), "hihat": (0.05, 0.07)}
        tr, ta = thr.get(stem, (0.05, 0.06))
        ons, _, _ = _onset_times(x, sr, min_gap=gaps.get(stem, 0.06), thr_rel=tr, thr_abs=ta)
        for t, _pk in ons:
            if kind == "tom":
                s0 = int(t * sr); seg = x[s0:s0 + int(0.06 * sr)]
                tom_cands.append((t, _fundamental(seg, sr)))
            elif kind == "hihat":
                s0 = int(t * sr)
                tail = x[s0 + int(0.06 * sr): s0 + int(0.30 * sr)]
                peak = float(np.max(np.abs(x[s0:s0 + int(0.03 * sr)])) or 1e-9)
                sus = float(np.sqrt((tail ** 2).mean())) / peak if tail.size else 0.0
                hits.append((t, 46 if sus > 0.35 else 42))     # open vs closed
            elif kind == "cymbal":
                hits.append((t, _classify_cymbal(x, sr, t, has_isolated_hat)))
            else:
                hits.append((t, midi_fixed))

    if progress:
        progress("Detecting onsets per instrument...")
    add("kick", midi_fixed=36)
    add("snare", midi_fixed=38)
    add("toms", kind="tom")
    for t, midi in _assign_toms(tom_cands):
        hits.append((t, midi))
    if has_isolated_hat:
        add("hihat", kind="hihat")
    add("cymbals", kind="cymbal")

    if not hits:
        return [{}], [Fraction(1)], round(bpm or 120.0, 3), 0.0

    # tempo from the kick+snare backbone if not supplied
    if bpm is None:
        kx = stems.get("kick"); sx = stems.get("snare")
        ref = None
        for a in (kx, sx):
            if a is not None and np.any(a):
                e, fps = T._band_envs(a, sr, [(20, sr / 2)])
                ref = e[0] if ref is None else ref + e[0]
        bpm = T._estimate_bpm(ref, fps) if ref is not None else 120.0

    # Standardize (default): quantize to a musical 1/16 grid, de-dupe, and cap
    # simultaneous voices so the raw onsets become a clean, playable chart. When
    # standardize is off, emit exactly what was heard on the fine 1/64 grid with no
    # voice cap - the raw first-pass transcription.
    from . import standardize as _std
    if standardize:
        events, barlens, anchor = _std.build_events(hits, bpm, max_hand_voices=2, adaptive=True)
    else:
        events, barlens, anchor = _std.build_events(hits, bpm, grid_div=64, max_hand_voices=999)
    return events, barlens, round(bpm, 3), anchor


def from_audio_fullkit(drum_wav, bpm=None, progress=None, standardize=True):
    """Automatic dual-engine full-kit transcription - no user selection.

    Runs BOTH separators and lets each own the lanes it is strongest at, since they
    are complementary:
        * inagoy (htdemucs)  -> kick, snare, toms        (the drum bodies)
        * LarsNet (U-Nets)   -> closed hat, open hat, ride, crash  (metals + hats)

    LarsNet uniquely isolates the hi-hat into its own stem, which is what makes ride
    recoverable; inagoy's htdemucs is a strong separator for the membrane drums and
    reuses the demucs runtime we already load. Combining them yields a fuller kit
    than either alone. Degrades gracefully: if one engine is unavailable the other
    covers what it can; if both fail the caller falls back to the fast heuristic.
    """
    ina = lars = None
    ina_err = lars_err = None
    try:
        if progress: progress("Full-kit engine 1/2: inagoy (kick / snare / toms)...")
        ina, ina_sr, _ = _separate_inagoy(drum_wav, progress=progress)
    except Exception as e:
        ina_err = str(e)[:120]
        if progress: progress(f"  inagoy unavailable: {ina_err}")
    try:
        if progress: progress("Full-kit engine 2/2: LarsNet (hi-hat / ride / crash)...")
        lars, lars_sr, _ = _separate_larsnet(drum_wav, progress=progress)
    except Exception as e:
        lars_err = str(e)[:120]
        if progress: progress(f"  LarsNet unavailable: {lars_err}")

    if ina is None and lars is None:
        raise RuntimeError(f"both full-kit engines failed (inagoy: {ina_err}; larsnet: {lars_err})")

    # Fuse: bodies from inagoy, metals+hats from LarsNet. Fall back per-family.
    stems = {}
    if ina is not None and lars is not None:
        sr = ina_sr
        for k in ("kick", "snare", "toms"):
            stems[k] = ina.get(k)                    # inagoy owns the drum bodies
        stems["hihat"] = lars.get("hihat")           # LarsNet owns the metals + hats
        stems["cymbals"] = lars.get("cymbals")
        isolated_hat = True
        if progress: progress("Fusing engines: bodies from inagoy, hats/ride/crash from LarsNet.")
    elif lars is not None:
        sr = lars_sr; stems = lars; isolated_hat = True
        if progress: progress("Using LarsNet only (inagoy unavailable).")
    else:
        sr = ina_sr; stems = ina; isolated_hat = False
        if progress: progress("Using inagoy only (LarsNet unavailable - no ride).")

    return transcribe_stems(stems, sr, bpm=bpm, progress=progress,
                            has_isolated_hat=isolated_hat, standardize=standardize)
