# Building the standalone .exe

The pre-built app is distributed as a zip (see the Releases page). To build it
yourself from source:

## Prerequisites
- Windows 10/11, Python 3.10+
- `pip install -r requirements.txt`
- `pip install pyinstaller demucs soundfile`  (Demucs pulls in PyTorch, ~2 GB)
- deno in `assets/bin/deno.exe` (run `setup.cmd`, or download from
  https://github.com/denoland/deno/releases)

## Build
```bat
python -m PyInstaller --noconfirm --clean DTXForge.spec
```
Output lands in `dist/DTX Forge/` - a folder containing `DTX Forge.exe` plus an
`_internal/` folder with all dependencies (torch, ffmpeg, deno, the web UI, and
the drum-kit samples). Zip that whole folder to distribute.

The build is **onedir** (a folder, not a single file) because the PyTorch payload
doesn't pack cleanly into a one-file exe. Total size is ~750 MB unzipped.

## Notes
- `DTXForge.spec` lists the hidden imports and bundled data. If you add a new
  `dtxforge/` module, add it to the `hiddenimports` list.
- The torch "sharding_spec not found" warnings during build are harmless
  (deprecated optional submodules).
- UI-only changes (edits to `web/index.html`) don't need a full rebuild - just
  copy the file into `dist/DTX Forge/_internal/web/` and re-zip.
