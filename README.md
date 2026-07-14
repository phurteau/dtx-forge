# 🥁 DTX Forge

Turn a drum tab (or just audio) into a fully playable **DTXMania** chart - **no manual notation**.
It fetches the tab, grabs the song, auto-syncs the audio, applies realistic foot technique,
verifies a human can actually play it, and packages a ready-to-drop `.dtx` zip.

Built from a pipeline verified to place ~99% of charted notes within ±10–20 ms of the real recording.

![DTX Forge](docs/screenshot.png)

---

## Highlights

- **Notation optional - audio is enough.** Paste a **Songsterr** URL, a **Guitar Pro** / **MIDI** URL,
  an **ASCII drum tab**, or a file - or **leave notation blank** and DTX Forge transcribes the drums
  straight from the audio into a **full kit** (kick, snare, toms, open/closed hi-hat, ride, crash).
- **Real audio from almost anywhere.** Paste a link from **YouTube, SoundCloud, Bandcamp, Vimeo** and
  1000+ sites, a **direct audio-file URL**, or upload a file. DTX Forge auto-syncs it to the chart.
- **Full song by default.** Keep the complete track, quiet the drums, or fully remove them (arcade feel).
- **Difficulty tiers.** Pick a level - **Basic / Advanced / Extreme / Master** - or let **Auto** derive it
  from a 0.00–9.99 score rated against a skilled-player reference. The output `.dtx` is named by tier
  (`bsc` / `adv` / `ext` / `mstr`), the DTXMania / GITADORA convention.
- **Advanced foot technique.** Optional left-foot hi-hat on the **2 & 4 backbeat**, plus **DKDK** double-bass
  that converts only the kicks too fast to play one-legged.
- **Human-playability check.** Every chart is verified against a 2-hands + 2-feet model and
  auto-relaxed if a passage is physically impossible.
- **Faithfulness score.** When charting from a tab, each chart reports how true it is to the tab -
  **100% = untouched** - and shows exactly what changed (notes moved to the left foot, dropped, or added).
- **Live pipeline visualizer.** Watch each stage light up as it runs.
- **Personalize it.** Light/dark themes + an accent color picker (remembered between runs).

---

## Install - pick ONE

There are two independent ways to run DTX Forge. You don't need both.

### Option A - Standalone app (no Python)
1. Download **`DTX-Forge-EXE.zip`** from the [Releases](../../releases) page and unzip it.
2. Double-click **`DTX Forge.exe`**. That's it.

### Option B - From source (Python)
1. Install **Python 3.10+** - use the installer from <https://www.python.org/downloads/> and
   tick *Add Python to PATH*. (The Microsoft Store build works too, but only exposes `python`,
   not `pythonw`; the launcher handles that automatically.)
2. Double-click **`setup.cmd`** - installs dependencies and offers Demucs (needed for audio-only
   transcription and the *Quiet* / *Remove* drum modes, ~2 GB).
3. Run it:
   - **App window:** double-click **`DTX Forge.cmd`**, or
   - **Browser:** double-click **`run.cmd`** → opens <http://127.0.0.1:8765>.

Full-kit separation models (~160 MB + ~515 MB) download automatically the first time you
transcribe from audio with no tab (both options).

## Using it

Fill in **Title** and **Artist** (both required), pick your sources, hit **Generate**, download the zip.

## Install a chart

