"""Smart source detection + fetching. Turns a URL or uploaded file into a
notation source the pipeline can transcribe, without the user picking a type.

Detection order:
  * Songsterr URL / numeric id     -> ('songsterr', song_id)
  * URL ending in a GP extension   -> download -> ('guitarpro', path)
  * URL to a raw text tab          -> fetch    -> ('ascii', text)
  * local .gp*/.mid/.txt file      -> by extension
  * otherwise                      -> try to fetch and sniff (GP magic / MIDI / text)
"""
import os, re, gzip, urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DTXScribe/1.0"
GP_EXT = (".gp", ".gp3", ".gp4", ".gp5", ".gpx", ".gtp")
MIDI_EXT = (".mid", ".midi")
TXT_EXT = (".txt", ".tab", ".text")


def _fetch(url, max_bytes=8_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read(max_bytes)
        if r.headers.get("Content-Encoding") == "gzip":
            try: raw = gzip.decompress(raw)
            except Exception: pass
        ctype = r.headers.get("Content-Type", "")
    return raw, ctype


def _looks_like_gp(b):
    # GP3/4/5 start with a version pascal-string like 'FICHIER GUITAR PRO v...'
    head = b[:40]
    return b"GUITAR PRO" in head or b[:4] == b"PK\x03\x04" and b".gp" in b[:200].lower()


def _looks_like_midi(b):
    return b[:4] == b"MThd"


def detect(url_or_id="", file_path="", workdir="."):
    """Return (kind, payload) where kind in {songsterr, guitarpro, midi, ascii}.
    payload is a song_id (songsterr), a file path (guitarpro/midi), or text (ascii)."""
    os.makedirs(workdir, exist_ok=True)

    # ---- local file ----
    if file_path:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in GP_EXT:
            return "guitarpro", file_path
        if ext in MIDI_EXT:
            return "midi", file_path
        if ext in TXT_EXT:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return "ascii", f.read()
        # sniff by content
        with open(file_path, "rb") as f:
            head = f.read(4096)
        if _looks_like_midi(head):
            return "midi", file_path
        if _looks_like_gp(head):
            return "guitarpro", file_path
        try:
            return "ascii", head.decode("utf-8", "replace")
        except Exception:
            raise RuntimeError("Unrecognized file type.")

    s = (url_or_id or "").strip()
    if not s:
        raise RuntimeError("No source provided.")

    # ---- Songsterr (id or URL) ----
    if s.isdigit() or "songsterr.com" in s:
        from . import songsterr
        return "songsterr", songsterr.parse_song_id(s)

    # ---- URL by extension ----
    low = s.lower().split("?")[0]
    if s.startswith("http"):
        if low.endswith(GP_EXT):
            data, _ = _fetch(s)
            p = os.path.join(workdir, "tab" + os.path.splitext(low)[1])
            with open(p, "wb") as f: f.write(data)
            return "guitarpro", p
        if low.endswith(MIDI_EXT):
            data, _ = _fetch(s)
            p = os.path.join(workdir, "tab.mid")
            with open(p, "wb") as f: f.write(data)
            return "midi", p
        # fetch + sniff
        data, ctype = _fetch(s)
        if _looks_like_midi(data):
            p = os.path.join(workdir, "tab.mid")
            with open(p, "wb") as f: f.write(data)
            return "midi", p
        if _looks_like_gp(data):
            p = os.path.join(workdir, "tab.gp5")
            with open(p, "wb") as f: f.write(data)
            return "guitarpro", p
        text = data.decode("utf-8", "replace")
        # a readable ASCII drum tab has rows like 'HH|x-x-'
        if re.search(r"(?im)^\s*[A-Za-z][A-Za-z0-9#\-]{0,6}\s*[|:].*[xXoO]", text):
            return "ascii", text
        raise RuntimeError(
            "That URL doesn't contain readable drum-note data. Supported: a Songsterr "
            "tab link, a Guitar Pro file (.gp/.gp5), a MIDI file, or a plain-text drum tab.")

    # bare text pasted as the 'url' -> treat as ASCII tab
    if "|" in s and re.search(r"[xXoO]", s):
        return "ascii", s
    raise RuntimeError("Could not recognize the source. Paste a Songsterr link, a Guitar "
                       "Pro/MIDI URL, or upload a file.")
