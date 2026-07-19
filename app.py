"""DTX Forge web app: FastAPI backend + background job runner."""
import os, sys, uuid, threading, traceback, shutil, re, json, subprocess, webbrowser, urllib.request


def _downloads_dir():
    """Resolve the user's real Downloads folder. Honors a relocated Downloads via the
    Windows known-folder registry entry, falling back to ~/Downloads (created if absent)."""
    path = None
    if os.name == "nt":
        try:
            import winreg
            key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            guid = "{374DE290-123F-4565-9164-39C4925E467B}"      # Downloads known folder
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                raw, _ = winreg.QueryValueEx(k, guid)
            path = os.path.expandvars(raw)
        except Exception:
            path = None
    if not path:
        path = os.path.join(os.path.expanduser("~"), "Downloads")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        path = os.path.expanduser("~")
    return path


def _unique_in(folder, filename):
    """A non-clobbering path in `folder`: 'name.zip', then 'name (2).zip', '(3)'..."""
    base, ext = os.path.splitext(filename)
    dst = os.path.join(folder, filename)
    n = 2
    while os.path.exists(dst):
        dst = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return dst


# make a bundled deno (for YouTube JS challenges) discoverable on PATH
def _bootstrap_path():
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [os.path.join(here, "assets", "bin"),
             os.path.join(getattr(sys, "_MEIPASS", here), "assets", "bin"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "deno")]
    extra = [c for c in cands if c and os.path.isdir(c)]
    if extra:
        os.environ["PATH"] = os.pathsep.join(extra + [os.environ.get("PATH", "")])
_bootstrap_path()

from fastapi import FastAPI, UploadFile, File, Form, Body
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from dtxforge import pipeline, songsterr
from dtxforge.report import Reporter
from dtxforge import __version__ as APP_VERSION

GITHUB_REPO = "phurteau/dtx-forge"
_updl = {}   # download id -> {status, received, total, name, saved, error}


def _ver_tuple(s):
    """'v1.5.2' / '1.5.2' -> (1, 5, 2); trailing non-numeric parts ignored."""
    nums = re.findall(r"\d+", s or "")
    return tuple(int(n) for n in nums[:3]) if nums else (0,)


