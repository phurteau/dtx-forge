"""DTXScribe - native desktop window with automatic browser fallback.

Starts the local server in a background thread and shows the UI in its own window
via pywebview (Edge WebView2). If the native window can't start -- which can happen
in a frozen .exe where pywebview's .NET/pythonnet backend fails to resolve the
Python runtime -- it falls back to opening the default web browser and keeps the
server running, so the app always works instead of crashing.
"""
import os, threading, time, socket, urllib.request, sys, webbrowser, traceback

# In a windowed (console=False) PyInstaller build, sys.stdout / sys.stderr are None.
# Several libraries (notably uvicorn's logging, which calls sys.stdout.isatty())
# crash on that. Redirect the missing streams to a real writable null stream so the
# server can start and stray print()s never raise.
if sys.stdout is None or sys.stderr is None:
    _null = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = _null
    if sys.stderr is None:
        sys.stderr = _null

# Bind the whole process tree into a Windows Job Object that dies with us, so no child
# (uvicorn, a mid-encode ffmpeg, a yt-dlp/deno download, the WebView2 window) can ever be
# left running after DTXScribe exits -- by the Exit button, the window's X, or a crash. This
# runs before the server thread and before any subprocess could spawn. Best-effort, no-op off
# Windows.
try:
    from dtxscribe import winjob
    winjob.enable_kill_on_close()
except Exception:
    pass

# One-time rebrand data-folder migration (DTXForge -> DTXScribe) BEFORE anything
# touches %LOCALAPPDATA%, so an updated install keeps its already-downloaded model
# weights instead of re-fetching ~1 GB under the new name. Best-effort.
try:
    from dtxscribe import migrate_legacy_appdata
    migrate_legacy_appdata()
except Exception:
    pass

HOST, PORT = "127.0.0.1", 8765


def _log_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "DTXScribe")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        d = os.path.expanduser("~")
    return os.path.join(d, "dtxscribe.log")


LOG = _log_path()


def log(msg):
    line = time.strftime("%H:%M:%S") + "  " + str(msg)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        sys.stderr.write(line + "\n"); sys.stderr.flush()
    except Exception:
        pass


try:
    open(LOG, "w", encoding="utf-8").close()   # reset log each launch
except Exception:
    pass

log(f"=== DTXScribe starting (frozen={getattr(sys, 'frozen', False)}) ===")
log(f"python {sys.version}")
log(f"log file: {LOG}")

try:
    import uvicorn
    log("imported uvicorn OK")
    from app import app
    log("imported app OK (torch/pipeline loaded)")
except Exception:
    log("FATAL: import failed:\n" + traceback.format_exc())
    raise


def _free_port(start):
    p = start
    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((HOST, p)) != 0:
                return p
        p += 1
    return start


def _serve(port):
    try:
        log(f"server thread: starting uvicorn on {HOST}:{port}")
        # log_config=None: skip uvicorn's default logging setup, which calls
        # sys.stdout.isatty() and crashes in a windowed (no-console) frozen build.
        uvicorn.run(app, host=HOST, port=port, log_level="warning", log_config=None)
        log("server thread: uvicorn.run returned")
    except Exception:
        log("server thread CRASHED:\n" + traceback.format_exc())


def main():
    port = _free_port(PORT)
    log(f"chosen port: {port}")
    threading.Thread(target=_serve, args=(port,), daemon=True).start()
    url = f"http://{HOST}:{port}/"
    ready = False
    for i in range(150):  # wait up to ~30s for the server (torch import can be slow)
        try:
            urllib.request.urlopen(url, timeout=1); ready = True
            log(f"server reachable after ~{i * 0.2:.1f}s"); break
        except Exception:
            time.sleep(0.2)
    if not ready:
        log("WARNING: server not reachable after ~30s wait")

    # Try the native desktop window; fall back to the browser on any failure so the
    # app never hard-crashes with a winforms / "resolve Python runtime" error.
    try:
        import webview
        log("imported webview OK; creating native window")
        webview.create_window("DTXScribe", url, width=1040, height=880, min_size=(760, 640))
        webview.start()   # blocks until the window is closed
        log("webview.start() returned (window closed)")
        return
    except Exception:
        log("native window unavailable; opening in browser instead:\n" + traceback.format_exc())

    try:
        webbrowser.open(url)
        log(f"opened browser at {url}")
    except Exception:
        log("webbrowser.open failed:\n" + traceback.format_exc())
    print(f"DTXScribe is running -> {url}  (close this window to stop it)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
