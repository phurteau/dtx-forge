# Changelog

## v1.3

Cleaner, more playable audio-only charts, difficulty that actually simplifies, and UI polish.

- **Standardize pass (audio-only).** Raw drum onsets are quantized to a clean **1/16 grid** while
  **genuine 1/32 fills/rolls are preserved**, and doubled / jittered / physically-impossible notes are
  removed - fixing the "too many notes, impossible to play" charts. Toggle **Standardize / Raw** in the
  Advanced card (Raw emits exactly what was heard).
- **Difficulty tiers now thin density.** Lower tiers trim the hi-hat / ride timekeeping (Basic → 1/4,
  Advanced → 1/8, Extreme → 1/16, Master → everything); kick/snare/toms/crashes are untouched. The score
  is re-rated to match the emitted notes.
- **BPM octave correction.** Tempo detection no longer locks onto the half-time pulse (e.g. a 190 BPM punk
  song reading as 95); a well-supported double below 100 BPM is auto-corrected.
- **UI.** Generate button moved to the bottom of the input column, drum emoji removed, card 4 renamed
  **Advanced**, and the default accent is the darker green in dark mode.
- **`uninstall.cmd`** helper reclaims the ~1 GB of downloaded model weights (the app itself is portable -
  just delete the folder).
- **Spotify links** are explicitly unsupported (DRM) - use YouTube / SoundCloud / a direct file / Upload.

## v1.2

Difficulty tiers, required metadata, and a standalone-exe reliability fix.

- **Difficulty tiers.** Basic / Advanced / Extreme / Master picker; the `.dtx` is named by tier
  (`bsc` / `adv` / `ext` / `mstr`) in its `set.def` slot. Auto-derives from the 0.00–9.99 score.
- **Title and Artist are required** (client validation + server guard).
- **Standalone exe launch fix.** The windowed build's local server crashed on startup
  (`'NoneType' object has no attribute 'isatty'`); it now starts cleanly and shows the native window, with
  a browser fallback and a diagnostic log at `%LOCALAPPDATA%\DTXForge\dtxforge.log`.
- **Launcher hardening.** `DTX Forge.cmd` falls back `pythonw → pyw → python` (Microsoft Store Python has
  no `pythonw`); `run.cmd` waits for the server before opening the browser.

## v1.1

Audio-only full-kit transcription, automatic difficulty, and UI refinements.

- **Notation is now optional; audio is required.** Leave the tab blank and DTX Forge
  transcribes the drums straight from the audio.
- **Full-kit audio transcription** - automatically separates the drum track into
  individual pieces to recover a full kit: **kick, snare, toms (high/low/floor),
  open & closed hi-hat, ride, and crash**. Runs two complementary separation models
  (fetched at runtime, not bundled); falls back to a fast built-in detector.
- **Auto difficulty** - leave Difficulty blank and it's rated from a skilled-player
  reference so beginners get a realistic sense of the demand.
- **Any-URL audio** - YouTube, SoundCloud, Bandcamp, Vimeo and 1000+ sites, plus
  direct audio-file links.
- **BPM & difficulty auto-fill** - populate live once detected (never overwrites a
  value you typed).
- **Hi-Hat Pedal** simplified to a single **2 & 4 backbeat** toggle (the game-typical
  pattern).
- **UI** - reordered input cards (Details → Audio → Notation → Advanced),
  source-aware faithfulness (hidden in audio-only mode), "Charted using DTX Forge"
  credit written into the chart.

> Model weights are downloaded at runtime to `%LOCALAPPDATA%/DTXForge` and are **not**
> redistributed. LarsNet weights are CC BY-NC (non-commercial); see `LICENSE`.

## v1.0
First release.

- **Multi-source notation** - Songsterr (URL/id), Guitar Pro (.gp/.gp5/.gpx),
  MIDI, and pasted/uploaded ASCII drum tabs; auto-detected.
- **Audio** - YouTube (tiered: anonymous → browser session cookies → fallback,
  with a bundled deno JS runtime) or file upload.
- **Auto-sync** - aligns YouTube/uploaded audio to the chart via same-recording
  cross-correlation.
- **Drum modes** - Keep (full song), Quiet (~50% drums), Remove (~90% arcade).
- **Hi-Hat Pedal** - 1:1 True / Medium / Off left-foot hi-hat.
- **DKDK Mode** - On/Off double-bass; converts only too-fast-for-one-leg kicks.
- **Human-playability check** - 2-hands/2-feet model with auto-relax.
- **Faithfulness score** - reports how true the chart is to the tab.
- **Pipeline visualizer**, light/dark themes, accent color picker.
- Spec-correct DTXMania channel + GM-drum lane mapping.
