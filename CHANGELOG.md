# Changelog

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
