"""DTX Forge web app: FastAPI backend + background job runner."""
import os, sys, uuid, threading, traceback, shutil

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

from fastapi import FastAPI, UploadFile, File, Form
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
        hihat_foot=(hihat_foot.strip() or "off"),
        double_bass=(double_bass.lower() == "true"),
        title=title.strip(), artist=artist.strip(), author=author.strip(),
        bpm=(float(bpm) if bpm.strip() else None),
        dlevel=dlevel.strip(),
        dlevel_tier=(dlevel_tier.strip() or "auto"),
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
        out["download"] = f"/api/download/{job_id}"
    if job["status"] == "error":
        out["error"] = job["error"]
    return out


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
    if not job or job["status"] != "done":
        return JSONResponse({"error": "not ready"}, status_code=404)
    z = job["result"]["zip"]
    return FileResponse(z, filename=os.path.basename(z), media_type="application/zip")


if __name__ == "__main__":
    import uvicorn
    print("DTX Forge -> http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
