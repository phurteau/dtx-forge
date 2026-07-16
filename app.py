"""DTX Forge web app: FastAPI backend + background job runner."""
import os, sys, uuid, threading, traceback, shutil


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
            set_label=rp["set_label"], set_slot=rp["set_slot"])
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


if __name__ == "__main__":
    import uvicorn
    print("DTX Forge -> http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
