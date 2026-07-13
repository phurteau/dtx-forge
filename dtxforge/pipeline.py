"""End-to-end pipeline orchestration. Each run streams progress + stage events."""
import os, re, copy, traceback
from . import (songsterr, audio, transcribe, drumkit, dtx, humanize, playability,
               notes, autosync, sources, faithfulness as faith)

def normalize_dlevel(text, default="50"):
    """Accept '0-99' (tens scale, 50->5.00) or '0.00-9.99' (literal). Emit the
    DTXManiaNX hundredths integer that displays that difficulty (5.55 -> 555)."""
    s = str(text).strip() or str(default)
    try:
        if "." in s:
            d = float(s)                 # 0.00-9.99
        else:
            iv = int(s)
            d = iv / 10.0 if 0 <= iv <= 99 else iv / 100.0
    except ValueError:
        d = 5.0
    d = max(0.0, min(9.99, d))
    return int(round(d * 100))           # hundredths; DTXManiaNX shows d


def _slug(s):
    s = re.sub(r'[<>:"/\\|?*]+', "", s or "").strip()
    return re.sub(r"\s+", " ", s) or "chart"

def run(opts, workdir, assets_dir, progress):
    """
    opts keys:
      tab_source: 'songsterr' | 'midi' | 'audio'
      songsterr_query / songsterr_url  (for songsterr)
      midi_path                         (for midi)
      audio_source: 'songsterr' | 'youtube' | 'upload' | 'none'
      youtube_url, upload_audio_path
      remove_drums: bool  (option C)
      title, artist, bpm(optional), dlevel
    Returns dict(folder, zip, stats).
    """
    os.makedirs(workdir, exist_ok=True)
    kit_dir = os.path.join(assets_dir, "drumkit")
    kit_files = drumkit.ensure_kit(kit_dir)

    # stage/log shims (progress may be a Reporter or a plain callable)
    def stg(sid, msg=None):
        if hasattr(progress, "stage"): progress.stage(sid, msg)
        elif msg: progress(msg)
    def skp(sid):
        if hasattr(progress, "skip"): progress.skip(sid)
    def log(msg):
        progress(msg)

    title = opts.get("title") or "Untitled"
    artist = opts.get("artist") or "Unknown"
    bpm = opts.get("bpm")
    m = None

    asrc = opts.get("audio_source", "none")
    drum_mode = opts.get("drum_mode", "keep")           # keep = full song (default)
    auto_sync = bool(opts.get("auto_sync", True)) and asrc in ("youtube", "upload")
    need_stem = (drum_mode in ("remove", "quiet")) or (opts["tab_source"] == "audio")

    # ---------- 1. NOTATION ----------
    stg("notation", "Resolving notation source...")
    if opts["tab_source"] in ("songsterr", "url", "auto"):
        # smart-detect: Songsterr / Guitar Pro / MIDI / ASCII from URL or uploaded file
        kind, payload = sources.detect(url_or_id=opts.get("songsterr_url", ""),
                                       file_path=opts.get("tab_file_path", ""),
                                       workdir=workdir)
        log(f"Detected source: {kind}.")
        if kind == "songsterr":
            sid = payload
            m = songsterr.meta(sid)
            _t = re.sub(r"\s+drum\s*tab\s*$", "", m.get("title", title), flags=re.I).strip()
            title = opts.get("title") or _t
            artist = opts.get("artist") or m.get("artist", artist)
            trk = songsterr.fetch_drum_notation(m)
            events, barlens = transcribe.from_songsterr(trk["measures"])
            if not bpm:
                tt = (trk.get("automations") or {}).get("tempo")
                bpm = (tt[0]["bpm"] if tt else 120)
        elif kind == "guitarpro":
            events, barlens, bpm2 = transcribe.from_guitarpro(payload)
            bpm = bpm or bpm2
        elif kind == "midi":
            events, barlens, bpm2 = transcribe.from_midi(payload)
            bpm = bpm or bpm2
        elif kind == "ascii":
            events, barlens, bpm2 = transcribe.from_ascii_tab(payload, bpm=bpm or 120)
            bpm = bpm or bpm2
        else:
            raise RuntimeError(f"Unsupported source kind: {kind}")
        log(f"Transcribed {dtx.count_chips(events)} notes across {len(events)} bars.")
    elif opts["tab_source"] == "midi":
        log("Parsing MIDI drum track...")
        events, barlens, bpm2 = transcribe.from_midi(opts["midi_path"])
        bpm = bpm or bpm2
    elif opts["tab_source"] == "audio":
        events = barlens = None                         # produced later from audio
    else:
        raise ValueError("bad tab_source")

    # ---------- 2. AUDIO ----------
    raw_audio = None
    if asrc == "none":
        skp("audio")
    else:
        stg("audio")
        if asrc == "songsterr":
            if not m:
                m = songsterr.meta(songsterr.parse_song_id(opts.get("songsterr_url") or ""))
            log("Downloading tab-synced audio from Songsterr...")
            raw_audio = os.path.join(workdir, "src.opus")
            songsterr.download_synced_audio(m, raw_audio)
        elif asrc == "youtube":
            log("Downloading audio from YouTube...")
            raw_audio = audio.youtube_download(opts["youtube_url"], os.path.join(workdir, "src"), progress=log)
        elif asrc == "upload":
            raw_audio = opts["upload_audio_path"]
            log("Using uploaded audio file.")

    full_wav = None
    drum_stem = None
    if raw_audio:
        full_wav = os.path.join(workdir, "fullmix.wav")
        log("Decoding audio...")
        audio.to_wav(raw_audio, full_wav)

    # ---------- 3. DRUM SEPARATION ----------
    if raw_audio and need_stem:
        stg("separate", "Separating drums (Demucs)...")
        _, drum_stem = audio.demucs_remove_drums(full_wav, os.path.join(workdir, "demucs"), log)
    else:
        skp("separate")

    # ---------- 3b. AUDIO-ONLY TRANSCRIBE ----------
    if opts["tab_source"] == "audio":
        stg("notation", "Transcribing drums from audio (beta)...")
        events, barlens, bpm2, _ = transcribe.from_audio_drums(drum_stem, bpm=bpm, progress=log)
        bpm = bpm or bpm2

    if events is None:
        raise RuntimeError("No notation was produced.")
    if not bpm:
        bpm = 120

    # snapshot the faithful transcription - the baseline for the faithfulness score
    original_events = copy.deepcopy(events)

    # ---------- 4. AUTO-SYNC (align external audio to the chart) ----------
    if raw_audio and auto_sync and opts["tab_source"] != "audio":
        stg("align")
        alpha = beta = None
        # Preferred: align to the tab-synced Songsterr master (same recording -> robust)
        ref_wav = None
        if m is not None:
            try:
                ref_opus = os.path.join(workdir, "ref.opus")
                songsterr.download_synced_audio(m, ref_opus)
                ref_wav = os.path.join(workdir, "ref.wav")
                audio.to_wav(ref_opus, ref_wav)
            except Exception as e:
                log(f"Auto-sync reference unavailable ({str(e)[:60]}); using chart notes.")
        if ref_wav:
            alpha, beta = autosync.align_audio_to_reference(full_wav, ref_wav, progress=log)
        elif drum_stem:
            note_times = [notes.abs_time(n["m"], n["pos"], barlens, bpm) for n in notes.flatten(events)]
            alpha, beta = autosync.align_audio_to_chart(drum_stem, note_times,
                                                        notes.bar_starts(barlens, bpm)[-1], progress=log)
        else:
            log("Auto-sync: no reference or drum stem; skipping alignment.")
        if alpha is not None and (abs(alpha - 1) > 1e-4 or abs(beta) > 0.01):
            full_aln = os.path.join(workdir, "full_aligned.wav")
            autosync.apply_alignment(full_wav, full_aln, alpha, beta)
            full_wav = full_aln
            if drum_stem:
                dr_aln = os.path.join(workdir, "drums_aligned.wav")
                autosync.apply_alignment(drum_stem, dr_aln, alpha, beta)
                drum_stem = dr_aln
            log("Audio aligned to chart timeline.")
    else:
        skp("align")

    # ---------- 4b. BUILD BGM (per drum mode) ----------
    bgm_file = None
    if raw_audio:
        if drum_mode == "keep" or not drum_stem:
            bgm_wav = full_wav
        else:
            k = 0.90 if drum_mode == "remove" else 0.55
            bgm_wav = audio.build_bgm(full_wav, drum_stem, os.path.join(workdir, "bgm_ducked.wav"), k)
        bgm_file = os.path.join(workdir, "bgm.ogg")
        log("Encoding BGM...")
        audio.to_ogg(bgm_wav, bgm_file)

    # ---------- 5. HUMANIZE ----------
    hh_lvl = opts.get("hihat_foot", "off")
    db_on = bool(opts.get("double_bass", False))
    db_converted = 0
    if hh_lvl != "off" or db_on:
        stg("humanize", f"Advanced technique (hi-hat foot: {hh_lvl}, double bass: {'on' if db_on else 'off'})...")
        events, db_converted = humanize.humanize(events, barlens, bpm, hihat_level=hh_lvl, doublebass=db_on)
        if db_on:
            log(f"Double kick: converted {db_converted} too-fast kicks to left-foot.")
    else:
        skp("humanize")

    # ---------- 6. PLAYABILITY ----------
    stg("playability", "Checking human playability...")
    rep = playability.analyze(events, barlens, bpm)
    log(f"Playability: {rep['verdict']} (score {rep['score']}/100, {rep['issue_count']} tight spots).")
    play_report = rep
    if rep["issue_count"] > 0 and opts.get("auto_relax", True):
        log("Auto-relaxing hard passages...")
        events, relax = playability.auto_relax(events, barlens, bpm, allow_doublebass=db_on)
        play_report = relax["after"]
        log(f"After relax: {play_report['verdict']} (score {play_report['score']}/100, {play_report['issue_count']} tight spots).")

    # ---------- 6b. FAITHFULNESS (vs the original tab) ----------
    fscore = faith.compare(original_events, events)
    log(faith.summary_line(fscore))

    # ---------- 7. PACKAGE ----------
    stg("package", "Building DTX chart...")
    if bgm_file is None:
        import wave
        silent_wav = os.path.join(workdir, "silence.wav")
        with wave.open(silent_wav, "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
            w.writeframes(b"\x00\x00" * 44100)
        bgm_file = os.path.join(workdir, "bgm.ogg")
        audio.to_ogg(silent_wav, bgm_file)

    meta = dict(title=title, artist=artist, bpm=round(float(bpm), 3),
                dlevel=normalize_dlevel(opts.get("dlevel", "50")),
                comment=(f"Charted by {opts['author']}. " if opts.get("author") else "")
                        + f"Generated by DTX Forge. Source: {opts['tab_source']}.",
                bgm=os.path.basename(bgm_file))
    dtx_text = dtx.emit_dtx(events, barlens, meta)

    song_name = f"{_slug(artist)} - {_slug(title)}"
    folder, zpath = dtx.package(os.path.join(workdir, "dist"), song_name, dtx_text, bgm_file, kit_dir, kit_files)
    if hasattr(progress, "finish"): progress.finish()
    stats = dict(measures=len(events), chips=dtx.count_chips(events), bpm=meta["bpm"],
                 drum_mode=drum_mode if raw_audio else "none",
                 removed_drums=bool(raw_audio and drum_mode != "keep"),
                 hihat_foot=hh_lvl, double_bass=("on" if db_on else "off"),
                 double_kicks=db_converted,
                 playability=play_report["verdict"], play_score=play_report["score"],
                 play_issues=play_report["issue_count"],
                 faithfulness=fscore["percent"], notes_moved=fscore["moved"],
                 notes_dropped=fscore["dropped"], notes_added=fscore["added"],
                 source=opts["tab_source"], title=title, artist=artist)
    log("Done.")
    return dict(folder=folder, zip=zpath, stats=stats, playability=play_report, faithfulness=fscore)
