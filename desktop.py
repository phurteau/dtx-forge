"""DTX Forge - native desktop window (no browser).
Starts the local server in a background thread and shows the UI in its own
window via the Edge WebView2 runtime built into Windows."""
import threading, time, socket, urllib.request
import uvicorn
import webview
from app import app

HOST, PORT = "127.0.0.1", 8765


def _free_port(start):
    p = start
    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((HOST, p)) != 0:
                return p
        p += 1
    return start


def _serve(port):
    uvicorn.run(app, host=HOST, port=port, log_level="warning")


def main():
    port = _free_port(PORT)
    threading.Thread(target=_serve, args=(port,), daemon=True).start()
    url = f"http://{HOST}:{port}/"
    for _ in range(80):  # wait up to ~16s for server to answer
        try:
            urllib.request.urlopen(url, timeout=1); break
        except Exception:
            time.sleep(0.2)
    webview.create_window("DTX Forge", url, width=1040, height=880, min_size=(760, 640))
    webview.start()   # blocks until the window is closed


if __name__ == "__main__":
    main()
