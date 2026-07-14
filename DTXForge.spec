# PyInstaller spec for DTX Forge (onedir desktop app)
from PyInstaller.utils.hooks import collect_all, collect_submodules
import os

datas, binaries, hiddenimports = [], [], []

# heavy / tricky packages: grab everything (py + data + dylibs)
for pkg in ["demucs", "torch", "yt_dlp", "imageio_ffmpeg", "soundfile",
            "julius", "einops", "dora", "openunmix", "webview", "pythonnet",
            "clr_loader"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

hiddenimports += collect_submodules("uvicorn")
hiddenimports += ["dtxforge", "dtxforge.songsterr", "dtxforge.audio",
                  "dtxforge.transcribe", "dtxforge.dtx", "dtxforge.drumkit",
                  "dtxforge.pipeline", "dtxforge.report", "dtxforge.notes",
                  "dtxforge.humanize", "dtxforge.playability", "dtxforge.autosync",
                  "dtxforge.sources", "dtxforge.faithfulness", "dtxforge.difficulty",
                  "dtxforge.fullkit", "dtxforge.larsnet_engine",
                  "dtxforge.standardize", "dtxforge.simplify",
                  "dtxforge.vendor", "dtxforge.vendor.larsnet_unet",
                  "guitarpro", "attr", "attrs",
                  "app", "anyio", "mido", "clr", "webview.platforms.winforms"]

# gdown (LarsNet weights fetch) - optional; only needed for the Full kit+ engine
try:
    d, b, h = collect_all("gdown")
    datas += d; binaries += b; hiddenimports += h
except Exception:
    pass

# app data files
datas += [("web", "web"), ("assets", "assets")]

block_cipher = None

a = Analysis(
    ["desktop.py"],
    pathex=[os.getcwd()],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DTX Forge",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # no console window (native app)
    icon=None,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name="DTX Forge",
)
