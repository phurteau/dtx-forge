# 🥁 DTX Forge

Turn a drum tab (or just audio) into a fully playable **DTXMania** chart - **no manual notation**.
It fetches the tab, grabs the song, auto-syncs the audio, applies realistic foot technique,
verifies a human can actually play it, and packages a ready-to-drop `.dtx` zip.

Built from a pipeline verified to place ~99% of charted notes within ±10–20 ms of the real recording.

![DTX Forge](docs/screenshot.png)

---

## Highlights

- **No notation, ever.** Paste a **Songsterr** URL, a **Guitar Pro** / **MIDI** URL, an **ASCII drum tab**,
  or upload a Guitar Pro / MIDI / .txt file → notes are transcribed automatically. The URL box
  auto-detects the source: as long as it has readable drum notes, DTX Forge charts it.
- **Real audio, auto-synced.** Pull the song from YouTube or upload a file; DTX Forge aligns it to the
  chart (fixes intro offset & length differences) using the same recording as a reference.
- **Full song by default.** Keep the complete track, quiet the drums, or fully remove them (arcade feel).
- **Advanced foot technique.** Hi-hat left-pedal and double-bass, each at 1:1 / Medium / Basic.
- **Human-playability check.** Every chart is verified against a 2-hands + 2-feet model and
  auto-relaxed if a passage is physically impossible.
- **Faithfulness score.** Every chart reports how true it is to the tab - **100% = untouched**,
  and below that it shows exactly what changed (notes moved to the left foot for double-kicks,
  dropped, or foot notes added).
- **Live pipeline visualizer.** Watch each stage light up as it runs.
- **Personalize it.** Light/dark themes + an accent color picker (remembered between runs).

---

## Setup (one time)

1. Install **Python 3.10+** (tick *Add Python to PATH*).
2. Double-click **`setup.cmd`** - installs core dependencies and offers to install
   Demucs (only needed for *Quiet* / *Remove* drum modes, ~2 GB).

*(The `.exe` build needs none of this - just unzip and run.)*

## Run

- **App window:** double-click **`DTX Forge.cmd`** (opens its own desktop window), or
- **Browser:** double-click **`run.cmd`** → opens <http://127.0.0.1:8765>.

Pick your sources, hit **Generate**, download the zip.

## Install a chart

Unzip the downloaded `Artist - Title.zip` into your DTXMania songs folder
(e.g. `DTXManiaNX\...\Songs\`). Launch DTXMania → it rescans → play. 🎶

---

## How the pieces work

- **Notation** - Songsterr's note data → true-meter, 1/64-quantized DTX (phantom AI-tab notes merged
  so the chart stays tempo-locked).
- **Audio** - YouTube via yt-dlp (tiered: anonymous → your browser's YouTube session → friendly
  fallback) or a file you upload. A bundled `deno` solves YouTube's JS challenge.
- **Auto-sync** - cross-correlates your audio against the tab-synced master to find the exact offset,
  then trims to align. Tempo is trusted from the tab (same song = same tempo).
- **Foot technique** - adds left-foot hi-hat/double-bass notes on lane 1B with correct samples.
- **Playability** - flags any foot/hand asked to move faster than humanly possible, and relaxes it.
- **Package** - Shift-JIS `.dtx` + BGM + a synthesized drum kit, zipped.

## YouTube & usability

Most users download **anonymously, no login**. If YouTube bot-blocks the network, DTX Forge
automatically borrows your browser's existing YouTube session (Firefox/Chrome/Edge/Brave) - you never
log into DTX Forge itself. If everything is blocked, **Upload file** always works.

## Sources it can read

The URL box (and file upload) auto-detect the source - you don't pick a type:

| Source | How |
|--------|-----|
| **Songsterr** | Paste any tab link or the numeric id. Structured note data → exact chart. |
| **Guitar Pro** | `.gp` / `.gp3` / `.gp4` / `.gp5` / `.gpx` - URL or file. Percussion track → GM drums. |
| **MIDI** | `.mid` / `.midi` with a GM drum track (channel 10). |
| **ASCII drum tab** | Paste text like `HH|x-x-x-x-|` (Ultimate-Guitar style), or a `.txt`/URL. |
| **Audio only** *(beta)* | No tab at all - onset detection + frequency classification. |

The dividing line isn't the website - it's whether the source has **machine-readable notes** vs. a
picture of notes. Photos/PDFs of sheet music aren't supported (that needs optical music recognition).

## Notes & limits

- Songsterr tabs are often **AI-generated** - a strong approximation, not a hand-verified chart.
- **Audio-only** transcription (no tab) is beta: onset detection + frequency-band classification.
- Auto-sync assumes the upload is the same tempo as the song; disable it for nightcore/sped-up rips.

## Layout

```
dtx-forge/
  app.py  desktop.py           server + native window
  DTX Forge.cmd  run.cmd  setup.cmd
  dtxforge/
    songsterr.py  audio.py  autosync.py   fetch, download, align
    transcribe.py  dtx.py  humanize.py     notes, emit, foot technique
    playability.py  notes.py  report.py    checks, helpers, stage events
    drumkit.py  pipeline.py                samples, orchestration
  web/index.html                           UI (themes, picker, visualizer)
  assets/drumkit/  assets/bin/deno.exe     samples + JS runtime
  jobs/                                    per-run work + output zips
```
