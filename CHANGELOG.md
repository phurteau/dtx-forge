# Changelog

## v1.4.1

Fidelity fix - the chart now mirrors the song's actual per-bar note values, at every
difficulty. Grounded in an analysis of **4,700+ real GITADORA/DrumMania charts**, which
showed that charts of *every* tier mix note values freely (even Basic charts contain
16ths and triplets) and that 16th notes are a minority even at Extreme (~11%).

- **Per-bar fidelity (audio "Standardize").** Each bar is now quantized to its **own
  natural subdivision** - quarter, 8th, 16th, 32nd *or* triplet, whichever that bar
  actually plays - instead of a fixed 1/16 grid. A sparse bar stays sparse; the next bar
  with a 16th run or a 32nd fill keeps its density. Triplets are preserved.
- **Difficulty no longer caps note values.** Tiers previously thinned timekeeping to a
  per-tier grid (Basic → 1/4, Advanced → 1/8, Extreme → 1/16). That's removed: a chart of
  **any** difficulty keeps the song's real 16th / triplet / 32nd content. The tier is a
  *rating* of density and complexity, not a note-value ceiling.
- **DTXMania style no longer inflates density.** Its timekeeping pass now only removes
  timing *jitter* (snapping to each bar's own subdivision) and never rewrites a bar to a
  fixed tier grid, so an 8th-note bar stays 8th and a sparse bar stays sparse.
- No new features; generation output is more faithful to the source.

## v1.4.0

DTXMania **Notes style** matured into an empirically-grounded chart generator, a critical
silent-drums fix, and automatic tier-gated foot technique.

- **Fixed: audio-only charts had no drum sounds.** The standardize pass wrote note cells
  as the drum label instead of the DTX WAV slot, so DTXMania played nothing on the pads.
  Cells now reference the correct WAV - drums sound again.
- **Notes style (Transcribed / DTXMania).** The DTXMania regularizer is a first-class **Notes
  style** control that works for **both** a supplied tab and audio transcription, not just
  audio-only. The audio-only toggle is now just **Raw / Standardize**.
- **DTXMania style, grounded in 2,000 real GITADORA charts.** The regularizer was rebuilt against
  an analysis of 2,000 published charts (188,760 bars):
  - **Steady, evenly-spaced timekeeping** at the tier's resolution (80% of real hi-hat bars are
    perfectly even).
  - **One timekeeper per section** - hi-hat *or* ride, chosen per phrase instead of flip-flopping
    bar to bar (the two coexist in only ~0.1% of real bars).
  - **Crashes are preserved, not thinned.** Earlier builds collapsed crashes to one per bar and
    injected a crash on every phrase start; real charts do neither - crashes stack freely with
    kick/snare, and only 31% of phrase downbeats carry one - so both rules were removed.
  - A **closed** hi-hat sharing a crash's tick (a transcription artifact - 3 in 160k real bars)
    is cleaned up; a rare **open** hi-hat under a crash is kept.
- **Automatic, tier-gated foot technique in DTXMania style.** Basic/Advanced add little or none;
  Extreme adds double bass on genuinely fast kick runs; Master adds the hi-hat "chick" on 2 & 4
  too (95% of real Master charts use it, 58% use double bass). The left foot is one resource - a
  hi-hat chick and a double kick never share a tick. The manual **LFHH / DKDK** toggles remain for
  Transcribed style and are handled automatically when DTXMania is selected.
- **Lower density.** Hi-hat and ride are de-conflicted (real charts don't play both at once),
  roughly halving the timekeeping density on busy songs. Master keeps both.
- **Stop button.** A red Stop next to Generate cancels a run mid-generation so you can change
  settings; the pipeline aborts at the next stage boundary.
- **Version** shown in the header; minor UI polish.

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
