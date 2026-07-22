# DTXScribe Roadmap

What's shipped, what's in active development, and what's planned. This is a living document
and dates/scope may change.

## In active development

### Record mode - play your own charts on an electronic drum kit

The next major feature. Instead of transcribing a chart from audio or a tab, you connect your
electronic drum module, play, and DTXScribe turns your performance straight into a playable
DTXMania chart - then opens it in the editor for cleanup.

**Two ways to record:**

- **Freeplay (default)** - no audio needed. Pick a tempo and a time signature, play to a
  metronome, and hit Stop. Your chart is built from what you played. Nothing to upload,
  nothing to download until you're happy with it.
- **Play-along** - record over an uploaded song. DTXScribe detects the tempo, lets you confirm
  the click lines up with the music, and the song becomes the backing track of your chart.

**How it works:**

1. Pick your input device. The kit is detected even if you turn it on *after* opening the app -
   no restart needed.
2. Set the tempo and time signature (4/4, 3/4, 6/8, 5/4, 7/8, and more). For play-along the
   tempo is detected for you.
3. Optional one-time latency calibration so your hits line up precisely.
4. Press Start, play through the count-in, and record. Your hits print in real time on the lane
   view.
5. Press Stop - your take opens in the editor, ready to tidy up and export.

**Works with your kit.** The core of every mainstream module (kick, snare, toms, hi-hat, crash,
ride) works out of the box over standard MIDI - Yamaha DTX, Roland TD, Alesis, and others.
A quick guided "learn your kit" step captures anything non-standard, so any MIDI drum module is
supported, and your kit profile is saved so you only do it once.

This feature is being tested rigorously before release.

## Recently shipped

### v1.9.0
- Full-length songs in the chart - the complete intro and outro are kept, not trimmed.
- More reliable YouTube downloads.
- New app icon and a full uninstaller.

### v1.8.0
- Rearrange the editor lanes into your preferred order, with a smooth drag animation.
- Lane grouping (Full / Standard / Custom) to fold voices the way a DTXMania kit reads them.
- Full-length playback in the editor, including the outro.

### v1.7.0
- The app was renamed from DTX Forge to DTXScribe.

See [CHANGELOG.md](CHANGELOG.md) for the full history.

## Under consideration

- A pickable drum sample pack for recorded charts, so the kit can sound closer to a real kit.
- Capturing dynamics (accents and ghost notes) from your playing.
- Smarter automatic clean-up of repeated patterns.

Feedback and testing are welcome - open an issue with what you'd like to see.
