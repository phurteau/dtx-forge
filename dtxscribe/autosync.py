"""Auto-sync: align an arbitrary audio track (YouTube/upload) to the chart's note
timeline using its isolated drum stem. Fits a linear (tempo alpha, offset beta)
map by 2D search on onset envelopes, then reports the front-trim needed so the
BGM lines up with the chart. Robust to intro-silence and slight tempo diffs."""
import numpy as np, wave, os, subprocess
from . import audio, notes as N


def _onset_env(path, ar=22050, target_hz=200):
    tmp = path + ".mono.wav"
    audio.to_wav(path, tmp, ar=ar, ac=1)
    with wave.open(tmp, "r") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0
    win, hop = 1024, 256
    fps = sr / hop
    wnd = np.hanning(win)
    nfr = max(0, (len(x) - win) // hop)
    prev = None
    on = np.zeros(nfr)
    for i in range(nfr):
        mag = np.abs(np.fft.rfft(x[i*hop:i*hop+win] * wnd))
        if prev is not None:
            d = mag - prev; on[i] = np.sum(d[d > 0])
        prev = mag
    if on.max() > 0:
        on /= on.max()
    t = np.arange(nfr) / fps
    T = np.arange(0, t[-1] if len(t) else 0, 1 / target_hz)
    return (np.interp(T, t, on) if len(t) else np.zeros(0)), target_hz


def _chart_env(note_times, dur, hz=200):
    n = int(dur * hz) + 1
    env = np.zeros(n)
    for t in note_times:
        i = int(round(t * hz))
        if 0 <= i < n:
            env[i] = 1.0
    # slight smoothing so correlation is stable
    k = 3
    return np.convolve(env, np.ones(k)/k, mode="same"), hz


def _fullmix_env(path, hz=200):
    """Onset envelope of a full-mix track (no separation needed)."""
    return _onset_env(path, target_hz=hz)


def _global_offset(ea, er, hz, maxlag_s=8.0):
    """Best global shift so audio-env ea aligns to reference-env er (same content
    => sharp unambiguous peak). Returns beta where audio_time = ref_time + beta."""
    n = 1
    L = max(len(ea), len(er))
    while n < 2 * L:
        n *= 2
    FA = np.fft.rfft(ea - ea.mean(), n)
    FR = np.fft.rfft(er - er.mean(), n)
    cc = np.fft.irfft(FA * np.conj(FR), n)
    cc = np.concatenate((cc[-(len(er) - 1):], cc[:len(ea)]))
    center = len(er) - 1
    ml = int(maxlag_s * hz)
    seg = cc[center - ml:center + ml]
    return (np.argmax(seg) - ml) / hz


def align_audio_to_reference(audio_path, ref_path, progress=None):
    """Align an audio track to a reference recording of the SAME song (e.g. the
    tab-synced Songsterr master). Returns (alpha, beta): audio_time = ref_time + beta.
    Same-content cross-correlation makes the global offset unambiguous and robust;
    tempo is kept at 1.0 (two recordings of the same song share tempo - a drift fit
    on self-similar pop audio only adds noise and was verified unnecessary)."""
    if progress:
        progress("Auto-sync: matching audio to reference recording...")
    ea, hz = _fullmix_env(audio_path)
    er, _ = _fullmix_env(ref_path)
    if len(ea) < hz or len(er) < hz:
        return 1.0, 0.0
    beta = _global_offset(ea, er, hz)
    if progress:
        progress(f"Auto-sync: offset {beta:+.3f}s (tempo matched).")
    return 1.0, float(beta)


def _first_strong_onset(env, hz, thr=0.30, warmup=0.2):
    """Time (s) of the first sustained strong onset in an envelope."""
    start = int(warmup * hz)
    for i in range(start, len(env)):
        if env[i] >= thr:
            return i / hz
    return 0.0


def align_audio_to_chart(drum_stem_wav, note_times, chart_dur, progress=None):
    """Return (alpha, beta_seconds): audio_time = alpha*chart_time + beta.
    Anchored on the first strong drum onset vs the chart's first note so the search
    cannot lock onto the wrong bar, then refined by local correlation."""
    if progress:
        progress("Auto-sync: analysing drum onsets...")
    ey, hz = _onset_env(drum_stem_wav)
    er, _ = _chart_env(note_times, chart_dur, hz)
    if len(ey) < hz or len(er) < hz or not note_times:
        return 1.0, 0.0

    def corr(alpha, beta):
        n = len(er)
        t_r = np.arange(n) / hz
        ty = alpha * t_r + beta
        idx = ty * hz
        i = np.floor(idx).astype(int)
        ok = (i >= 0) & (i < len(ey) - 1)
        fr = idx - i
        ys = np.zeros(n)
        ii = np.clip(i, 0, len(ey) - 2)
        ys[ok] = ey[ii[ok]] * (1 - fr[ok]) + ey[ii[ok] + 1] * fr[ok]
        a = er - er.mean(); b = ys - ys.mean()
        d = np.sqrt((a @ a) * (b @ b)) + 1e-9
        return (a @ b) / d

    # anchor: first real drum onset vs first charted note
    y_first = _first_strong_onset(ey, hz)
    c_first = min(note_times)
    beta_anchor = y_first - c_first
    if progress:
        progress(f"Auto-sync: anchor first hit audio {y_first:.2f}s vs chart {c_first:.2f}s.")

    # search beta only NEAR the anchor (+-0.8s) so it can't jump a whole bar
    best = (-9, 1.0, beta_anchor)
    for alpha in np.arange(0.994, 1.007, 0.001):
        for beta in np.arange(beta_anchor - 0.8, beta_anchor + 0.8, 0.02):
            c = corr(alpha, beta)
            if c > best[0]:
                best = (c, alpha, beta)
    _, a0, b0 = best
    for alpha in np.arange(a0 - 0.001, a0 + 0.001, 0.0002):
        for beta in np.arange(b0 - 0.04, b0 + 0.04, 0.004):
            c = corr(alpha, beta)
            if c > best[0]:
                best = (c, alpha, beta)
    cval, alpha, beta = best
    if progress:
        progress(f"Auto-sync: tempo {(alpha-1)*100:+.2f}%, offset {beta:+.3f}s (fit {cval:.2f}).")
    return float(alpha), float(beta)


def apply_alignment(src_audio, out_wav, alpha, beta):
    """Produce an aligned WAV on the chart timeline: aligned(t)=src(alpha*t+beta).
    Uses ffmpeg atempo for tempo (if needed) then a front trim/pad for offset."""
    ff = audio.ffmpeg_exe()
    filt = []
    # atempo plays faster for alpha>1 (src runs slower than chart -> speed up)
    if abs(alpha - 1.0) > 1e-4:
        filt.append(f"atempo={alpha:.6f}")
    af = ",".join(filt) if filt else None
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error"]
    if beta >= 0:
        cmd += ["-ss", f"{beta:.3f}", "-i", src_audio]
    else:
        cmd += ["-i", src_audio, "-af", f"adelay={int(-beta*1000)}|{int(-beta*1000)}"]
    if af:
        cmd += ["-af", af]
    cmd += ["-ac", "2", "-ar", "44100", out_wav]
    subprocess.run(cmd, check=True)
    return out_wav