def _latest_release(timeout=6):
    """Fetch the latest GitHub release JSON (public repo, no auth). Raises on failure."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    req = urllib.request.Request(url, headers={
        "User-Agent": "DTX-Forge-Updater",
        "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _pick_exe_asset(rel):
    """The standalone-exe zip asset from a release (name ends '-EXE.zip'); None if absent."""
    assets = rel.get("assets", []) or []
    for a in assets:
        if (a.get("name") or "").lower().endswith("-exe.zip"):
            return a
    for a in assets:                                   # fallback: any zip that isn't the source app
        n = (a.get("name") or "").lower()
        if n.endswith(".zip") and "app" not in n:
            return a
    return None


def _reveal(path):
    """Select the file in Explorer (Windows). Best-effort; never raises."""
    try:
        if os.name == "nt" and path and os.path.exists(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
JOBS = os.path.join(HERE, "jobs")
ASSETS = os.path.join(HERE, "assets")
os.makedirs(JOBS, exist_ok=True)

app = FastAPI(title="DTX Forge")
_jobs = {}   # id -> {status, reporter, result, error}


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/pads/{name}")
def pad_icon(name: str):
    """Serve the DTXMania lane pad icons (web/pads/*.png)."""
    if "/" in name or "\\" in name or ".." in name or not name.lower().endswith(".png"):
        return JSONResponse({"error": "bad name"}, status_code=400)
    p = os.path.join(WEB, "pads", name)
    if not os.path.isfile(p):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(p, media_type="image/png")


@app.get("/api/kit/{name}")
def kit_sample(name: str):
    """Serve a drum-kit one-shot WAV (assets/drumkit/*.wav) so the editor can preview the
    charted drum chips as the playhead crosses them - the same samples the packaged chart uses."""
    if "/" in name or "\\" in name or ".." in name or not name.lower().endswith(".wav"):
        return JSONResponse({"error": "bad name"}, status_code=400)
    p = os.path.join(ASSETS, "drumkit", name)
    if not os.path.isfile(p):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(p, media_type="audio/wav")


@app.get("/api/kit/{job_id}/{name}")
def kit_sample_job(job_id: str, name: str):
    """Serve the drum one-shot for a specific job - the real per-song sliced samples
    (generated charts) or an imported chart's own bundled kit - falling back to the built-in
    synth sample for any lane without a custom one. This is why the editor's Drum Sounds
    preview matches the packaged chart instead of always playing the generic synth kit."""
    if "/" in name or "\\" in name or ".." in name or not name.lower().endswith(".wav"):
        return JSONResponse({"error": "bad name"}, status_code=400)
    job = _jobs.get(job_id)
    if job and job.get("result"):
        kd = (job["result"].get("repack") or {}).get("kit_dir")
        if kd and os.path.isfile(os.path.join(kd, name)):
            return FileResponse(os.path.join(kd, name), media_type="audio/wav")
    p = os.path.join(ASSETS, "drumkit", name)
    if not os.path.isfile(p):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(p, media_type="audio/wav")


@app.get("/api/search")
def api_search(q: str):
    try:
        return {"results": songsterr.search(q, size=12)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def _run_job(job_id, opts, upload_paths):
    job = _jobs[job_id]
    rep = job["reporter"]
    try:
        opts.update(upload_paths)
        res = pipeline.run(opts, workdir=os.path.join(JOBS, job_id),
                           assets_dir=ASSETS, progress=rep)
        job["result"] = res
        job["status"] = "done"
    except pipeline.Cancelled:
        job["status"] = "cancelled"
        rep.log("Generation stopped.")
    except Exception as e:
        job["error"] = str(e)
        job["trace"] = traceback.format_exc()
        job["status"] = "error"
        rep.error()
        rep.log("ERROR: " + str(e))


@app.post("/api/generate")
async def api_generate(
    tab_source: str = Form(...),
    songsterr_query: str = Form(""),
    songsterr_url: str = Form(""),
    audio_source: str = Form("url"),
    audio_url: str = Form(""),
    drum_mode: str = Form("keep"),
    auto_sync: str = Form("true"),
    standardize: str = Form("true"),
    style: str = Form(""),
    notes_style: str = Form("transcribed"),
    group_cymbals: str = Form("true"),
    openhat_lp: str = Form("false"),
    hihat_foot: str = Form("off"),
    double_bass: str = Form("false"),
    title: str = Form(""),
    artist: str = Form(""),
    author: str = Form(""),
    bpm: str = Form(""),
    dlevel: str = Form(""),
    dlevel_tier: str = Form("auto"),
    midi_file: UploadFile = File(None),
    tab_file: UploadFile = File(None),
    audio_file: UploadFile = File(None),
    image_file: UploadFile = File(None),
):
    job_id = uuid.uuid4().hex[:12]
    wd = os.path.join(JOBS, job_id)
    os.makedirs(wd, exist_ok=True)
    upload_paths = {}
    # a generic tab upload (gp/gp5/gpx/mid/txt) - routed by content
    up = tab_file if (tab_file is not None) else midi_file
    if up is not None:
        name = up.filename or "tab"
        ext = os.path.splitext(name)[1].lower() or ".mid"
        p = os.path.join(wd, "tab" + ext)
        with open(p, "wb") as f:
            shutil.copyfileobj(up.file, f)
        upload_paths["tab_file_path"] = p
        upload_paths["midi_path"] = p       # back-compat for tab_source='midi'
    if audio_file is not None:
        ext = os.path.splitext(audio_file.filename or "audio")[1] or ".mp3"
        p = os.path.join(wd, "upload" + ext)
        with open(p, "wb") as f:
            shutil.copyfileobj(audio_file.file, f)
        upload_paths["upload_audio_path"] = p
    if image_file is not None:
        ext = os.path.splitext(image_file.filename or "jacket.png")[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".bmp", ".gif"):
            ext = ".png"
        p = os.path.join(wd, "jacket" + ext)
        with open(p, "wb") as f:
            shutil.copyfileobj(image_file.file, f)
        upload_paths["jacket_path"] = p

    opts = dict(
        tab_source=tab_source,
        songsterr_query=songsterr_query.strip(),
        songsterr_url=songsterr_url.strip(),
        audio_source=audio_source,
        audio_url=audio_url.strip(),
        drum_mode=(drum_mode.strip() or "keep"),
        auto_sync=(auto_sync.lower() == "true"),
        standardize=(standardize.lower() != "false"),
        style=(style.strip().lower() or None),
        notes_style=(notes_style.strip().lower() or "transcribed"),
        group_cymbals=(group_cymbals.lower() != "false"),
        openhat_lp=(openhat_lp.lower() == "true"),
        hihat_foot=(hihat_foot.strip() or "off"),
        double_bass=(double_bass.lower() == "true"),
        title=title.strip(), artist=artist.strip(), author=author.strip(),
        bpm=(float(bpm) if bpm.strip() else None),
        dlevel=dlevel.strip(),
        dlevel_tier=(dlevel_tier.strip() or "auto"),
        defer_package=True,   # edit first, package once on download
    )
    _jobs[job_id] = {"status": "running", "reporter": Reporter(), "result": None, "error": None}
    threading.Thread(target=_run_job, args=(job_id, opts, upload_paths), daemon=True).start()
    return {"job_id": job_id}


def _import_custom_kit(wd, src_folder, meta):
    """If an imported chart bundles its own drum one-shots, build a job-local kit dir that
    overrides the built-in synth samples lane-by-lane, so the editor preview AND the
    re-packaged chart use the source's real drum sounds. Falls back to the built-in kit for
    any lane without a usable source sample. Returns (kit_dir, kit_files, sampled_lanes)."""
    from dtxforge import dtx, drumkit, audio as _audio
    builtin = os.path.join(ASSETS, "drumkit")
    kit_files = drumkit.ensure_kit(builtin)             # {label: 'label.wav'}
    wav_defs = meta.get("wav_defs") or {}
    lane_slot = meta.get("lane_slot") or {}
    if not src_folder or not wav_defs or not lane_slot:
        return builtin, kit_files, []
    disk = {}                                           # case-insensitive filename -> path
    for root, _d, files in os.walk(src_folder):
        for fn in files:
            disk.setdefault(fn.lower(), os.path.join(root, fn))
    job_kit = os.path.join(wd, "kit")
    os.makedirs(job_kit, exist_ok=True)
    for lab, fn in kit_files.items():                   # seed with the built-in kit
        try:
            shutil.copy2(os.path.join(builtin, fn), os.path.join(job_kit, fn))
        except OSError:
            pass
    sampled = []
    for lane, slot in lane_slot.items():                # override lanes that ship a real sample
        lab = dtx.LANE_LABEL.get(lane)
        src_name = wav_defs.get(str(slot).upper())
        if not lab or not src_name:
            continue
        src = disk.get(os.path.basename(src_name).lower())
        if not src or not os.path.isfile(src):
            continue
        dst = os.path.join(job_kit, lab + ".wav")
        try:
            if src.lower().endswith(".wav"):
                shutil.copy2(src, dst)
            else:
                _audio.to_wav(src, dst)
            sampled.append(lane)
        except Exception:
            try:
                _audio.to_wav(src, dst)
                sampled.append(lane)
            except Exception:
                pass
    if not sampled:
        return builtin, kit_files, []
    return job_kit, kit_files, sorted(set(sampled))


def _build_import_result(wd, dtx_text, bgm_src=None, image_src=None, src_folder=None):
    """Turn a parsed .dtx into a _jobs result dict (chart + repack + stats) so the editor
    endpoints (/api/chart, /api/save, /api/package, /api/audio) work on an imported chart
    exactly as on a generated one. bgm_src: an audio file to play (zip import), or None for
    a silent (notes-only) import. src_folder: the extracted chart folder (zip import) whose
    bundled drum one-shots should override the built-in kit; None for a bare .dtx."""
    import wave
    from dtxforge import dtx, audio as _audio
    events, barlens, bpm, meta = dtx.parse_dtx(dtx_text)
    if not any(events):
        raise ValueError("No drum notes found - only standard DTX drum channels (11–1C) are read.")
    kit_dir, kit_files, sampled_lanes = _import_custom_kit(wd, src_folder, meta)
    # BGM: real audio from a zip, else a second of silence so the track object exists
    has_audio = False
    bgm_file = os.path.join(wd, "bgm.ogg")
    if bgm_src and os.path.exists(bgm_src):
        try:
            _audio.to_ogg(bgm_src, bgm_file); has_audio = True
        except Exception:
            has_audio = False
    if not has_audio:
        silent = os.path.join(wd, "silence.wav")
        with wave.open(silent, "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
            w.writeframes(b"\x00\x00" * 44100)
        try:
            _audio.to_ogg(silent, bgm_file)
        except Exception:
            bgm_file = silent
    meta["bgm"] = os.path.basename(bgm_file)
    if not image_src and meta.get("preimage"):
        meta.pop("preimage", None)                      # referenced a jacket we don't have
    tier_key = dtx.tier_from_score((meta.get("dlevel") or 50) / 100.0)
    dtx_name, tier_label, tier_slot = dtx.tier_info(tier_key)
    title = meta.get("title") or "Imported chart"
    artist = meta.get("artist") or ""
    song_name = (f"{pipeline._slug(artist)} - {pipeline._slug(title)}") if artist else pipeline._slug(title)
    repack = dict(out_dir=os.path.join(wd, "dist"), song_name=song_name,
                  bgm_file=bgm_file, kit_dir=kit_dir, kit_files=kit_files,
                  dtx_name=dtx_name, set_label=tier_label, set_slot=tier_slot,
                  image_file=image_src)
    chart = dict(events=events, barlens=barlens, bpm=float(meta["bpm"]), meta=meta,
                 has_audio=has_audio, review=dict(onsets=[]))
    stats = dict(measures=len(events), chips=dtx.count_chips(events), bpm=meta["bpm"],
                 drum_mode=("keep" if has_audio else "none"), removed_drums=False,
                 has_audio=has_audio, audio_source="import",
                 sampled_lanes=sampled_lanes, sampled_count=len(sampled_lanes),
                 playability="imported", play_score=100, play_issues=0,
                 faithfulness=100, notes_moved=0, notes_dropped=0, notes_added=0,
                 dlevel=(meta.get("dlevel") or 50) / 100.0, dlevel_auto=False,
                 dlevel_tier=tier_key, dtx_file=dtx_name, tier_manual=True,
                 source="import", title=title, artist=artist)
    return dict(folder=None, zip=None, stats=stats,
                playability={"verdict": "imported", "score": 100, "issue_count": 0},
                faithfulness={"percent": 100, "moved": 0, "dropped": 0, "added": 0},
                chart=chart, repack=repack)


@app.post("/api/import")
async def api_import(file: UploadFile = File(...)):
    """Import an existing chart for editing: a bare .dtx (notes only, silent playback) or a
    .zip / DTXMania folder archive (.dtx + its bgm + jacket -> full playback)."""
    job_id = uuid.uuid4().hex[:12]
    wd = os.path.join(JOBS, job_id)
    os.makedirs(wd, exist_ok=True)
    name = file.filename or "chart.dtx"
    ext = os.path.splitext(name)[1].lower()
    raw = os.path.join(wd, "upload" + (ext or ".dtx"))
    with open(raw, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        if ext == ".zip":
            import zipfile
            ex = os.path.join(wd, "src")
            os.makedirs(ex, exist_ok=True)
            with zipfile.ZipFile(raw) as z:
                z.extractall(ex)
            dtx_path = None
            for root, _dirs, files in os.walk(ex):
                for fn in files:
                    if fn.lower().endswith(".dtx"):
                        p = os.path.join(root, fn)
                        if dtx_path is None or os.path.getsize(p) > os.path.getsize(dtx_path):
                            dtx_path = p
            if not dtx_path:
                return JSONResponse({"error": "No .dtx file found inside the zip."}, status_code=400)
            with open(dtx_path, encoding="shift_jis", errors="replace") as fh:
                dtx_text = fh.read()
            folder = os.path.dirname(dtx_path)
            from dtxforge import dtx as _dtx
            _e, _b, _bpm, meta0 = _dtx.parse_dtx(dtx_text)
            kit = {"bd.wav", "sd.wav", "hh.wav", "ho.wav", "ht.wav", "lt.wav",
                   "ft.wav", "cy.wav", "rd.wav", "rb.wav", "lp.wav"}
            # BGM: prefer the file named by #WAV01, else any audio that isn't a kit one-shot
            bgm_src = None
            if meta0.get("bgm"):
                cand = os.path.join(folder, meta0["bgm"])
                if os.path.exists(cand):
                    bgm_src = cand
            if not bgm_src:
                for fn in sorted(os.listdir(folder)):
                    if fn.lower().endswith((".ogg", ".mp3", ".wav", ".m4a")) and fn.lower() not in kit:
                        bgm_src = os.path.join(folder, fn); break
            image_src = None
            if meta0.get("preimage"):
                cand = os.path.join(folder, meta0["preimage"])
                if os.path.exists(cand):
                    dst = os.path.join(wd, os.path.basename(meta0["preimage"]))
                    shutil.copyfile(cand, dst); image_src = dst
            result = _build_import_result(wd, dtx_text, bgm_src=bgm_src, image_src=image_src, src_folder=folder)
        else:
            with open(raw, encoding="shift_jis", errors="replace") as fh:
                dtx_text = fh.read()
            result = _build_import_result(wd, dtx_text)
        _jobs[job_id] = {"status": "done", "reporter": Reporter(), "result": result, "error": None}
        return {"job_id": job_id, "editable": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/job/{job_id}")
def api_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "unknown job"}, status_code=404)
    rep = job["reporter"]
    out = {"status": job["status"], "messages": rep.messages, "stages": rep.snapshot(), "data": rep.data}
    if job["status"] == "done":
        out["stats"] = job["result"]["stats"]
        out["editable"] = bool(job["result"].get("chart"))
        if job["result"].get("zip"):
            out["download"] = f"/api/download/{job_id}"     # only once packaged
    if job["status"] == "error":
        out["error"] = job["error"]
    return out


@app.get("/api/chart/{job_id}")
def api_chart(job_id: str):
    """Return the generated chart's note model for the editor."""
    job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        return JSONResponse({"error": "not ready"}, status_code=404)
    ch = job["result"].get("chart")
    if not ch:
        return JSONResponse({"error": "no chart model"}, status_code=404)
    from dtxforge import dtx
    out = dtx.chart_to_json(ch["events"], ch["barlens"], ch["bpm"], ch["meta"])
    out["hasAudio"] = bool(ch.get("has_audio"))
    out["review"] = ch.get("review") or {"onsets": []}
    return out


def _apply_edits(job, bars_json):
    """Rebuild the in-memory chart events/barlens from the editor's edited bar list."""
    from dtxforge import dtx
    ch = job["result"]["chart"]
    n_bars = len(ch["events"])
    events, barlens = dtx.events_from_json(bars_json, n_bars)
    ch["events"], ch["barlens"] = events, barlens
    job["result"]["stats"]["chips"] = dtx.count_chips(events)
    return dtx.count_chips(events)


@app.post("/api/save/{job_id}")
async def api_save(job_id: str, payload: dict = Body(...)):
    """Commit edited bars to the in-memory chart model (no zip yet -- packaging happens
    once on download, so editing never triggers a re-zip)."""
    job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        return JSONResponse({"error": "not ready"}, status_code=404)
    if not job["result"].get("chart"):
        return JSONResponse({"error": "chart not editable"}, status_code=400)
    try:
        chips = _apply_edits(job, payload.get("bars", []))
        return {"ok": True, "chips": chips}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/package/{job_id}")
async def api_package(job_id: str, payload: dict = Body(None)):
    """Package the current (possibly edited) chart into the .zip ONCE and return the
    download link. Optionally applies a final set of edits passed in the body first."""
    job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        return JSONResponse({"error": "not ready"}, status_code=404)
    res = job["result"]
    ch, rp = res.get("chart"), res.get("repack")
    if not ch or not rp:
        return JSONResponse({"error": "chart not packageable"}, status_code=400)
    from dtxforge import dtx
    try:
        if payload and payload.get("bars") is not None:
            _apply_edits(job, payload["bars"])
        dtx_text = dtx.emit_dtx(ch["events"], ch["barlens"], ch["meta"])
        folder, zpath = dtx.package(
            rp["out_dir"], rp["song_name"], dtx_text, rp["bgm_file"],
            rp["kit_dir"], rp["kit_files"], dtx_name=rp["dtx_name"],
            set_label=rp["set_label"], set_slot=rp["set_slot"],
            image_src=rp.get("image_file"))
        res["folder"], res["zip"] = folder, zpath
        # Save straight to the user's Downloads folder. The packaged exe's WebView2 host
        # doesn't wire up a browser download handler, so an <a download> click silently
        # fails; writing the file server-side (this IS the user's own machine) is reliable
        # in both the native window and the browser fallback.
        saved = None
        try:
            dl = _downloads_dir()
            dst = _unique_in(dl, os.path.basename(zpath))
            shutil.copyfile(zpath, dst)
            res["saved"] = saved = dst
        except Exception:
            saved = None
        out = {"ok": True, "chips": dtx.count_chips(ch["events"]),
               "download": f"/api/download/{job_id}"}
        if saved:
            out["saved"] = saved
            out["saved_name"] = os.path.basename(saved)
        return out
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/audio/{job_id}")
def api_audio(job_id: str):
    """Serve the chart-aligned backing track (bgm.ogg) so the editor can play the slice
    of the song under the bar being edited."""
    job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        return JSONResponse({"error": "not ready"}, status_code=404)
    rp = job["result"].get("repack") or {}
    bgm = rp.get("bgm_file")
    if not bgm or not os.path.exists(bgm):
        return JSONResponse({"error": "no audio"}, status_code=404)
    return FileResponse(bgm, media_type="audio/ogg")


@app.post("/api/cancel/{job_id}")
def api_cancel(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "unknown job"}, status_code=404)
    job["reporter"].request_cancel()
    return {"status": "cancelling"}


@app.get("/api/download/{job_id}")
def api_download(job_id: str):
    job = _jobs.get(job_id)
    if not job or job["status"] != "done" or not job["result"].get("zip"):
        return JSONResponse({"error": "not ready"}, status_code=404)
    z = job["result"]["zip"]
    return FileResponse(z, filename=os.path.basename(z), media_type="application/zip")


@app.get("/api/update-check")
def api_update_check():
    """Compare this build's version to the latest GitHub release. Never raises -- on any
    error/offline it returns update_available False, so the UI simply shows no banner."""
    try:
        rel = _latest_release()
        latest = rel.get("tag_name") or ""
        asset = _pick_exe_asset(rel)
        avail = _ver_tuple(latest) > _ver_tuple(APP_VERSION)
        return {"ok": True, "current": APP_VERSION, "latest": latest.lstrip("v"),
                "update_available": bool(avail and asset),
                "html_url": rel.get("html_url", ""),
                "asset": {"name": asset["name"], "size": asset.get("size", 0)} if asset else None}
    except Exception as e:
        return {"ok": False, "update_available": False, "error": str(e)}


def _run_update_download(dl_id, url, name):
    prog = _updl[dl_id]
    try:
        dst = _unique_in(_downloads_dir(), name)
        tmp = dst + ".part"
        req = urllib.request.Request(url, headers={"User-Agent": "DTX-Forge-Updater"})
        with urllib.request.urlopen(req, timeout=30) as r:
            prog["total"] = int(r.headers.get("Content-Length") or 0)
            got = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    prog["received"] = got
        os.replace(tmp, dst)
        prog["saved"] = dst
        prog["saved_name"] = os.path.basename(dst)
        prog["status"] = "done"
        _reveal(dst)
    except Exception as e:
        prog["status"] = "error"
        prog["error"] = str(e)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


@app.post("/api/update-download")
def api_update_download():
    """Download the latest release's standalone-exe zip straight into the user's Downloads
    folder (server-side, because the packaged WebView2 host has no browser download handler)."""
    try:
        asset = _pick_exe_asset(_latest_release())
        if not asset:
            return JSONResponse({"error": "no downloadable asset in the latest release"}, status_code=404)
        dl_id = uuid.uuid4().hex[:12]
        _updl[dl_id] = {"status": "downloading", "received": 0, "total": asset.get("size", 0),
                        "name": asset["name"], "saved": None, "error": None}
        threading.Thread(target=_run_update_download,
                         args=(dl_id, asset["browser_download_url"], asset["name"]),
                         daemon=True).start()
        return {"dl_id": dl_id, "name": asset["name"], "size": asset.get("size", 0)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/update-download/{dl_id}")
def api_update_download_status(dl_id: str):
    prog = _updl.get(dl_id)
    if not prog:
        return JSONResponse({"error": "unknown download"}, status_code=404)
    total, got = prog.get("total") or 0, prog.get("received") or 0
    out = {"status": prog["status"], "received": got, "total": total,
           "pct": int(got * 100 / total) if total else 0}
    if prog["status"] == "done":
        out["saved"], out["saved_name"] = prog.get("saved"), prog.get("saved_name")
    if prog["status"] == "error":
        out["error"] = prog.get("error")
    return out


@app.post("/api/open-external")
def api_open_external(payload: dict = Body(...)):
    """Open a link in the system browser, restricted to this GitHub repo so the native
    webview never navigates away from the app and no arbitrary URL can be opened."""
    url = (payload or {}).get("url", "")
    try:
        from urllib.parse import urlparse
        u = urlparse(url)
        if (u.scheme in ("http", "https")
                and u.netloc.lower() in ("github.com", "www.github.com")
                and u.path.lower().startswith("/phurteau/dtx-forge")):
            webbrowser.open(url)
            return {"ok": True}
        return JSONResponse({"error": "url not allowed"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    print("DTX Forge -> http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
