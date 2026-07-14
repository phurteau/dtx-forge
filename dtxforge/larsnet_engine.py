"""LarsNet full-kit engine: 5-stem neural drum separation (kick / snare / toms /
hi-hat / cymbals). Because the hi-hat is isolated in its own stem, the cymbals
stem is crash + ride only - which lets DTX Forge recover ride cymbal, unlike the
inagoy engine.

Upstream: https://github.com/polimi-ispl/larsnet (Mezza et al., 2024). The model
WEIGHTS are CC BY-NC 4.0 and are fetched at runtime to %LOCALAPPDATA%/DTXForge,
never bundled. The UNet architecture is vendored in dtxforge/vendor/larsnet_unet.py.

We deliberately avoid importing torchaudio (not a DTX Forge dependency): the vendored
UNetWaveform is pure torch and accepts a raw tensor, and we resample with our own
ffmpeg path upstream, so audio arrives at 44.1 kHz already.
"""
import os
import numpy as np

WEIGHTS_GDRIVE_ID = "1U8-5924B1ii1cjv9p0MTPzayb00P4qoL"
STEMS = ["kick", "snare", "toms", "hihat", "cymbals"]
_F, _T = 2048, 512   # from LarsNet config.yaml


def _weights_dir(models_root):
    return os.path.join(models_root, "larsnet", "pretrained_larsnet_models")


def _ensure_weights(models_root, progress=None):
    wd = _weights_dir(models_root)
    have = all(os.path.exists(os.path.join(wd, s, f"pretrained_{s}_unet.pth")) for s in STEMS)
    if have:
        return wd
    # download + extract the 5-model bundle (~515 MB) on first use
    import gdown, zipfile
    root = os.path.join(models_root, "larsnet")
    os.makedirs(root, exist_ok=True)
    zpath = os.path.join(root, "larsnet_weights.zip")
    if not os.path.exists(zpath):
        if progress:
            progress("Downloading LarsNet models (~515 MB, first use only)...")
        gdown.download(id=WEIGHTS_GDRIVE_ID, output=zpath, quiet=True)
    if progress:
        progress("Extracting LarsNet models...")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(root)
    if not all(os.path.exists(os.path.join(wd, s, f"pretrained_{s}_unet.pth")) for s in STEMS):
        raise RuntimeError("LarsNet weights missing after extraction.")
    return wd


def _load_models(wd, device, progress=None):
    import sys, torch
    # make the vendored UNet importable as a top-level module name too, in case a
    # checkpoint pickled references to it (defensive; state_dicts don't need it)
    from .vendor import larsnet_unet
    models = {}
    for s in STEMS:
        if progress:
            progress(f"Loading LarsNet {s} model...")
        m = larsnet_unet.UNetWaveform(input_size=(2, _F, _T), device=device)
        ckpt = torch.load(os.path.join(wd, s, f"pretrained_{s}_unet.pth"),
                          map_location=device, weights_only=False)
        m.load_state_dict(ckpt["model_state_dict"])
        m.eval()
        models[s] = m
    return models


def separate(drum_wav, models_root, _download, _read_stereo, progress=None):
    """Separate an isolated drum stem into 5 sub-stems with LarsNet.
    Returns (stems: {name: mono float32 np.array}, sr, has_isolated_hat=True)."""
    import torch
    wd = _ensure_weights(models_root, progress)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    models = _load_models(wd, device, progress)

    x, sr = _read_stereo(drum_wav)              # (2, N) float32 @ 44100
    if progress:
        progress("Separating kick / snare / toms / hi-hat / cymbals...")
    mix = torch.from_numpy(x).float().to(device)   # (2, N)

    out = {}
    with torch.no_grad():
        for name, model in models.items():
            y, _ = model(mix)                   # (1, 2, N)
            out[name] = y.squeeze(0).mean(0).cpu().numpy()   # mono
    return out, sr, True
