"""Synthesize a general-MIDI drum kit of one-shot WAVs (numpy, 44.1k/16-bit mono).
Generated once and cached under assets/drumkit/."""
import numpy as np, wave, os

SR = 44100

def _env_expdecay(n, tau):
    t = np.arange(n) / SR
    return np.exp(-t / tau)

def _noise(n, seed=0):
    return np.random.default_rng(seed).standard_normal(n)

def _lp(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR); y = np.empty_like(x); p = 0.0
    for i in range(len(x)):
        p = (1 - a) * x[i] + a * p; y[i] = p
    return y

def _hp(x, cutoff):
    return x - _lp(x, cutoff)

def _save(path, sig, peak=0.9):
    sig = np.asarray(sig, dtype=np.float64)
    m = np.max(np.abs(sig)) or 1.0
    sig = np.tanh(sig / m * peak * 1.1)
    data = (sig * 32767).astype("<i2")
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(data.tobytes())

def _kick():
    n = int(0.28 * SR); t = np.arange(n) / SR
    f = 110 * np.exp(-t / 0.03) + 45
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env_expdecay(n, 0.09)
    click = _hp(_noise(n), 3000) * _env_expdecay(n, 0.004) * 0.6
    return body + click

def _snare():
    n = int(0.22 * SR); t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * 185 * t) + 0.7 * np.sin(2 * np.pi * 330 * t)) * _env_expdecay(n, 0.03)
    nz = _hp(_noise(n), 1200) * _env_expdecay(n, 0.11) * 1.1
    return tone * 0.7 + nz

def _tom(f0):
    n = int(0.35 * SR); t = np.arange(n) / SR
    f = f0 * np.exp(-t / 0.12) + f0 * 0.55
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env_expdecay(n, 0.16)
    click = _hp(_noise(n), 2500) * _env_expdecay(n, 0.003) * 0.3
    return body + click

def _hat(tau, cut=8000):
    n = int((tau * 6 + 0.02) * SR); t = np.arange(n) / SR
    nz = _hp(_noise(n), cut)
    metal = sum(np.sin(2 * np.pi * f * t) for f in (6300, 8200, 10500, 12800)) * 0.15
    return (nz + metal) * _env_expdecay(n, tau)

def _cymbal(tau, bright=1.0):
    n = int((tau * 4 + 0.05) * SR); t = np.arange(n) / SR
    nz = _hp(_noise(n), 4000 * bright)
    parts = sum(np.sin(2 * np.pi * f * t) for f in (3400, 5100, 7300, 9600, 11200, 13500)) * 0.1
    return (nz + parts) * _env_expdecay(n, tau)

def _bell():
    n = int(0.6 * SR); t = np.arange(n) / SR
    tone = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((1200, 1.0), (1830, 0.6), (2400, 0.4), (3600, 0.25)))
    return tone * _env_expdecay(n, 0.28)

# label -> generator
KIT = {
    "bd": _kick, "sd": _snare,
    "ht": lambda: _tom(240), "lt": lambda: _tom(175), "ft": lambda: _tom(120),
    "hh": lambda: _hat(0.028), "ho": lambda: _hat(0.28, 7000), "lp": lambda: _hat(0.020),
    "cy": lambda: _cymbal(0.9, 1.2), "rd": lambda: _cymbal(0.45, 0.8), "rb": _bell,
}

def ensure_kit(dest_dir):
    """Generate the kit WAVs into dest_dir if missing; return {label: filename}."""
    os.makedirs(dest_dir, exist_ok=True)
    files = {}
    for label, gen in KIT.items():
        fn = f"{label}.wav"; path = os.path.join(dest_dir, fn)
        if not os.path.exists(path):
            _save(path, gen())
        files[label] = fn
    return files

if __name__ == "__main__":
    here = os.path.dirname(__file__)
    out = os.path.join(here, "..", "assets", "drumkit")
    print("generated:", ensure_kit(out))