Unzip the downloaded `Artist - Title.zip` into your DTXMania songs folder
(e.g. `DTXManiaNX\...\Songs\`). Launch DTXMania → it rescans → play. 🎶

---

## How the pieces work

- **Notation** - Songsterr / Guitar Pro / MIDI / ASCII → true-meter, 1/64-quantized DTX (odd-meter
  overflow notes merged so the chart stays tempo-locked). Or, with no tab, the drums are transcribed
  from the audio (see below).
- **Audio** - any yt-dlp-supported link (YouTube, SoundCloud, Bandcamp, Vimeo, 1000+ sites), a direct
  audio-file URL, or a file you upload. A bundled `deno` solves the JS challenge for sites (e.g. YouTube)
  that need it.
- **Auto-sync** - cross-correlates your audio against the tab-synced master to find the exact offset,
  then trims to align. Tempo is trusted from the tab (same song = same tempo).
- **Full kit (audio-only)** - separates the drum stem into individual pieces and onset-detects each, so
  toms and ride are recovered - not just kick/snare/hat.
- **Foot technique** - optional left-foot hi-hat on 2 & 4 and DKDK double-bass, written to lane 1B with
  the correct samples.
- **Difficulty** - choose a tier (Basic / Advanced / Extreme / Master) or let **Auto** map it from a
  0.00–9.99 score (note density, peak bursts, limb speed, kit variety), referenced to a player with some
  drum skill. Tier boundaries: Basic < 3.00 · Advanced 3.00–5.99 · Extreme 6.00–8.49 · Master ≥ 8.50.
  The chart file is named by tier (`bsc.dtx` / `adv.dtx` / `ext.dtx` / `mstr.dtx`) in its `set.def` slot.
- **Playability** - flags any foot/hand asked to move faster than humanly possible, and relaxes it.
- **Package** - Shift-JIS `.dtx` + BGM + a synthesized drum kit, zipped.

## Audio downloads & usability

Most links download **anonymously, no login**. If a site bot-blocks the network (e.g. YouTube), DTX Forge
automatically borrows your browser's existing session for that site (Firefox/Chrome/Edge/Brave) - you
never log into DTX Forge itself. If everything is blocked, **Upload file** always works.

## Sources it can read

The URL box (and file upload) auto-detect the source - you don't pick a type:

| Source | How |
|--------|-----|
| **Songsterr** | Paste any tab link or the numeric id. Structured note data → exact chart. |
| **Guitar Pro** | `.gp` / `.gp3` / `.gp4` / `.gp5` / `.gpx` - URL or file. Percussion track → GM drums. |
| **MIDI** | `.mid` / `.midi` with a GM drum track (channel 10). |
| **ASCII drum tab** | Paste text like `HH|x-x-x-x-|` (Ultimate-Guitar style), or a `.txt`/URL. |
| **Audio only** *(beta)* | No tab at all - the drum track is separated into pieces and transcribed. Fully automatic. |

The dividing line isn't the website - it's whether the source has **machine-readable notes** vs. a
picture of notes. Photos/PDFs of sheet music aren't supported (that needs optical music recognition).

### Audio-only drum detection *(automatic, when notation is blank)*

DTX Forge runs two complementary separation models and fuses their strengths - there's **no engine to
pick**:

| Piece | Recovered by |
| --- | --- |
| kick, snare, toms (high / low-mid / floor) | drum-body separation |
| open & closed hi-hat, ride, crash | hat / cymbal separation |

Models download once to `%LOCALAPPDATA%/DTXForge` and are **not** bundled; if they can't be fetched, a
fast built-in kick/snare/hat detector covers the basics. Toms are pitch-split into high/low-mid/floor and
cymbals into crash/ride. See `LICENSE` for model attributions (one model's weights are CC BY-NC).

## Notes & limits

- Songsterr tabs are often **auto-generated** - a strong approximation, not a hand-verified chart.
- **Audio-only** transcription (no tab) is beta: the drum stem is separated into pieces, then each is
  onset-detected. Tempo detection on raw audio can pick the wrong octave - set BPM manually if it looks
  doubled/halved (note placement still follows the audio either way).
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
    difficulty.py  faithfulness.py         auto-rating, tab fidelity
    fullkit.py  larsnet_engine.py          audio-only full-kit separation
    vendor/larsnet_unet.py                 vendored model architecture
    drumkit.py  pipeline.py                samples, orchestration
  web/index.html                           UI (themes, picker, visualizer)
  assets/drumkit/  assets/bin/deno.exe     samples + JS runtime
  jobs/                                    per-run work + output zips
```
