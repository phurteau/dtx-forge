# Changelog

## v1.5.3

Black dark mode, a colour-wheel accent picker, and in-app update notifications.

- **True-black dark mode.** Dark mode is now genuine black with neutral panels instead of the
  dimmed-green theme, so the accent colour is what stands out. The default accent is unchanged
  (the deep green), and light mode is untouched.
- **Colour-wheel accent picker.** The accent picker is now an HSV colour wheel with a brightness
  slider, a hex field and a live preview - pick any colour, not just the old presets.
- **Update notifications.** On launch the app checks GitHub for a newer release and shows a
  dismissible banner when one is available. One click downloads the new build straight into your
  Downloads folder (unzip and run to update). Fails silently when offline - no banner, no error.

## v1.5.2

Data-calibrated cleanup thresholds and a regression test that keeps them honest.

- **Keep thresholds are now empirically calibrated, not hand-picked.** A closed-loop calibration
  takes real corpus charts as ground truth, injects synthetic transcription noise into the
  hi-hat/ride (bleed ghosts plus dropped and jittered hits), runs the cleaner at each candidate
  strength, and scores how well the result recovers the original chart (F1 over 1/16 timekeeping
  slots). Averaged over multiple noise seeds and ~160 charts per tier, the data picks a gentler
  keep strength (35 for Basic, 30 for Advanced/Extreme/Master) than the earlier hand-picked
  50/45/38/32, which sat past the plateau and over-cleaned. Kick and snare remain untouched.
- **Grounding regression test.** `test_grounding.py` re-runs a mini calibration and fails if the
  shipped thresholds ever drift off the data-optimal plateau, and checks the per-lane note grids
  still match how real charts subdivide each lane.
- **Corpus tooling in the repo.** The mining and calibration scripts used to derive every threshold
  now live under `tools/` (with a README), so the grounding is reproducible from the real charts.

## v1.5.1

Note-preservation fix and a much deeper grounding in real charts.

- **Keeps the notes that belong there.** v1.5.0's DTXMania cleanup was too aggressive - it voted
  the whole groove (including kick and snare) toward a "consensus" and deleted real playing. Now the
  regularization only cleans the bleed-prone **hi-hat / ride timekeeping**; **kick and snare are
  preserved exactly as played**, so fast double-kicks, ghost snares and syncopation all survive.
- **Off-beat timekeeping is respected.** Off-beats are ~40% of every lane's hits in real charts (up
  to 55% at Master), so the cleanup no longer treats an off-beat hi-hat as suspect - disco/funk/ska
  off-beat hats, off-beat ride and varied 16th patterns are kept; only sporadic bleed is removed.
- **Genre-safe.** Jazz swing (triplet ride), shuffle, odd meters (5/4, 7/8, waltz), blast beats,
  double bass, polyrhythm and ghost notes are all left intact - verified by a genre test suite.
- **Tier-aware cleanup.** Grounded in the full corpus (see below), difficulty scales hard - a Master
  chart is 3.5× denser than Basic and off-beat over half the time - so the cleanup is now gentler at
  higher difficulties (where there's more intentional playing) and firmer at lower ones.
- **Grounded in 6,621 real charts.** Every threshold (de-flam window, keep strength, per-lane note
  grids) is now calibrated from the whole deduplicated corpus across both sets and documented in
  `docs/drum-corpus-facts.md` (+ machine-readable `docs/drum_facts*.json`), not assumed.

## v1.5.0

A built-in chart editor, a big step up in charting quality, and a smoother finish flow.

- **Cleaner, more "real" charts (DTXMania Chart Style).** The DTXMania style now grooms the whole
  groove toward the way real charts are actually written, grounded in a corpus of **4,700+ real
  GITADORA/DrumMania charts**. Instead of snapping each bar on its own (which read jittery and
  "thrown together"), it now finds a clean groove for each phrase and **repeats it**, so the chart
  is as consistent bar-to-bar as a real one. Stray, bleed-induced ghost hi-hats are voted out, so a
  quarter-note hat stays a quarter instead of inflating into a busy 8th/16th mess.
- **The whole kit reads neat, not just the hi-hats.** Cymbals, ride and open hi-hats are de-jittered
  onto a clean grid too, so crashes land on the beat instead of between grid lines. Toms are cleaned
  the same way.
- **No more impossible rolls.** During a fast snare roll or tom fill both hands are on the drums, so
  the hi-hat/ride that transcription used to layer on top (physically impossible to play) is now
  removed for the length of the fill.
- **Chart Style options.** When **DTXMania** style is selected, you can group the right cymbal onto
  the ride, and (optionally) map open hi-hats to the left-foot pedal. Left-foot technique (hi-hat
  chick / double bass) is added automatically, tier-appropriate.
- **Visual chart editor.** A new **Review & edit notes** step opens a vertical, one-bar-at-a-time
  editor (DTXMania-style colored lanes). **Click** an empty cell to add a note, **drag** to move it,
  **right-click** to delete; a grid selector (¼ · 8th · ⅓ · 16th · 24 · 32nd) sets the snap. **Undo**
  (button or Ctrl+Z) and a **Reset** that also restores the view. Clean up anything by hand.
- **Game-style playback in the editor.** Notes fall down a highway past a raised **judgement line**
  (a little above the pad icons, like a real rhythm game), the charted drum sounds play as each note
  crosses the line, and the whole-song play animation is smooth. Per-bar **Play** hears just the slice
  under the bar you're editing, with **🐢 Slow / 🐇 Fast** (pitch-preserved), a scroll-speed control,
  and a **loop** toggle. A draggable scrubber seeks and previews exactly where the line sits.
- **De-flam cymbals.** Audio transcription can split one hard cymbal/hi-hat hit into a flam (a phantom
  second onset from decay or mic bleed). Same-lane cymbal/hi-hat hits closer than ~70 ms are collapsed
  to one, so timekeeping reads clean. Toms, snare and kick are left alone (they really do play fast).
- **Downloads land in your Downloads folder.** Clicking **Download chart .zip** now saves the package
  straight to your Downloads folder and shows you the exact path (the in-app browser's download
  handler could silently drop it before). The chart is packaged **once, on download**, after any edits.
- **UI polish.** "Notes Style" is now **Chart Style**; a **Make another chart** button resets the page
  after a download; console shows a blinking cursor while a stage runs; trimmed wording throughout.

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
